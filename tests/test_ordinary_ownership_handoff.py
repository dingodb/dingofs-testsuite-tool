"""Run real standalone wrapper entrypoints with a controlled Python boundary."""
import os
from pathlib import Path
import shlex
import subprocess
import pytest


@pytest.mark.parametrize('custom', [False, True])
def test_local_setup_cleanup_share_explicit_config_directory(tmp_path, custom):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / 'repo' / 'dingofs-integration-test' / 'conf' / 'env').mkdir(parents=True)
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'repo').write_text(str(tmp_path / 'repo'))
    custom_dir = tmp_path / 'custom'
    custom_dir.mkdir()
    if custom:
        (custom_dir / 'test.yaml').write_text('name: test\n')
    script = f'''
source {shlex.quote(str(root / 'dingofs-testsuite-tool'))}
CONFIG_DIR={shlex.quote(str(config))}
unset DINGOFS_TESTSUITE_CONFIG_DIR
load_config() {{ case "$1" in repo) printf '%s' {shlex.quote(str(tmp_path / 'repo'))};; custom) printf '%s' {shlex.quote(str(custom_dir))};; esac; }}
python3() {{ printf 'HANDOFF=%s\\n' "${{DINGOFS_TESTSUITE_CONFIG_DIR:-missing}}"; if [[ -f conf/env/test.yaml ]]; then printf 'ENV_VISIBLE=yes\\n'; fi; }}
_run_setup_env test
_run_cleanup_env test
'''
    result = subprocess.run(['bash', '-c', script], text=True, capture_output=True,
                            env={**os.environ, 'DINGOFS_TESTSUITE_CONFIG_DIR': str(config)})
    assert result.returncode == 0, result.stderr
    assert result.stdout.count('HANDOFF=' + str(config)) == 2
    if custom:
        assert result.stdout.count('ENV_VISIBLE=yes') == 2
