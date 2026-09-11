import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "dingofs-testsuite-tool"


class AiCliTest(unittest.TestCase):
    def _run_bash(self, body, env=None):
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            ["bash", "-c", "source %s; %s" % (WRAPPER, body)],
            text=True,
            capture_output=True,
            env=merged,
            check=False,
        )

    def test_new_run_id_has_timestamp_and_random_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self._run_bash(
                "new_ai_run_id; new_ai_run_id",
                {"DINGOFS_TESTSUITE_CONFIG_DIR": str(Path(temp_dir) / "config")},
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        values = result.stdout.splitlines()
        self.assertEqual(len(values), 2)
        for value in values:
            self.assertRegex(value, r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")
        self.assertNotEqual(values[0], values[1])

    def test_prepare_ai_run_creates_private_directory_and_exports_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "reports"
            result = self._run_bash(
                "prepare_ai_run %s tool 'dtt -t fio -s seq_read --ai-analysis'; "
                "stat -c '%%a' \"$DTT_AI_HOST_RUN_DIR\"; "
                "printf '%%s\\n%%s\\n%%s\\n' \"$DTT_AI_RUN_ID\" \"$DTT_AI_MODE\" \"$DTT_AI_COMMAND\""
                % root,
                {"DINGOFS_TESTSUITE_CONFIG_DIR": str(Path(temp_dir) / "config")},
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], "700")
        self.assertRegex(lines[1], r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")
        self.assertEqual(lines[2:], ["tool", "dtt -t fio -s seq_read --ai-analysis"])

    def test_finalize_ai_run_never_leaks_analyzer_exit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            analyzer = temp / "fake-analyzer"
            analyzer.write_text("#!/bin/bash\nexit 4\n", encoding="utf-8")
            analyzer.chmod(analyzer.stat().st_mode | stat.S_IXUSR)
            report_root = temp / "reports"
            result = self._run_bash(
                "prepare_ai_run %s tool 'dtt -t vdbench -s stability --ai-analysis'; "
                "run_dir=\"$DTT_AI_HOST_RUN_DIR\"; "
                "finalize_ai_run \"$run_dir\" %s/ai-analysis '' '' '' ''; "
                "status=$?; test ! -e \"$run_dir\"; printf 'final=%%s\\n' \"$status\""
                % (report_root, report_root),
                {
                    "DINGOFS_TESTSUITE_CONFIG_DIR": str(temp / "config"),
                    "DTT_AI_ANALYZER": str(analyzer),
                },
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("final=0", result.stdout)

    def test_debug_ai_analysis_is_rejected_before_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            config.mkdir()
            marker = temp / "runtime-called"
            runtime = temp / "fake-runtime"
            runtime.write_text("#!/bin/bash\ntouch \"$RUNTIME_MARKER\"\n", encoding="utf-8")
            runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)
            (config / "runtime").write_text(str(runtime), encoding="utf-8")
            (config / "image").write_text("fake-image", encoding="utf-8")

            result = subprocess.run(
                [str(WRAPPER), "debug", "--ai-analysis"],
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "DINGOFS_TESTSUITE_CONFIG_DIR": str(config),
                    "RUNTIME_MARKER": str(marker),
                },
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("does not run a test", result.stdout + result.stderr)
        self.assertFalse(marker.exists())

    def test_top_level_help_mentions_ai_analysis(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [str(WRAPPER), "--help"],
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "DINGOFS_TESTSUITE_CONFIG_DIR": str(Path(temp_dir) / "config"),
                },
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--ai-analysis", result.stdout)

    def test_installer_installs_wrapper_analyzer_and_schema_together(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            home = temp / "home"
            install_bin = home / ".local" / "bin"
            install_bin.mkdir(parents=True)
            fake_bin = temp / "fake-bin"
            fake_bin.mkdir()
            docker = fake_bin / "docker"
            docker.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
            docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
            curl = fake_bin / "curl"
            curl.write_text(
                "#!/bin/bash\n"
                "url=''\nout=''\n"
                "while [[ $# -gt 0 ]]; do\n"
                "  case \"$1\" in\n"
                "    -o) out=\"$2\"; shift 2 ;;\n"
                "    http*) url=\"$1\"; shift ;;\n"
                "    *) shift ;;\n"
                "  esac\n"
                "done\n"
                "name=\"${url##*/}\"\n"
                "cp \"$INSTALL_SOURCE_ROOT/$name\" \"$out\"\n",
                encoding="utf-8",
            )
            curl.chmod(curl.stat().st_mode | stat.S_IXUSR)
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "PATH": "%s:%s:%s" % (fake_bin, install_bin, env["PATH"]),
                    "INSTALL_SOURCE_ROOT": str(ROOT),
                    "DINGOFS_TESTSUITE_CONFIG_DIR": str(home / ".dingofs_testsuite"),
                }
            )

            result = subprocess.run(
                ["bash", str(ROOT / "install.sh"), "--no-pull"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((install_bin / "dingofs-testsuite-tool").is_file())
            self.assertTrue(os.access(install_bin / "dingofs-testsuite-tool", os.X_OK))
            self.assertTrue((install_bin / "dtt-ai-analyze").is_file())
            self.assertTrue(os.access(install_bin / "dtt-ai-analyze", os.X_OK))
            schema = home / ".local" / "lib" / "dingofs-testsuite-tool" / "analysis.schema.json"
            self.assertTrue(schema.is_file())


if __name__ == "__main__":
    unittest.main()
