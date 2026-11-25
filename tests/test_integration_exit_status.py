"""The integration log tee must preserve Python failures for platform callers."""
from pathlib import Path
import subprocess
import pytest
import json
import os


@pytest.mark.parametrize('code,status', [(0, 'SUCCESS'), (7, 'FAIL')])
def test_guided_summary_uses_final_suite_counts_and_process_exit(tmp_path, code, status):
    (tmp_path/'functional-events.jsonl').write_text(json.dumps({'version':2,'seq':1,'type':'suite_finished',
        'module':'quota','data':{'total':1,'passed':1,'failed':0,'completed':1,'skipped':0,'known_bugs':0,
        'suite_errors':0,'status':'completed'}})+'\n')
    result = run_summary(tmp_path, code, 'case finished successfully', guided=True)
    assert result.returncode == 0, result.stderr
    assert 'Total: 1' in result.stdout and 'Passed: 1' in result.stdout
    assert f'STATUS={status}' in result.stdout


@pytest.mark.parametrize('code,status', [(0,'SUCCESS'), (7,'FAIL')])
def test_text_suite_summary_never_overrides_process_failure(tmp_path, code, status):
    result = run_summary(tmp_path, code, 'TEST SUITE SUMMARY\nTotal Cases: 2\nPassed: 2\nFailed: 0\nSuite Errors: 0\n')
    assert 'Total: 2' in result.stdout and f'STATUS={status}' in result.stdout


def test_missing_counts_are_unknown_not_zero_failed_tests(tmp_path):
    result = run_summary(tmp_path, 0, 'unrecognized output')
    assert 'Total: unknown' in result.stdout
    assert 'STATUS=UNKNOWN' in result.stdout


def test_corrupt_guided_events_do_not_fall_back_to_successful_text(tmp_path):
    (tmp_path/'functional-events.jsonl').write_text('{broken\n')
    result = run_summary(tmp_path, 0, '  quota: 1 passed, 0 failed', guided=True)
    assert 'Total: unknown' in result.stdout and 'STATUS=UNKNOWN' in result.stdout


@pytest.mark.parametrize('log,total,passed,failed,status', [
    ('  quota: 2 passed, 0 failed\n  basic: 3 passed, 1 failed',6,5,1,'FAIL'),
    ('======= 2 passed, 1 skipped in 0.20s =======',3,2,0,'SUCCESS'),
    ('======= 2 passed, 1 error in 0.20s =======',3,2,0,'FAIL'),
    ('TEST SUITE SUMMARY\nTotal Cases: 1\nPassed: 1\nFailed: 0\nSuite Errors: 1\n',1,1,0,'FAIL'),
])
def test_summary_legacy_and_suite_error_paths(tmp_path, log, total, passed, failed, status):
    result = run_summary(tmp_path, 0, log)
    assert f'Total: {total}' in result.stdout
    assert f'Passed: {passed}' in result.stdout
    assert f'Failed: {failed}' in result.stdout
    assert f'STATUS={status}' in result.stdout


def run_summary(tmp_path, code, log, guided=False):
    root = Path(__file__).resolve().parents[1]
    source = (root/'entrypoint.sh').read_text()
    start = source.index('    # Parse test results from the log output.')
    end = source.index('    echo "Integration tests completed with exit code:',start)
    logfile = tmp_path/'run.log'
    logfile.write_text(log)
    script = 'run() {\nlocal log_file="$1" exit_code="$2" failed_tests=""\n' + source[start:end] + '\necho "STATUS=$status"\n}\nrun "$1" "$2"'
    return subprocess.run(['bash','-c',script,'test',str(logfile),str(code)],capture_output=True,text=True,
        env={**os.environ,'OUTPUT':str(tmp_path),'INT_CASE_PLAN':'plan.json' if guided else '',
             'DTT_INTEGRATION_SUMMARY':str(root/'scripts/integration_summary.py')})

@pytest.mark.parametrize('code', [0, 1, 7])
def test_integration_pipeline_preserves_python_exit(tmp_path, code):
    source=(Path(__file__).resolve().parents[1]/'entrypoint.sh').read_text()
    start=source.index('\n',source.index('echo "Executing: ${cmd[*]}"'))+1
    end=source.index('\n    # Accumulate allure reports',start)
    segment=source[start:end]
    script='run() {\nlocal cmd=(bash -c "exit '+str(code)+'")\nlocal log_file="$1"\n'+segment+'\nreturn "$exit_code"\n}\nrun "$1"\n'
    result=subprocess.run(['bash','-c',script,'test',str(tmp_path/'run.log')],capture_output=True,text=True)
    assert result.returncode==code

@pytest.mark.parametrize('code', [1, 7])
def test_failed_run_still_reaches_report_generation_with_errexit(tmp_path, code):
    source=(Path(__file__).resolve().parents[1]/'entrypoint.sh').read_text()
    start=source.index('\n',source.index('echo "Executing: ${cmd[*]}"'))+1
    end=source.index('\n    # Accumulate allure reports',start)
    segment=source[start:end]
    script='set -e\nrun() {\nlocal cmd=(bash -c "exit '+str(code)+'")\nlocal log_file="$1"\n'+segment+'\nprintf report-ready > "$1.report"\nreturn "$exit_code"\n}\nrun "$1"\n'
    result=subprocess.run(['bash','-c',script,'test',str(tmp_path/'run.log')],capture_output=True,text=True)
    assert (tmp_path/'run.log.report').read_text()=='report-ready'
    assert result.returncode==code
