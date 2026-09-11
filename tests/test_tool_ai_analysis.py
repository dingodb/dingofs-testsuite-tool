from pathlib import Path
import shlex
import stat
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ToolAiAnalysisTest(unittest.TestCase):
    TOOL_CASES = (
        ("fio", "seq_read"),
        ("vdbench", "seq_rd"),
        ("mdtest", "all"),
        ("pjdtest", "all"),
        ("ltp", "smoke"),
        ("int", "quota"),
        ("mlperf", "resnet50"),
        ("xfstest", "quick"),
        ("task", "sample"),
        ("elbencho", "small"),
    )

    def _run_tool(self, tool, scenario, *, runtime_exit=6, extra_args="", rootless=False):
        wrapper = ROOT / "dingofs-testsuite-tool"
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        temp = Path(temp_dir.name)
        config = temp / "config"
        mount = temp / "mount"
        output = temp / "output"
        for path in (config, mount, output):
            path.mkdir()

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
            "exit 4\n",
            encoding="utf-8",
        )
        analyzer.chmod(analyzer.stat().st_mode | stat.S_IXUSR)

        (config / "image").write_text("test-image\n", encoding="utf-8")
        (config / "testdir").write_text(f"{mount}\n", encoding="utf-8")
        (config / "output").write_text(f"{output}\n", encoding="utf-8")
        (config / "runtime").write_text(f"{runtime}\n", encoding="utf-8")
        (config / "int_env").write_text("env_126_smoke\n", encoding="utf-8")

        command = textwrap.dedent(
            f"""
            export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}
            export DTT_AI_ANALYZER={shlex.quote(str(analyzer))}
            source {shlex.quote(str(wrapper))}
            _is_rootless() {{ {'true' if rootless else 'false'}; }}
            run_testsuite -t {shlex.quote(tool)} -s {shlex.quote(scenario)} \
                --ai-analysis {extra_args}
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
        return result, args, analyzer_call, event_list, output

    def test_each_one_shot_tool_passes_ai_metadata_and_preserves_exit(self):
        for tool, scenario in self.TOOL_CASES:
            with self.subTest(tool=tool):
                result, args, analyzer_call, events, output = self._run_tool(
                    tool, scenario
                )
                self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
                self.assertEqual(events, ["runtime", "analyzer"])
                for expected in (
                    "DTT_AI_ENABLED=1",
                    "DTT_DEFER_NOTIFICATIONS=yes",
                    "DTT_AI_RUN_DIR=/output/.dtt-ai-work/",
                    "DTT_AI_COMMAND=dtt -t",
                ):
                    self.assertTrue(
                        any(expected in arg for arg in args),
                        (tool, expected, args),
                    )
                self.assertIn("--mode", args)
                self.assertIn("one-shot", args)
                self.assertIn(str(output / "ai-analysis"), analyzer_call)

    def test_rootless_tool_uses_container_root_as_bundle_owner(self):
        result, args, _call, _events, _output = self._run_tool("fio", "seq_read", rootless=True)
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("DTT_AI_OUTPUT_OWNER=0:0", args)

    def test_long_running_ai_is_rejected_before_runtime(self):
        result, args, analyzer_call, events, _output = self._run_tool(
            "fio", "seq_read", extra_args="--mode long-running"
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(args, [])
        self.assertEqual(analyzer_call, [])
        self.assertEqual(events, [])
        self.assertIn(
            "--ai-analysis is supported only with --mode one-shot",
            result.stdout + result.stderr,
        )

    def test_invalid_mode_is_rejected_before_runtime(self):
        result, args, _analyzer_call, events, _output = self._run_tool(
            "fio", "seq_read", extra_args="--mode invalid"
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(args, [])
        self.assertEqual(events, [])
        self.assertIn("Invalid --mode", result.stdout + result.stderr)

    def test_entrypoint_exporter_runs_once_and_preserves_exit(self):
        entrypoint = ROOT / "entrypoint.sh"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            output = temp / "output"
            run_dir = output / ".dtt-ai-work" / "20260911-210000-ab12cd"
            output.mkdir()
            calls = temp / "exporter-calls"
            exporter = temp / "fake-exporter"
            exporter.write_text(
                "import pathlib\n"
                "import sys\n"
                f"path = pathlib.Path({str(calls)!r})\n"
                "path.write_text('call\\n' + '\\n'.join(sys.argv[1:]) + '\\n', encoding='utf-8')\n",
                encoding="utf-8",
            )
            command = textwrap.dedent(
                f"""
                export DTT_AI_ENABLED=1
                export DTT_AI_RUN_ID=20260911-210000-ab12cd
                export DTT_AI_RUN_DIR={shlex.quote(str(run_dir))}
                export DTT_AI_COMMAND='dtt -t fio -s seq_read --ai-analysis'
                export DTT_AI_EXPORTER={shlex.quote(str(exporter))}
                export DTT_ENTRYPOINT_SOURCE_ONLY=1
                source {shlex.quote(str(entrypoint))}
                TOOL=fio
                SCENARIO=seq_read
                OUTPUT={shlex.quote(str(output))}
                MODE=one-shot
                setup_ai_export
                false
                """
            )
            result = subprocess.run(
                ["bash", "-c", command], text=True, capture_output=True, check=False
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(
                calls.read_text(encoding="utf-8").splitlines().count("call"), 1
            )
            exported = calls.read_text(encoding="utf-8")
            self.assertIn("--exit-code\n1", exported)
            self.assertIn("--artifact-list", exported)
            self.assertTrue((run_dir / "execution.raw.log").exists())

    def test_entrypoint_registers_only_artifacts_below_output(self):
        entrypoint = ROOT / "entrypoint.sh"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            output = temp / "output"
            run_dir = output / ".dtt-ai-work" / "20260911-210000-ab12cd"
            inside = output / "fio_run"
            outside = temp / "outside"
            for path in (run_dir, inside, outside):
                path.mkdir(parents=True, exist_ok=True)
            command = textwrap.dedent(
                f"""
                export DTT_ENTRYPOINT_SOURCE_ONLY=1
                source {shlex.quote(str(entrypoint))}
                OUTPUT={shlex.quote(str(output))}
                DTT_AI_ENABLED=1
                DTT_AI_RUN_DIR={shlex.quote(str(run_dir))}
                register_ai_artifact {shlex.quote(str(inside))}
                register_ai_artifact {shlex.quote(str(outside))} || true
                """
            )
            result = subprocess.run(
                ["bash", "-c", command], text=True, capture_output=True, check=False
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            artifacts = (run_dir / "artifacts.list").read_text(encoding="utf-8")
            self.assertIn(str(inside), artifacts)
            self.assertNotIn(str(outside), artifacts)

    def test_entrypoint_actual_exporter_captures_final_log_and_exit(self):
        import json
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            output = temp / "output"
            output.mkdir()
            run_id = "20260911-210000-ab12cd"
            run_dir = output / ".dtt-ai-work" / run_id
            script = textwrap.dedent(f"""
                export DTT_ENTRYPOINT_SOURCE_ONLY=1
                source {shlex.quote(str(ROOT / 'entrypoint.sh'))}
                TOOL=vdbench SCENARIO=stability MODE=one-shot
                OUTPUT={shlex.quote(str(output))}
                DTT_AI_ENABLED=1 DTT_AI_RUN_ID={run_id}
                DTT_AI_RUN_DIR={shlex.quote(str(run_dir))}
                DTT_AI_COMMAND='dtt -t vdbench -s stability --ai-analysis'
                AI_EXPORTER={shlex.quote(str(ROOT / 'dingofs-integration-test/scripts/export_ai_run.py'))}
                setup_ai_export
                for ((i=0; i<4000; i++)); do echo progress; done
                echo 'fatal: late corruption password=hidden-value'
                exit 6
            """)
            result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 6, result.stderr)
            manifest = json.loads((run_dir / "run_manifest.json").read_text())
            evidence = json.loads((run_dir / "evidence.json").read_text())
            self.assertEqual(manifest["exit_code"], 6)
            self.assertIn("late corruption", json.dumps(evidence))
            self.assertNotIn("hidden-value", json.dumps(evidence))
            self.assertFalse((run_dir / "execution.raw.log").exists())


if __name__ == "__main__":
    unittest.main()
