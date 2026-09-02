from pathlib import Path
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import unittest


ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for_url(url, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                return response.read().decode("utf-8")
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"URL did not become ready: {url}")


class SmokeReportServerTest(unittest.TestCase):
    def test_owned_server_is_ready_before_start_returns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            output = temp / "output"
            report = output / "allure-smoke-report-latest"
            report.mkdir(parents=True)
            (report / "index.html").write_text("current smoke report", encoding="utf-8")
            port = free_port()
            command = (
                f"export DINGOFS_TESTSUITE_CONFIG_DIR={config}; "
                f"source {ROOT / 'dingofs-testsuite-tool'}; "
                f"start_smoke_report_server {output} {port} 127.0.0.1"
            )
            result = subprocess.run(
                ["bash", "-c", command], text=True, capture_output=True, check=False
            )
            state_file = config / "smoke-report-servers" / f"{port}.state"
            pid = int(state_file.read_text(encoding="utf-8").splitlines()[0])
            self.addCleanup(self._terminate, pid)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                wait_for_url(
                    f"http://127.0.0.1:{port}/allure-smoke-report-latest/index.html"
                ),
                "current smoke report",
            )

            changed_bind_command = command.replace(
                " 127.0.0.1", " 127.0.0.2"
            )
            second = subprocess.run(
                ["bash", "-c", changed_bind_command],
                text=True,
                capture_output=True,
                check=False,
            )
            reused_pid = int(state_file.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(reused_pid, pid)

    def test_unknown_listener_is_not_killed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            other_output = temp / "other-output"
            requested_output = temp / "requested-output"
            config = temp / "config"
            other_output.mkdir()
            requested_output.mkdir()
            (other_output / "owner.txt").write_text("unrelated", encoding="utf-8")
            port = free_port()
            listener = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "http.server",
                    str(port),
                    "--bind",
                    "127.0.0.1",
                    "--directory",
                    str(other_output),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.addCleanup(self._terminate_process, listener)
            wait_for_url(f"http://127.0.0.1:{port}/owner.txt")

            command = (
                f"export DINGOFS_TESTSUITE_CONFIG_DIR={config}; "
                f"source {ROOT / 'dingofs-testsuite-tool'}; "
                "set +e; "
                f"start_smoke_report_server {requested_output} {port} 127.0.0.1; "
                "rc=$?; set -e; echo start_rc=$rc; exit 0"
            )
            result = subprocess.run(
                ["bash", "-c", command], text=True, capture_output=True, check=False
            )

            self.assertIn("start_rc=1", result.stdout + result.stderr)
            self.assertIsNone(listener.poll())
            self.assertEqual(
                wait_for_url(f"http://127.0.0.1:{port}/owner.txt"), "unrelated"
            )

    @staticmethod
    def _terminate(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    @staticmethod
    def _terminate_process(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


if __name__ == "__main__":
    unittest.main()
