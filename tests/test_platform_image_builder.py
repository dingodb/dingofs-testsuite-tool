import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / 'scripts/build_platform_image.py'


def invoke(source, context):
    return subprocess.run([sys.executable, '-B', str(BUILDER), '--source-root', str(source),
                           '--context', str(context), '--no-build'], text=True, capture_output=True)


def test_prepared_context_binds_complete_reviewed_sources_and_small_package(tmp_path):
    source = tmp_path / 'source'
    shutil.copytree(ROOT, source, symlinks=True, ignore=shutil.ignore_patterns('.git', '__pycache__', '.pytest_cache'))
    (source / 'scripts/ai_storage_scenarios.py').write_text('SCENARIOS = {}\n')
    cache = source / 'dingofs-integration-test/src/__pycache__'
    cache.mkdir(exist_ok=True)
    (cache / 'stale.pyc').write_bytes(b'stale')
    context = tmp_path / 'context'
    result = invoke(source, context)
    assert result.returncode == 0, result.stderr
    package = context / 'package'
    manifest = json.loads((package / 'image-manifest.json').read_text())
    assert manifest['tool'] == 'dtt'
    assert manifest['entrypoint'] == 'dingofs-testsuite-tool'
    assert manifest['source_location'] == 'image'
    assert 'image_id' not in manifest
    assert 'image-manifest.json' not in manifest['files']
    assert not (package / 'dingofs-integration-test').exists()
    assert set(manifest['files']) == {'dingofs-testsuite-tool', 'dtt-ai-analyze', 'analysis.schema.json',
        'entrypoint.sh', 'functional_runtime.py', 'performance_benchmark.py', 'performance_plan.py',
        'performance_report.py', 'performance_tools.py', 'ai_storage_scenarios.py'}
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == digest
    tree = context / 'dingofs-integration-test'
    assert not list(tree.rglob('__pycache__'))
    assert 'src/config/ssh_client.py' in manifest['source_manifest']
    assert manifest['source_aliases']
    for alias, target in manifest['source_aliases'].items():
        assert (tree / alias).is_symlink()
        assert (tree / alias).resolve() == tree / target
    for name, digest in manifest['source_manifest'].items():
        assert hashlib.sha256((tree / name).read_bytes()).hexdigest() == digest


def test_existing_context_is_not_overwritten(tmp_path):
    context = tmp_path / 'context'
    context.mkdir()
    (context / 'keep').write_text('user data')
    result = invoke(ROOT, context)
    assert result.returncode != 0
    assert 'empty directory' in result.stderr
    assert (context / 'keep').read_text() == 'user data'


def test_external_source_alias_is_rejected(tmp_path):
    source = tmp_path / 'source'
    shutil.copytree(ROOT, source, symlinks=True,
                    ignore=shutil.ignore_patterns('.git', '__pycache__', '.pytest_cache'))
    (source / 'dingofs-integration-test/testcases/escape.yaml').symlink_to('/etc/passwd')
    result = invoke(source, tmp_path / 'context')
    assert result.returncode != 0
    assert 'alias' in result.stderr.lower()


def load_builder():
    import importlib.util
    spec=importlib.util.spec_from_file_location('platform_builder', BUILDER)
    builder=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    return builder


def test_raw_base_id_resolves_to_verified_local_repository_digest(monkeypatch):
    builder=load_builder()
    image_id='sha256:'+'a'*64
    repo='local.example/dtt@sha256:'+'b'*64
    def inspect(argv, **kwargs):
        assert argv[:3]==['docker','image','inspect']
        assert argv[3] in (image_id,repo)
        return subprocess.CompletedProcess(argv,0,json.dumps([{'Id':image_id,'RepoDigests':[repo]}]),'')
    monkeypatch.setattr(builder.subprocess,'run',inspect)
    assert builder.resolve_base_image(image_id)==repo


def test_raw_base_id_without_repository_digest_is_rejected(monkeypatch):
    import pytest
    builder=load_builder()
    image_id='sha256:'+'a'*64
    monkeypatch.setattr(builder.subprocess,'run',lambda argv,**kw:
        subprocess.CompletedProcess(argv,0,json.dumps([{'Id':image_id,'RepoDigests':[]}]),''))
    with pytest.raises(ValueError,match='repository digest'):
        builder.resolve_base_image(image_id)


def test_raw_base_id_rejects_repository_digest_with_different_identity(monkeypatch):
    import pytest
    builder=load_builder()
    image_id='sha256:'+'a'*64
    repo='local.example/dtt@sha256:'+'b'*64
    def inspect(argv, **kwargs):
        identity=image_id if argv[3]==image_id else 'sha256:'+'c'*64
        return subprocess.CompletedProcess(argv,0,json.dumps([{'Id':identity,'RepoDigests':[repo]}]),'')
    monkeypatch.setattr(builder.subprocess,'run',inspect)
    with pytest.raises(ValueError,match='repository digest'):
        builder.resolve_base_image(image_id)
