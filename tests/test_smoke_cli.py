from pathlib import Path
import shlex
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SmokeCliTest(unittest.TestCase):
    def _run_smoke(
        self,
        smoke_args,
        *,
        runtime_exit=0,
        report_server_exit=0,
        publish_public_report=True,
    ):
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
        public_report_script = (
            "  mkdir -p \"$public_root/live/allure-smoke-report-latest\"\n"
            "  printf 'report' > \"$public_root/live/"
            "allure-smoke-report-latest/index.html\"\n"
            if publish_public_report
            else ""
        )
        runtime.write_text(
            "#!/bin/bash\n"
            f"printf '%s\\n' \"$@\" > {runtime_args}\n"
            "host_output=\n"
            "public_root=\n"
            "url_file=\n"
            "for argument in \"$@\"; do\n"
            "  case \"$argument\" in\n"
            "    *:/output) host_output=${argument%:/output} ;;\n"
            "    *:/dtt-smoke-report-public) "
            "public_root=${argument%:/dtt-smoke-report-public} ;;\n"
            "    DTT_SMOKE_REPORT_URL_FILE=/output/*) "
            "url_file=${argument#DTT_SMOKE_REPORT_URL_FILE=/output/} ;;\n"
            "  esac\n"
            "done\n"
            "if [[ -n \"$host_output\" && -n \"$public_root\" && "
            "-n \"$url_file\" && "
            "-f \"$host_output/$url_file\" ]]; then\n"
            + public_report_script
            + "  mv \"$host_output/$url_file\" \"$host_output/$url_file.ready\"\n"
            + "fi\n"
            + f"exit {runtime_exit}\n",
            encoding="utf-8",
        )
        runtime.chmod(0o755)

        server_args_file = temp / "server-args"

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
            hostname() {{ echo "192.0.2.10"; }}
            start_smoke_report_server() {{
                printf '%s\n' "$@" > {shlex.quote(str(server_args_file))}
                return {report_server_exit}
            }}
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
        self.last_config_dir = config
        docker_args = (
            runtime_args.read_text(encoding="utf-8").splitlines()
            if runtime_args.exists()
            else []
        )
        server_args = (
            server_args_file.read_text(encoding="utf-8").splitlines()
            if server_args_file.exists()
            else []
        )
        return result, docker_args, server_args, configured_output, report_path

    def test_smoke_accepts_email_address_wechat_and_report_path(self):
        result, args, server_args, configured_output, report_path = self._run_smoke(
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
        self.assertEqual(
            server_args,
            [
                str(self.last_config_dir / "smoke-report-public" / "live"),
                "8888",
                "192.0.2.10",
            ],
        )
        self.assertIn(
            f"{self.last_config_dir / 'smoke-report-public'}:"
            "/dtt-smoke-report-public",
            args,
        )

    def test_smoke_defaults_to_browsable_allure_report_on_port_8888(self):
        result, args, server_args, configured_output, _ = self._run_smoke(
            "--exclude pjdtest,ltp,xfstest,int_client,int_cache_node --email"
        )

        expected_url = (
            "http://192.0.2.10:8888/"
            "allure-smoke-report-latest/index.html"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(f"SMOKE_REPORT_URL={expected_url}", args)
        self.assertTrue(
            any(arg.startswith("DTT_SMOKE_REPORT_URL_FILE=/output/") for arg in args)
        )
        self.assertEqual(
            server_args,
            [
                str(self.last_config_dir / "smoke-report-public" / "live"),
                "8888",
                "192.0.2.10",
            ],
        )
        self.assertIn(f"Smoke Allure report: {expected_url}", result.stdout + result.stderr)

    def test_smoke_report_server_preserves_failed_suite_exit(self):
        result, _, server_args, _, report_path = self._run_smoke(
            "--exclude pjdtest,ltp,xfstest "
            f"--report-path {report_path_placeholder()} --report-port 18889",
            runtime_exit=7,
        )

        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertEqual(
            server_args,
            [
                str(self.last_config_dir / "smoke-report-public" / "live"),
                "18889",
                "192.0.2.10",
            ],
        )
        self.assertIn(
            "Smoke Allure report: http://192.0.2.10:18889/"
            "allure-smoke-report-latest/index.html",
            result.stdout + result.stderr,
        )

    def test_smoke_report_server_failure_omits_link_and_preserves_suite_exit(self):
        result, args, server_args, configured_output, _ = self._run_smoke(
            "--exclude pjdtest,ltp,xfstest --email",
            runtime_exit=7,
            report_server_exit=1,
        )

        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertEqual(
            server_args,
            [
                str(self.last_config_dir / "smoke-report-public" / "live"),
                "8888",
                "192.0.2.10",
            ],
        )
        self.assertFalse(
            any(arg.startswith("SMOKE_REPORT_URL=") for arg in args), args
        )
        self.assertFalse(
            any(arg.startswith("DTT_SMOKE_REPORT_URL_FILE=") for arg in args), args
        )
        self.assertIn(
            "Smoke Allure report service is unavailable",
            result.stdout + result.stderr,
        )

    def test_ready_marker_without_public_report_does_not_print_link(self):
        result, _, _, _, _ = self._run_smoke(
            "--exclude pjdtest,ltp,xfstest",
            publish_public_report=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("  Smoke Allure report: http://", result.stdout + result.stderr)
        self.assertIn(
            "Smoke Allure report was not published",
            result.stdout + result.stderr,
        )


def report_path_placeholder():
    return "__REPORT_PATH__"


if __name__ == "__main__":
    unittest.main()
