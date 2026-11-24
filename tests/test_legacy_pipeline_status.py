"""Exercise legacy runners with offline producers, including failed log sinks."""
import os
from pathlib import Path
import shlex
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('runner', ['fio', 'perf', 'ltp'])
@pytest.mark.parametrize('producer_status', [0, 7, 124])
@pytest.mark.parametrize('tee_status', [0, 9])
def test_runner_records_producer_failure_and_finishes_reporting(
        tmp_path, runner, producer_status, tee_status):
    producer = tmp_path / 'producer'
    producer.write_text('#!/bin/bash\nprintf "fake output\\n"\nexit "$PRODUCER_STATUS"\n')
    producer.chmod(0o755)
    config = tmp_path / (tmp_path.name + '.sh' if runner == 'perf' else 'seq_write.fio')
    config.write_text('#!/bin/bash\n"$FAKE_PRODUCER"\n')
    mount = tmp_path / 'mount'
    mount.mkdir()
    harness = f'''
export DTT_ENTRYPOINT_SOURCE_ONLY=1
source {shlex.quote(str(ROOT / 'entrypoint.sh'))}
set -e
FIO_BIN="$FAKE_PRODUCER"
MOUNT={shlex.quote(str(mount))}
OUTPUT={shlex.quote(str(tmp_path / 'output'))}
SCENARIO={'perf' if runner == 'perf' else 'fs' if runner == 'ltp' else 'seq_write'}
RUN_TIMESTAMP=regression
WECHAT_ENABLED=no
EMAIL_ENABLED=no
SMOKE_MODE=1
get_scenario_paths() {{ printf '%s\\n' {shlex.quote(str(config))}; }}
python3() {{ printf 'REPORT_GENERATED\\n'; }}
log_result() {{ printf 'RECORDED_STATUS=%s\\n' "$3"; }}
# Never access an installed LTP tree: dispatch its timeout boundary locally.
timeout() {{ [[ "$1" == 3600 && "$2" == /opt/ltp/runltp ]] || return 99; "$FAKE_PRODUCER"; }}
rm() {{ :; }}
tee() {{ command tee "$@"; return "$TEE_STATUS"; }}
{'ltp_run' if runner == 'ltp' else 'fio_run'}
'''
    try:
        result = subprocess.run(['bash', '-c', harness], text=True, capture_output=True,
                                env=dict(os.environ, FAKE_PRODUCER=str(producer),
                                         PRODUCER_STATUS=str(producer_status),
                                         TEE_STATUS=str(tee_status)))
    finally:
        if runner == 'perf':
            (Path('/tmp') / config.name).unlink(missing_ok=True)
    expected = producer_status or tee_status
    assert result.returncode == expected, result.stdout + result.stderr
    assert f'RECORDED_STATUS={expected}' in result.stdout
    if runner != 'ltp':
        assert 'REPORT_GENERATED' in result.stdout
    elif expected == 124:
        assert 'timed out' in result.stdout
