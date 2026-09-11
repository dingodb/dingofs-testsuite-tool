from pathlib import Path
import shlex
import stat
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DailyAiAnalysisTest(unittest.TestCase):
    def _run_daily(
        self,
        *,
        runtime_exit=0,
        analyzer_exit=0,
        extra_args="--include fault",
    ):
        wrapper = ROOT / "dingofs-testsuite-tool"
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        temp = Path(temp_dir.name)
        home = temp / "home"
        config = temp / "config"
        output = temp / "output"
        reports = temp / "reports"
        for path in (home, config, output, reports):
            path.mkdir()

        identity = home / ".ssh" / "rocky_70"
        identity.parent.mkdir()
        identity.write_text("test-private-key\n", encoding="utf-8")

        events = temp / "events"
        runtime_args = temp / "runtime-args"
        analyzer_args = temp / "analyzer-args"
        runtime = temp / "fake-runtime"
        runtime.write_text(
            "#!/bin/bash\n"
            f"printf '%s\\n' \"$@\" > {shlex.quote(str(runtime_args))}\n"
            f"echo runtime >> {shlex.quote(str(events))}\n"
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
        (config / "output").write_text(f"{output}\n", encoding="utf-8")
        (config / "runtime").write_text(f"{runtime}\n", encoding="utf-8")

        command = textwrap.dedent(
            f"""
            export HOME={shlex.quote(str(home))}
            export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}
            export DTT_AI_ANALYZER={shlex.quote(str(analyzer))}
            source {shlex.quote(str(wrapper))}
            prepare_chaos_tool_volume() {{ :; }}
            cmd_daily {extra_args} --ai-analysis \
                --report-path {shlex.quote(str(reports))} --report-port 8889
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
        return result, args, analyzer_call, event_list, reports

    def test_daily_ai_forwards_private_contract_and_finalizes_after_runtime(self):
        result, args, analyzer_call, events, reports = self._run_daily()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(events, ["runtime", "analyzer"])
        self.assertEqual(analyzer_call.count("--run-dir"), 1)
        self.assertIn(str(reports / "ai-analysis"), analyzer_call)
        self.assertIn("DTT_DEFER_NOTIFICATIONS=yes", args)
        command_tokens = shlex.split(args[-1])
        for option in (
            "--ai-run-id",
            "--ai-run-dir",
            "--ai-command",
            "--ai-mode",
            "--defer-notifications",
        ):
            self.assertIn(option, command_tokens)
        self.assertEqual(
            command_tokens[command_tokens.index("--ai-mode") + 1], "daily"
        )
        run_dir = command_tokens[command_tokens.index("--ai-run-dir") + 1]
        self.assertTrue(run_dir.startswith("/allure-report/.dtt-ai-work/"))

    def test_daily_ai_preserves_failed_test_exit_when_analysis_fails(self):
        result, _args, analyzer_call, events, _reports = self._run_daily(
            runtime_exit=9, analyzer_exit=4
        )

        self.assertEqual(result.returncode, 9, result.stdout + result.stderr)
        self.assertTrue(analyzer_call)
        self.assertEqual(events, ["runtime", "analyzer"])

    def test_daily_ai_all_pass_keeps_zero_when_analyzer_skips(self):
        result, _args, analyzer_call, events, _reports = self._run_daily(
            runtime_exit=0, analyzer_exit=3
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(analyzer_call)
        self.assertEqual(events, ["runtime", "analyzer"])

    def test_daily_debug_accepts_ai_analysis(self):
        result, args, analyzer_call, events, _reports = self._run_daily(
            extra_args="--debug"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("client", shlex.split(args[-1]))
        self.assertTrue(analyzer_call)
        self.assertEqual(events, ["runtime", "analyzer"])

    def test_daily_help_documents_ai_analysis(self):
        result = subprocess.run(
            ["bash", "-c", f"source {shlex.quote(str(ROOT / 'dingofs-testsuite-tool'))}; show_daily_help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--ai-analysis", result.stdout)


if __name__ == "__main__":
    unittest.main()
