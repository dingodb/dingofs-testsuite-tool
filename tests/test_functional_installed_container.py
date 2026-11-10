"""Opt-in actual package -> Docker -> entrypoint -> framework integration.

Requires the platform checkout/venv and an already present runtime image. No
pulls or SSH: a test-only Docker shim enforces --network=none and replaces only
Paramiko transport. Capability verification is deliberately never mocked.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('DTT_RUN_FUNCTIONAL_CONTAINER') == '1',
                     'Set DTT_RUN_FUNCTIONAL_CONTAINER=1 for offline local Docker integration')
class InstalledFunctionalContainer(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='dtt-installed-functional-')
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)
        platform_root = Path(os.environ['DTT_PLATFORM_SOURCE'])
        sys.path.insert(0, str(platform_root / 'backend/src'))
        self.addCleanup(sys.path.remove, str(platform_root / 'backend/src'))
        from dingofs_platform.tool_packages.functional_bundle import functional_source_files, FUNCTIONAL_FEATURES
        from dingofs_platform.tool_packages.remote import install_script
        from dingofs_platform.functional.source_bridge import inspect_source

        docker = shutil.which('docker')
        image = os.environ.get('DTT_FUNCTIONAL_TEST_IMAGE', 'dingofs-testsuite-tools:latest')
        info = json.loads(subprocess.check_output([docker, 'image', 'inspect', image]))[0]
        stage = self.temp / 'stage'
        stage.mkdir()
        paths, _, aliases = functional_source_files(ROOT)
        # Keep actual reviewed program bytes and cases; replace all real env
        # configs with synthetic credentials/TEST-NET hosts before packaging.
        for name, original in paths.items():
            if name.startswith('dingofs-integration-test/conf/'):
                continue
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
        for alias, target in aliases.items():
            link = stage / 'dingofs-integration-test' / alias
            link.unlink()
            link.symlink_to(os.path.relpath(stage / 'dingofs-integration-test' / target, link.parent))
        for name in ('dingofs-testsuite-tool', 'dtt-ai-analyze', 'analysis.schema.json'):
            shutil.copyfile(ROOT / name, stage / name)
        source = stage / 'dingofs-integration-test'
        (source / 'conf/env').mkdir(parents=True)
        (source / 'conf/env/fixture.yaml').write_text(
            'selected:\n  mds_addr: 192.0.2.1:6700\n  host: fixture-mds\n'
            '  ssh_user: tester\n  run_as_user: tester/fixture-secret\n'
            '  dingo_tool_path: /bin/dingo\n  mds_client_path: /bin/mds-client\n'
            '  storage: {storage_type: s3, storage_env: fixture}\n'
            '  clients: [{host: fixture-client, fs_name: fixed-fs, mount_path: /mnt/fs}]\n')
        (source / 'conf/storage.yaml').write_text(
            'fixture:\n  s3: {s3_ak: fixture-secret, s3_sk: fixture-secret, '
            's3_endpoint: http://store, s3_bucketname: bucket}\n')
        case = source / 'testcases/quota_test_cases/integration_fixture.yaml'
        case.write_text('case_name: installed fixture\nrequired_environment: selected\n'
                        'steps: [{step_name: sleep, parameter: {sleep_second: 0}}]\n')
        (case.parent / 'custom_fixture.yaml').write_text(
            'case_name: installed custom fixture\nrequired_environment: env_platform_abc\n'
            'steps: [{step_name: sleep, parameter: {sleep_second: 0}}]\n')
        alias = source / 'testcases/quota_test_cases/smoke/integration_alias.yaml'
        alias.parent.mkdir(exist_ok=True)
        alias.symlink_to('../integration_fixture.yaml')
        selected = {'quota': ['testcases/quota_test_cases/smoke/integration_alias.yaml']}
        original_descriptor = inspect_source(source, 'selected', selected)
        self.assertEqual(original_descriptor.issues, [])
        paths, manifest, aliases = functional_source_files(stage)
        for name in ('dingofs-testsuite-tool', 'dtt-ai-analyze', 'analysis.schema.json'):
            paths[name] = stage / name
        files = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
        # Real transfer representation consists of regular bytes.
        for alias, target in aliases.items():
            link = source / alias
            link.unlink()
            shutil.copyfile(source / target, link)
        bundle = dict(tool='dtt', entrypoint='dingofs-testsuite-tool', version='integration',
            architecture=platform.machine(), digest=hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
            image_id=info['Id'], files=files, source_manifest=manifest,
            source_aliases=aliases, functional_features=FUNCTIONAL_FEATURES)
        home = self.temp / 'home'
        home.mkdir()
        self.env = dict(os.environ, HOME=str(home), PYTHONDONTWRITEBYTECODE='1')
        installed = subprocess.run([sys.executable, '-B', '-'], input=install_script(bundle, str(stage)),
            env=self.env, capture_output=True, text=True, timeout=180)
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        self.record = json.loads(installed.stdout.splitlines()[-1])
        self.executable = self.record['immutable_path']
        self.source = Path(self.executable).parent / 'dingofs-integration-test'
        descriptor = inspect_source(self.source, 'selected', selected)
        self.assertEqual(descriptor.model_dump(), original_descriptor.model_dump())
        probe = subprocess.run([self.executable, '--functional-capabilities', '--format', 'json'],
            env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(json.loads(probe.stdout), self.record['functional_runtime'])
        approved = [target.model_dump() for target in descriptor.targets]
        routes = []
        for alias in sorted({target.host for target in descriptor.targets}):
            address = {'fixture-mds': '192.0.2.1', 'fixture-client': '192.0.2.2'}.get(alias, alias)
            index = 1 if address == '192.0.2.1' else 2
            routes.append(dict(source_host=alias, address=address, port=2222, user='tester',
                               machine_id=str(index), machine_name='fixture-' + str(index)))
            approved.extend({**target.model_dump(), 'host': address} for target in descriptor.targets if target.host == alias)
        self.context = self.temp / 'context.json'
        self.context.write_text(json.dumps(dict(version=1, parent_id='parent', child_id='child', module='quota',
            env_name='selected', retries=1, source_manifest=descriptor.source_manifest,
            approved_targets=approved, resolved_targets=routes, functional_runtime=self.record['functional_runtime'])))
        self.plan = self.temp / 'plan.json'
        self.plan.write_text(json.dumps(dict(version=1, modules={'quota': ['smoke/integration_alias.yaml']},
            hashes={'quota': {'smoke/integration_alias.yaml': manifest['testcases/quota_test_cases/integration_fixture.yaml']}}
        )))
        transport = self.temp / 'transport'
        shutil.copytree(ROOT / 'tests/functional_transport', transport,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copyfile(ROOT / 'dingofs-integration-test/tests/test_functional_owned_lifecycle.py', transport / 'owned_remote.py')
        bindir = self.temp / 'bin'
        bindir.mkdir()
        shim = bindir / 'docker'
        shim.write_text('#!' + sys.executable + '\nimport os,sys\nargs=sys.argv[1:]\n'
            'if args[:1]==["run"]:\n'
            ' args=[a for a in args if a!="--net=host"]\n'
            ' args[1:1]=["--network=none","--read-only","--tmpfs","/tmp:rw,nosuid",'
            '"-v",' + repr(str(transport) + ':/test-transport:ro') + ',"-e","PYTHONPATH=/test-transport"]\n'
            'os.execv(' + repr(docker) + ',[' + repr(docker) + ']+args)\n')
        shim.chmod(0o755)
        self.env['PATH'] = str(bindir) + ':' + os.environ['PATH']

    def launch(self):
        return subprocess.run([self.executable, '-t', 'int', '-s', 'quota', '--env', 'selected',
            '--case-plan', str(self.plan), '--functional-context', str(self.context), '-o', str(self.temp / 'output')],
            env=self.env, capture_output=True, text=True, timeout=120)

    def test_real_installed_cli_lifecycle_and_reports(self):
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.temp / 'output/parent/child'
        self.assertEqual((output / 'functional-events.jsonl').stat().st_uid, os.geteuid(),
                         'Private events must be readable by the installed execution user')
        events = [json.loads(line) for line in (output / 'functional-events.jsonl').read_text().splitlines()]
        self.assertEqual([event['seq'] for event in events], list(range(1, len(events) + 1)))
        final = next(event for event in events if event['type'] == 'suite_finished')
        self.assertEqual(final['data']['status'], 'completed')
        self.assertEqual(final['data']['cleanup_status'], 'cleaned')
        self.assertEqual(final['data']['results'], [dict(case_path='smoke/integration_alias.yaml', attempt=1, final=True, status='PASS')])
        report = next(event for event in events if event['type'] == 'report_finished')
        self.assertTrue(report['data']['success'])
        self.assertTrue((output / report['data']['path']).is_file())
        self.assertTrue((output / 'int_allure_report/allure-report-latest/index.html').is_file())
        transport = json.loads((output / 'transport.json').read_text())
        self.assertEqual({item['hostname'] for item in transport['connections']}, {'192.0.2.1', '192.0.2.2'})
        self.assertGreater(transport['command_count'], 10)
        self.assertEqual(transport['remaining_filesystems'], {'shared-external': '900', 'shared-sibling': '901'})
        self.assertEqual(transport['remaining_mounts'], [])
        self.assertEqual(transport['remaining_directories'], {})
        self.assertFalse(list(self.source.rglob('__pycache__')))
        for path in output.rglob('*'):
            if path.is_file():
                self.assertEqual(path.stat().st_uid, os.geteuid(), str(path))
                self.assertNotIn(b'fixture-secret', path.read_bytes(), str(path))

    def test_actual_framework_rejects_changed_plan_before_remote_setup(self):
        plan = json.loads(self.plan.read_text())
        plan['hashes']['quota']['smoke/integration_alias.yaml'] = '0' * 64
        self.plan.write_text(json.dumps(plan))
        result = self.launch()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        output = self.temp / 'output/parent/child'
        self.assertFalse((output / 'resources.jsonl').exists())
        transport = json.loads((output / 'transport.json').read_text())
        self.assertEqual(transport['connections'], [])
        self.assertEqual(transport['command_count'], 0)

    def test_actual_installed_bytes_are_rechecked_before_launch(self):
        with (self.source / 'src/config/env_parser.py').open('a') as stream:
            stream.write('\n# post-install tamper\n')
        result = self.launch()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('digest mismatch', result.stderr)
        self.assertFalse((self.temp / 'output').exists())

    def test_new_package_preserves_custom_preflight(self):
        from dingofs_platform.functional.environments.preflight import PROBE_CODE
        checked = subprocess.run([sys.executable, '-B', '-c', "DINGO_PATH='/bin/true'\n" + PROBE_CODE],
            env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout), {'dtt': True, 'runtime': True, 'dingo': True})

    def test_new_package_runs_custom_exact_plan_with_complete_imports(self):
        custom = self.temp / 'env_platform_abc.yaml'
        custom.write_text('env_platform_abc:\n  mds_addr: 192.0.2.1:6700\n'
            '  host: 192.0.2.1\n  ssh_user: tester\n  run_as_user: tester/fixture-secret\n'
            '  dingo_tool_path: /bin/dingo\n  clients: []\n')
        plan = self.temp / 'custom-plan.json'
        digest = hashlib.sha256((self.source / 'testcases/quota_test_cases/custom_fixture.yaml').read_bytes()).hexdigest()
        plan.write_text(json.dumps({'version': 1, 'modules': {'quota': ['custom_fixture.yaml']},
                                   'hashes': {'quota': {'custom_fixture.yaml': digest}}}))
        output = self.temp / 'custom-output'
        result = subprocess.run([self.executable, '-t', 'int', '-s', 'quota', '--env', 'env_platform_abc',
            '--case-plan', str(plan), '--int-env-file', str(custom), '-m', str(self.temp / 'data'), '-o', str(output)],
            env={**self.env, 'DTT_MDSADDR': '192.0.2.1:6700'}, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = [json.loads(line) for line in (output / 'functional-events.jsonl').read_text().splitlines()]
        self.assertTrue(any(row['type'] == 'case_finished' and row['data']['status'] == 'PASS' for row in rows))
        self.assertFalse(list(self.source.rglob('__pycache__')))
        for path in output.rglob('*'):
            if path.is_file():
                self.assertEqual(path.stat().st_uid, os.geteuid())
                self.assertNotIn(b'fixture-secret', path.read_bytes())


if __name__ == '__main__':
    unittest.main()
