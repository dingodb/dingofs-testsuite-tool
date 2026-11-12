import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import test_functional_runtime_cli as fixtures

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('image_runtime', ROOT/'functional_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


@pytest.fixture
def image_package(tmp_path, monkeypatch):
    root = tmp_path/'package'
    cap = fixtures.make_package(root)
    (root/'dingofs-integration-test').rename(tmp_path/'image-source')
    cap['files'] = {p:h for p,h in cap['files'].items() if not p.startswith('dingofs-integration-test/')}
    document = json.loads((root/'functional-runtime.json').read_text())
    document.update(source_location='image', functional_runtime=cap)
    (root/'functional-runtime.json').write_text(json.dumps(document))
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        if argv[1:3] == ['image','inspect']:
            architecture = {'x86_64': 'amd64', 'aarch64': 'arm64'}[document['architecture']]
            return subprocess.CompletedProcess(argv,0,json.dumps([{'Id':cap['image_id'],'Os':'linux','Architecture':architecture}]),'')
        assert argv[1]=='run' and '--network=none' in argv and '--read-only' in argv
        assert argv[-1]=='--image-source-manifest'
        return subprocess.CompletedProcess(argv,0,json.dumps(cap['source_manifest']),'')
    monkeypatch.setattr(runtime.subprocess,'run',run)
    return root,cap,calls,tmp_path/'image-source'


def test_image_capability_needs_no_host_source(image_package):
    root,cap,calls,_=image_package
    assert runtime.capability(root)==cap
    assert any(c[-1]=='--image-source-manifest' for c in calls)
    assert not (root/'dingofs-integration-test').exists()


def test_image_container_checks_actual_source(image_package):
    root,cap,_,source=image_package
    assert runtime.capability(root,inspect_image=False,container_source=source)==cap
    (source/'run_tests.py').write_text('changed')
    with pytest.raises(ValueError,match='manifest'):
        runtime.capability(root,inspect_image=False,container_source=source)


def test_image_manifest_mismatch_rejected(image_package,monkeypatch):
    root,_,_,_=image_package
    original=runtime.subprocess.run
    def run(argv,**kw):
        if argv[-1]=='--image-source-manifest':return subprocess.CompletedProcess(argv,0,'{}','')
        return original(argv,**kw)
    monkeypatch.setattr(runtime.subprocess,'run',run)
    with pytest.raises(ValueError,match='manifest'):
        runtime.capability(root)


@pytest.mark.parametrize('guided', [True, False])
def test_image_launch_protects_cases_and_keeps_scratch_writable(tmp_path,monkeypatch,guided):
    fixture=fixtures.FunctionalRuntimeCLI()
    fixture.setUp()
    try:
        root=fixture.package
        doc=json.loads((root/'functional-runtime.json').read_text())
        doc['source_location']='image'
        (root/'functional-runtime.json').write_text(json.dumps(doc))
        monkeypatch.setattr(runtime,'capability',lambda *a,**kw: fixture.cap)
        monkeypatch.setattr(runtime,'execution_identity_args',lambda engine: [])
        commands=[]
        monkeypatch.setattr(runtime.subprocess,'call',lambda argv: commands.append(argv) or 0)
        argv=['-t','int','-s','quota','--env','env_original','--case-plan',str(fixture.plan),'-o',str(tmp_path/'out')]
        if guided:
            argv += ['--functional-context',str(fixture.context)]
        assert (runtime.launch if guided else runtime.launch_legacy)(root,argv)==0
        assert not any(':/dingofs-integration-test' in a for a in commands[0])
        assert str(root)+':/functional-runtime:ro' in commands[0]
        assert '--read-only' in commands[0]
        tmpfs=[commands[0][i+1] for i,arg in enumerate(commands[0][:-1]) if arg=='--tmpfs']
        assert '/tmp:rw,nosuid,nodev,mode=1777' in tmpfs
        assert any(value.startswith('/functional-home:rw,') for value in tmpfs)
        assert any(value.startswith(str(tmp_path/'out')) and value.endswith(':/output') for value in commands[0])
    finally:fixture.doCleanups()


def test_legacy_image_allows_only_selected_generated_environment(image_package):
    root,cap,_,source=image_package
    custom=source/'conf/env/env_platform_abc123.yaml'
    custom.parent.mkdir(parents=True,exist_ok=True)
    custom.write_text('custom environment')
    assert runtime.capability(root,inspect_image=False,container_source=source,
                              legacy_env='env_platform_abc123')==cap
    (custom.parent/'env_platform_def456.yaml').write_text('unexpected environment')
    with pytest.raises(ValueError,match='manifest'):
        runtime.capability(root,inspect_image=False,container_source=source,
                           legacy_env='env_platform_abc123')


def test_legacy_custom_environment_does_not_allow_frozen_source_tampering(image_package):
    root,_,_,source=image_package
    custom=source/'conf/env/env_platform_abc123.yaml'
    custom.parent.mkdir(parents=True,exist_ok=True)
    custom.write_text('custom environment')
    (source/'run_tests.py').write_text('changed original')
    with pytest.raises(ValueError,match='manifest'):
        runtime.capability(root,inspect_image=False,container_source=source,
                           legacy_env='env_platform_abc123')


def test_guided_image_rejects_generated_environment_extra(image_package):
    root,_,_,source=image_package
    custom=source/'conf/env/env_platform_abc123.yaml'
    custom.parent.mkdir(parents=True,exist_ok=True)
    custom.write_text('custom environment')
    with pytest.raises(ValueError,match='manifest'):
        runtime.capability(root,inspect_image=False,container_source=source)


def test_legacy_custom_environment_cannot_replace_frozen_environment(image_package):
    root,cap,_,source=image_package
    custom=source/'conf/env/env_platform_abc123.yaml'
    custom.parent.mkdir(parents=True,exist_ok=True)
    custom.write_text('reviewed environment')
    cap['source_manifest']['conf/env/env_platform_abc123.yaml']=runtime.digest(custom)
    document=json.loads((root/'functional-runtime.json').read_text())
    document['functional_runtime']=cap
    (root/'functional-runtime.json').write_text(json.dumps(document))
    custom.write_text('changed environment')
    with pytest.raises(ValueError,match='manifest'):
        runtime.capability(root,inspect_image=False,container_source=source,
                           legacy_env='env_platform_abc123')


def test_legacy_cli_scopes_allowance_to_selected_environment(monkeypatch):
    calls=[]
    monkeypatch.setenv('INT_ENV','env_platform_abc123')
    monkeypatch.setattr(runtime,'capability',lambda *a,**kw: calls.append(kw))
    assert runtime.main(['--verify-legacy-container'])==0
    assert calls[0]['legacy_env']=='env_platform_abc123'
