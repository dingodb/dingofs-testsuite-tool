from pathlib import Path
import shlex
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DailyFaultTest(unittest.TestCase):
    def _run_daily(self, *, create_identity=True):
        wrapper = ROOT / "dingofs-testsuite-tool"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            home = temp / "home"
            config = temp / "config"
            output = temp / "output"
            home.mkdir()
            config.mkdir()
            output.mkdir()

            identity = home / ".ssh" / "rocky_70"
            if create_identity:
                identity.parent.mkdir()
                identity.write_text("test-private-key\n", encoding="utf-8")

            args_file = temp / "runtime-args"
            runtime = temp / "fake-runtime"
            runtime.write_text(
                f"#!/bin/bash\nprintf '%s\\n' \"$@\" > {args_file}\n",
                encoding="utf-8",
            )
            runtime.chmod(0o755)
            (config / "image").write_text("test-image\n", encoding="utf-8")
            (config / "output").write_text(f"{output}\n", encoding="utf-8")
            (config / "runtime").write_text(f"{runtime}\n", encoding="utf-8")

            command = textwrap.dedent(
                f"""
                export HOME={home}
                export DINGOFS_TESTSUITE_CONFIG_DIR={config}
                source {wrapper}
                cmd_daily
                """
            )
            result = subprocess.run(
                ["bash", "-c", command], text=True, capture_output=True, check=False
            )
            args = (
                args_file.read_text(encoding="utf-8").splitlines()
                if args_file.exists()
                else []
            )
            return result, args, identity

    def test_daily_runs_fault_with_external_chaos_paths(self):
        result, args, identity = self._run_daily()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"{identity}:/root/.ssh/rocky_70:ro", args)
        command_tokens = shlex.split(args[-1])
        fault_index = command_tokens.index("fault")
        self.assertEqual(
            command_tokens[fault_index:fault_index + 10],
            [
                "fault", "--env", "env_79_dingofs",
                "--chaos-tool-path", "/opt/dingofs-chaos-tool",
                "--ssh-identity-file", "/root/.ssh/rocky_70",
                "--enable-external-chaos", "--allow-high-risk-chaos",
                "mds_manage",
            ],
        )
        self.assertNotIn("--case", command_tokens)

    def test_daily_stops_before_container_start_when_identity_is_missing(self):
        result, args, identity = self._run_daily(create_identity=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(args, [])
        self.assertIn(str(identity), result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
