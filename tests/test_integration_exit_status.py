"""The integration log tee must preserve Python failures for platform callers."""
from pathlib import Path
import subprocess
import pytest

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
