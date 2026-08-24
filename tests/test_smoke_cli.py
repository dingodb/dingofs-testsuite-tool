from pathlib import Path
import shlex
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SmokeCliTest(unittest.TestCase):
    def _run_smoke(self, smoke_args, *, runtime_exit=0):
        wrapper = ROOT / "dingofs-testsuite-tool"
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        temp = Path(temp_dir.name)
        config = temp / "config"
        mount = temp / "mount"
        configured_output = temp / "configured-output"
        report_path = temp / "reports"
        fake_bin = temp / "bin"
        for path in (config, mount, configured_output, fake_bin):
            path.mkdir()

        runtime_args = temp / "runtime-args"
        runtime = temp / "fake-runtime"
        runtime.write_text(
            "#!/bin/bash\n"
            f"printf '%s\\n' \"$@\" > {runtime_args}\n"
            f"exit {runtime_exit}\n",
            encoding="utf-8",
        )
        runtime.chmod(0o755)

        nohup_args = temp / "nohup-args"
        fake_nohup = fake_bin / "nohup"
        fake_nohup.write_text(
            f"#!/bin/bash\nprintf '%s\\n' \"$@\" > {nohup_args}\n",
            encoding="utf-8",
        )
        fake_nohup.chmod(0o755)

        (config / "image").write_text("test-image\n", encoding="utf-8")
        (config / "testdir").write_text(f"{mount}\n", encoding="utf-8")
        (config / "output").write_text(
            f"{configured_output}\n", encoding="utf-8"
        )
        (config / "runtime").write_text(f"{runtime}\n", encoding="utf-8")
        (config / "email").write_text("configured@example.com\n", encoding="utf-8")
        smoke_args = smoke_args.replace(
            "__REPORT_PATH__", shlex.quote(str(report_path))
        )

        command = textwrap.dedent(
            f"""
            export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}
            export PATH={shlex.quote(str(fake_bin))}:$PATH
            source {shlex.quote(str(wrapper))}
            cmd_setup_env() {{ :; }}
            mountpoint() {{ return 0; }}
            _is_rootless() {{ return 0; }}
            pgrep() {{ return 1; }}
            set +e
            cmd_smoke {smoke_args}
            smoke_rc=$?
            set -e
            exit "$smoke_rc"
            """
        )
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )
        docker_args = (
            runtime_args.read_text(encoding="utf-8").splitlines()
            if runtime_args.exists()
            else []
        )
        server_args = (
            nohup_args.read_text(encoding="utf-8").splitlines()
            if nohup_args.exists()
            else []
        )
        return result, docker_args, server_args, configured_output, report_path

    def test_smoke_accepts_email_address_wechat_and_report_path(self):
        result, args, _, configured_output, report_path = self._run_smoke(
            "--exclude pjdtest,ltp,xfstest "
            "--email daigy@zetyun.com --wechat "
            f"--report-path {report_path_placeholder()}"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("EMAIL=yes", args)
        self.assertIn("EMAIL_TO=daigy@zetyun.com", args)
        self.assertIn("WECHAT=yes", args)
        self.assertIn(f"{report_path}:/output", args)
        self.assertNotIn(f"{configured_output}:/output", args)

    def test_smoke_report_server_preserves_failed_suite_exit(self):
        result, _, server_args, _, report_path = self._run_smoke(
            "--exclude pjdtest,ltp,xfstest "
            f"--report-path {report_path_placeholder()} --report-port 18889",
            runtime_exit=7,
        )

        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertEqual(
            server_args,
            ["python3", "-m", "http.server", "18889", "--directory", str(report_path)],
        )
        self.assertIn(":18889/", result.stdout + result.stderr)


def report_path_placeholder():
    return "__REPORT_PATH__"


if __name__ == "__main__":
    unittest.main()
