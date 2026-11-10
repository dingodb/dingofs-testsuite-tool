"""Hermetic wrapper checks: fake Docker accepts inspect/run only, never external I/O."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ['exact_case_plan_v1', 'runtime_context_v1', 'owned_cleanup_v1',
            'lifecycle_events_v2', 'cancel_boundary_v1', 'inspection_v1']
REQUIRED = ['run_tests.py', 'requirements.txt', 'pytest.ini',
            'src/test_runner/functional_plan.py', 'src/test_runner/runtime_context.py',
            'src/test_runner/resource_journal.py', 'src/test_runner/owned_resources.py',
            'src/test_runner/functional_events.py', 'src/test_runner/functional_redaction.py',
            'src/test_runner/functional_contracts.py', 'src/test_runner/functional_capabilities.py',
            'src/config/ssh_client.py', 'src/config/env_parser.py']


def make_package(root):
    root.mkdir(parents=True, exist_ok=True)
    for name in ('dingofs-testsuite-tool', 'entrypoint.sh', 'functional_runtime.py'):
        if (ROOT / name).exists():
            shutil.copyfile(ROOT / name, root / name)
    source = root / 'dingofs-integration-test'
    for name in REQUIRED + ['conf/env/base.yaml', 'conf/storage.yaml', 'testcases/quota_test_cases/smoke.yaml']:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic fixture\n')
    (source / 'functional_protocol.json').write_text(json.dumps({
        'version': 2, 'features': FEATURES, 'context_version': 1, 'event_version': 2}))
    source_manifest = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in source.rglob('*') if p.is_file()}
    files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*') if p.is_file()}
    cap = {'version': 2, 'features': FEATURES, 'files': files,
           'image_id': 'sha256:' + 'a' * 64, 'source_manifest': source_manifest}
    (root / 'functional-runtime.json').write_text(json.dumps({
        'architecture': platform.machine(), 'functional_runtime': cap}))
    return cap


class FunctionalRuntimeCLI(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='functional runtime ')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.package = self.root / 'immutable package'
        self.cap = make_package(self.package)
        self.log = self.root / 'docker.jsonl'
        bindir = self.root / 'bin'
        bindir.mkdir()
        fake = bindir / 'docker'
        fake.write_text('#!/usr/bin/env python3\nimport json,os,sys\n'
                        'with open(os.environ["FAKE_DOCKER_LOG"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                        'if sys.argv[1:3]==["image","inspect"]: print(json.dumps([{'
                        '"Id":os.environ["FAKE_IMAGE"],"Os":"linux","Architecture":os.environ["FAKE_ARCH"]}]))\n'
                        'elif sys.argv[1:2]!=["run"]: sys.exit(99)\n')
        fake.chmod(0o755)
        self.env = dict(os.environ, PATH=str(bindir) + ':' + os.environ['PATH'],
                        DINGOFS_TESTSUITE_CONFIG_DIR=str(self.root / 'must not create'),
                        FAKE_DOCKER_LOG=str(self.log), FAKE_IMAGE=self.cap['image_id'],
                        FAKE_ARCH={'x86_64': 'amd64', 'aarch64': 'arm64'}[platform.machine()])
        self.plan = self.root / 'case plan.json'
        self.plan.write_text('{"version":1,"modules":{"quota":["testcases/quota_test_cases/smoke.yaml"]}}')
        self.context = self.root / 'context.json'
        self.context_data = {'version': 1, 'parent_id': 'parent', 'child_id': 'child', 'module': 'quota', 'retries':2,
                             'env_name': 'env_original', 'source_manifest': self.cap['source_manifest'],
                             'approved_targets': [{'host':'alias','user':'tester','role':'client','mutates':True},
                                                  {'host':'192.0.2.1','user':'tester','role':'client','mutates':True}],
                             'resolved_targets': [{'source_host':'alias','machine_id':1,'machine_name':'fixture','address':'192.0.2.1','port':22,'user':'tester'}],
                             'functional_runtime': self.cap}
        self.context.write_text(json.dumps(self.context_data))

    def invoke(self, *args):
        return subprocess.run(['bash', str(self.package / 'dingofs-testsuite-tool'), *args],
                              env=self.env, capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def launch(self, *extra):
        return self.invoke('-t', 'int', '-s', 'quota', '--env', 'env_original',
                           '--case-plan', str(self.plan), '--functional-context', str(self.context),
                           '-o', str(self.root / 'output'), *extra)

    def test_missing_capability_fails_before_launch(self):
        (self.package / 'functional-runtime.json').unlink()
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_capability_is_read_only_and_complete(self):
        result = self.invoke('--functional-capabilities', '--format', 'json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.cap)
        self.assertFalse((self.root / 'must not create').exists())
        self.assertEqual([call[:2] for call in self.calls()], [['image', 'inspect']])

    def test_context_and_manifest_are_read_only_mounts(self):
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run = next(call for call in self.calls() if call[0] == 'run')
        self.assertIn(str(self.context) + ':' + str(self.context) + ':ro', run)
        self.assertIn(str(self.plan) + ':' + str(self.plan) + ':ro', run)
        self.assertIn(str(self.package) + ':/functional-runtime:ro', run)
        self.assertIn('--pull=never', run)
        self.assertIn(self.cap['image_id'], run)
        self.assertIn('HOME=/functional-home', run)
        self.assertIn('SSH_AUTH_SOCK=', run)
        self.assertIn('DTT_FUNCTIONAL_OUTPUT_DIR=/output', run)
        self.assertIn(str(self.root / 'output/parent/child') + ':/output', run)

    def test_image_and_base_digest_change_rejected(self):
        self.env['FAKE_IMAGE'] = 'sha256:' + 'b' * 64
        self.assertNotEqual(self.launch().returncode, 0)
        self.assertFalse(any(call[0] == 'run' for call in self.calls()))
        self.log.unlink(missing_ok=True)
        self.env['FAKE_IMAGE'] = self.cap['image_id']
        (self.package / 'dingofs-integration-test/conf/env/base.yaml').write_text('changed')
        self.assertNotEqual(self.launch().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_changed_approval_old_protocol_and_wrong_architecture_rejected(self):
        self.context_data['functional_runtime']['image_id'] = 'sha256:' + 'c' * 64
        self.context.write_text(json.dumps(self.context_data))
        self.assertNotEqual(self.launch().returncode, 0)
        self.assertFalse(any(call[0] == 'run' for call in self.calls()))
        self.env['FAKE_ARCH'] = 'invalid'
        self.assertNotEqual(self.invoke('--functional-capabilities', '--format', 'json').returncode, 0)
        protocol = self.package / 'dingofs-integration-test/functional_protocol.json'
        protocol.write_text('{"version":1}')
        self.assertNotEqual(self.launch().returncode, 0)

    def test_unlisted_file_or_missing_protocol_dependency_rejected(self):
        (self.package / 'dingofs-integration-test/src/injected.py').write_text('unsafe')
        self.assertNotEqual(self.launch().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_setup_switch_rejected_before_any_container(self):
        result = self.launch('--setup-env', 'unsafe')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_context_cannot_embed_credentials_or_unapproved_route(self):
        self.context_data['approved_targets'][0]['password']='synthetic-secret'
        self.context.write_text(json.dumps(self.context_data))
        self.assertNotEqual(self.launch().returncode,0)
        self.assertEqual(self.calls(),[])
        del self.context_data['approved_targets'][0]['password']
        self.context_data['resolved_targets'][0]['user']='unapproved'
        self.context.write_text(json.dumps(self.context_data))
        self.assertNotEqual(self.launch().returncode,0)
        self.assertEqual(self.calls(),[])

    def test_container_check_rejects_changed_source_without_subprocess(self):
        import runpy
        from unittest.mock import patch
        module=runpy.run_path(str(self.package/'functional_runtime.py'))
        (self.package/'dingofs-integration-test/conf/env/base.yaml').write_text('tampered')
        with patch('sys.version_info',(3,12,0)), patch('subprocess.run',side_effect=AssertionError('Container validation must be local')):
            with self.assertRaisesRegex(ValueError,'digest mismatch'):
                module['main'](['--verify-container',str(self.context)])

    def test_container_python_version_is_checked_separately(self):
        import runpy
        from unittest.mock import patch
        module=runpy.run_path(str(self.package/'functional_runtime.py'))
        with patch('sys.version_info',(3,9,0)), patch('subprocess.run',side_effect=AssertionError('No Docker in container validation')):
            with self.assertRaisesRegex(ValueError,'Python 3.10'):
                module['main'](['--verify-container',str(self.context)])

    def test_incomplete_protocol_cannot_be_hidden_by_rehashing(self):
        missing='src/test_runner/functional_events.py'
        (self.package/'dingofs-integration-test'/missing).unlink()
        del self.cap['source_manifest'][missing]
        del self.cap['files']['dingofs-integration-test/'+missing]
        (self.package/'functional-runtime.json').write_text(json.dumps({'architecture':platform.machine(),'functional_runtime':self.cap}))
        self.assertNotEqual(self.invoke('--functional-capabilities','--format','json').returncode,0)
        self.assertEqual(self.calls(),[])

    def test_retry_budget_is_frozen_and_ambient_override_ignored(self):
        self.env['DTT_INT_RERUNS']='5'
        result=self.launch()
        self.assertEqual(result.returncode,0,result.stderr)
        run=next(call for call in self.calls() if call[0]=='run')
        self.assertIn('DTT_INT_RERUNS=2',run)
        self.assertNotIn('DTT_INT_RERUNS=5',run)
        for invalid in (-1,6,True,'2'):
            self.context_data['retries']=invalid
            self.context.write_text(json.dumps(self.context_data))
            self.assertNotEqual(self.launch().returncode,0)

    def add_declared_alias(self):
        relative='testcases/quota_test_cases/alias.yaml'
        target='testcases/quota_test_cases/smoke.yaml'
        alias=self.package/'dingofs-integration-test'/relative
        alias.symlink_to('smoke.yaml')
        mapping=self.package/'functional-aliases.json'
        mapping.write_text(json.dumps({relative:target}))
        self.cap['files']['functional-aliases.json']=hashlib.sha256(mapping.read_bytes()).hexdigest()
        self.cap['source_manifest'][relative]=self.cap['source_manifest'][target]
        self.cap['files']['dingofs-integration-test/'+relative]=self.cap['source_manifest'][target]
        (self.package/'functional-runtime.json').write_text(json.dumps({'architecture':platform.machine(),'functional_runtime':self.cap}))
        self.context.write_text(json.dumps(self.context_data))
        return alias,mapping

    def test_declared_case_alias_is_pinned_and_retargeting_rejected(self):
        alias,mapping=self.add_declared_alias()
        result=self.launch()
        self.assertEqual(result.returncode,0,result.stderr)
        alias.unlink();alias.symlink_to('/etc/passwd')
        result=self.invoke('--functional-capabilities','--format','json')
        self.assertNotEqual(result.returncode,0)

    def test_alias_map_tampering_rejected_before_docker(self):
        alias,mapping=self.add_declared_alias()
        mapping.write_text('{}')
        self.assertNotEqual(self.invoke('--functional-capabilities','--format','json').returncode,0)
        self.assertEqual(self.calls(),[])

    def test_alias_target_tampering_rejected_before_docker(self):
        alias,mapping=self.add_declared_alias()
        alias.resolve().write_text('changed canonical target')
        self.assertNotEqual(self.invoke('--functional-capabilities','--format','json').returncode,0)
        self.assertEqual(self.calls(),[])

    def test_alias_cycle_rejected_before_docker(self):
        alias,mapping=self.add_declared_alias()
        alias.unlink();alias.symlink_to(alias.name)
        self.assertNotEqual(self.invoke('--functional-capabilities','--format','json').returncode,0)
        self.assertEqual(self.calls(),[])
