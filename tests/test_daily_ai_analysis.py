from pathlib import Path
import os
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
        rootless=False,
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
            _is_rootless() {{ {'true' if rootless else 'false'}; }}
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

    def test_daily_root_container_returns_private_bundle_to_host_user(self):
        _result, args, _analyzer, _events, reports = self._run_daily()
        self.assertIn("DTT_AI_OUTPUT_OWNER=%s:%s" % (os.getuid(), os.getgid()), args)
        self.assertTrue((reports / "ai-analysis").is_dir())
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            run_dir = temp / "run"
            run_dir.mkdir()
            bundle = run_dir / "run_manifest.json"
            bundle.write_text("{}", encoding="utf-8")
            recorded = temp / "ownership-args"
            fake_bin = temp / "bin"
            fake_bin.mkdir()
            for name, body in {
                "id": "echo 0",
                "python3": "exit 7",
                "chown": "printf '%s\\n' \"$@\" > \"$OWNERSHIP_ARGS\"",
            }.items():
                path = fake_bin / name
                path.write_text("#!/bin/bash\n" + body + "\n", encoding="utf-8")
                path.chmod(0o755)
            command = args[-1].replace("cd /dingofs-integration-test", "cd " + shlex.quote(str(temp)))
            completed = subprocess.run(
                ["bash", "-c", command], capture_output=True, text=True,
                env={**os.environ, "PATH": str(fake_bin) + ":" + os.environ["PATH"],
                     "DTT_AI_RUN_DIR": str(run_dir), "DTT_AI_OUTPUT_OWNER": "123:456",
                     "OWNERSHIP_ARGS": str(recorded)},
            )
            self.assertEqual(completed.returncode, 7, completed.stdout + completed.stderr)
            self.assertEqual(recorded.read_text().splitlines(), ["123:456", str(run_dir), str(bundle)])

    def test_daily_ai_all_pass_keeps_zero_when_analyzer_skips(self):
        result, _args, analyzer_call, events, _reports = self._run_daily(
            runtime_exit=0, analyzer_exit=3
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(analyzer_call)
        self.assertEqual(events, ["runtime", "analyzer"])

    def test_rootless_daily_uses_container_root_as_bundle_owner(self):
        result, args, _call, _events, _reports = self._run_daily(rootless=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DTT_AI_OUTPUT_OWNER=0:0", args)

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
