from pathlib import Path
import shlex
import stat
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SmokeAiAnalysisTest(unittest.TestCase):
    def _run_smoke(self, *, runtime_exit=0, analyzer_exit=0, debug=False):
        wrapper = ROOT / "dingofs-testsuite-tool"
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        temp = Path(temp_dir.name)
        config = temp / "config"
        mount = temp / "mount"
        output = temp / "output"
        reports = temp / "reports"
        for path in (config, mount, output, reports):
            path.mkdir()

        events = temp / "events"
        runtime_args = temp / "runtime-args"
        analyzer_args = temp / "analyzer-args"
        runtime = temp / "fake-runtime"
        runtime.write_text(
            "#!/bin/bash\n"
            f"printf '%s\\n' \"$@\" > {shlex.quote(str(runtime_args))}\n"
            f"echo runtime >> {shlex.quote(str(events))}\n"
            "host_output=\n"
            "public_root=\n"
            "url_file=\n"
            "for argument in \"$@\"; do\n"
            "  case \"$argument\" in\n"
            "    *:/output) host_output=${argument%:/output} ;;\n"
            "    *:/dtt-smoke-report-public) public_root=${argument%:/dtt-smoke-report-public} ;;\n"
            "    DTT_SMOKE_REPORT_URL_FILE=/output/*) url_file=${argument#DTT_SMOKE_REPORT_URL_FILE=/output/} ;;\n"
            "  esac\n"
            "done\n"
            "if [[ -n \"$host_output\" && -n \"$public_root\" && -n \"$url_file\" ]]; then\n"
            "  mkdir -p \"$public_root/live/allure-smoke-report-latest\"\n"
            "  printf report > \"$public_root/live/allure-smoke-report-latest/index.html\"\n"
            "  mv \"$host_output/$url_file\" \"$host_output/$url_file.ready\"\n"
            "fi\n"
            f"exit {runtime_exit}\n",
            encoding="utf-8",
        )
        runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)

        analyzer = temp / "fake-analyzer"
        analyzer.write_text(
            "#!/bin/bash\n"
            f"printf '%s\\n' \"$@\" > {shlex.quote(str(analyzer_args))}\n"
            f"echo analyzer >> {shlex.quote(str(events))}\n"
            f"exit {analyzer_exit}\n",
            encoding="utf-8",
        )
        analyzer.chmod(analyzer.stat().st_mode | stat.S_IXUSR)

        (config / "image").write_text("test-image\n", encoding="utf-8")
        (config / "testdir").write_text(f"{mount}\n", encoding="utf-8")
        (config / "output").write_text(f"{output}\n", encoding="utf-8")
        (config / "runtime").write_text(f"{runtime}\n", encoding="utf-8")
        (config / "email").write_text("configured@example.com\n", encoding="utf-8")

        debug_arg = " --debug" if debug else ""
        smoke_args = (
            "--env env_127 --exclude pjdtest,ltp,xfstest "
            "--email daigy@zetyun.com --wechat --ai-analysis "
            f"--report-path {shlex.quote(str(reports))} --report-port 18889"
            f"{debug_arg}"
        )
        command = textwrap.dedent(
            f"""
            export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}
            export DTT_AI_ANALYZER={shlex.quote(str(analyzer))}
            source {shlex.quote(str(wrapper))}
            cmd_setup_env() {{ :; }}
            mountpoint() {{ return 0; }}
            _is_rootless() {{ return 0; }}
            hostname() {{ echo 192.0.2.10; }}
            start_smoke_report_server() {{ return 0; }}
            smoke_report_server_bound_host() {{ echo 192.0.2.10; }}
            cmd_smoke {smoke_args}
            """
        )
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )
        args = (
            runtime_args.read_text(encoding="utf-8").splitlines()
            if runtime_args.exists()
            else []
        )
        analyzer_call = (
            analyzer_args.read_text(encoding="utf-8").splitlines()
            if analyzer_args.exists()
            else []
        )
        event_list = (
            events.read_text(encoding="utf-8").splitlines()
            if events.exists()
            else []
        )
        return result, args, analyzer_call, event_list, config, reports

    def test_smoke_ai_accepts_public_options_and_finalizes_after_runtime(self):
        result, args, analyzer_call, events, config, reports = self._run_smoke()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(events, ["runtime", "analyzer"])
        for expected in (
            "DTT_AI_ENABLED=1",
            "DTT_DEFER_NOTIFICATIONS=yes",
            "DTT_AI_RUN_ID=",
            "DTT_AI_RUN_DIR=/output/.dtt-ai-work/",
            "DTT_AI_COMMAND=dtt smoke",
        ):
            self.assertTrue(any(expected in arg for arg in args), (expected, args))
        self.assertIn(
            str(config / "smoke-report-public" / "live" / "ai-analysis"),
            analyzer_call,
        )
        self.assertIn("--base-url", analyzer_call)
        self.assertIn("http://192.0.2.10:18889/ai-analysis", analyzer_call)
        self.assertIn(f"{reports}:/output", args)

    def test_smoke_ai_preserves_failed_suite_exit_when_analysis_fails(self):
        result, _args, analyzer_call, events, _config, _reports = self._run_smoke(
            runtime_exit=7, analyzer_exit=4
        )

        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertTrue(analyzer_call)
        self.assertEqual(events, ["runtime", "analyzer"])

    def test_smoke_debug_accepts_ai_analysis(self):
        result, args, analyzer_call, events, _config, _reports = self._run_smoke(
            debug=True
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("--rm", args)
        self.assertTrue(analyzer_call)
        self.assertEqual(events, ["runtime", "analyzer"])

    def test_smoke_help_documents_ai_analysis(self):
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"source {shlex.quote(str(ROOT / 'dingofs-testsuite-tool'))}; show_smoke_help",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--ai-analysis", result.stdout)


if __name__ == "__main__":
    unittest.main()
