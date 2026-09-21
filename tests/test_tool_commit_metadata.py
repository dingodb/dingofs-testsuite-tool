import os
from pathlib import Path
import shlex
import stat
import subprocess
import tempfile
import textwrap
import unittest

from tests.test_smoke_cli import jenkins_metadata


ROOT = Path(__file__).resolve().parents[1]


class ToolCommitMetadataTest(unittest.TestCase):
    def test_vdbench_forwards_jenkins_commit_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            mount = temp / "mount"
            output = temp / "output"
            for path in (config, mount, output):
                path.mkdir()

            runtime_args = temp / "runtime-args"
            runtime = temp / "fake-runtime"
            runtime.write_text(
                "#!/bin/bash\n"
                f"printf '%s\\n' \"$@\" > {shlex.quote(str(runtime_args))}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)

            (config / "image").write_text("test-image\n", encoding="utf-8")
            (config / "testdir").write_text(f"{mount}\n", encoding="utf-8")
            (config / "output").write_text(f"{output}\n", encoding="utf-8")
            (config / "runtime").write_text(f"{runtime}\n", encoding="utf-8")

            command = textwrap.dedent(
                f"""
                export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}
                source {shlex.quote(str(ROOT / 'dingofs-testsuite-tool'))}
                _is_rootless() {{ false; }}
                run_testsuite -t vdbench -s seq_rd
                """
            )
            env = os.environ.copy()
            metadata = jenkins_metadata()
            env.update(metadata)
            result = subprocess.run(
                ["bash", "-c", command],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            args = runtime_args.read_text(encoding="utf-8").splitlines()
            for name, value in metadata.items():
                self.assertIn(f"{name}={value}", args)

    def test_deferred_notification_forwards_jenkins_commit_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            config.mkdir()
            manifest = temp / "run_manifest.json"
            manifest.write_text("{}\n", encoding="utf-8")
            runtime_args = temp / "runtime-args"
            runtime = temp / "fake-runtime"
            runtime.write_text(
                "#!/bin/bash\n"
                f"printf '%s\\n' \"$@\" > {shlex.quote(str(runtime_args))}\n",
                encoding="utf-8",
            )
            runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)
            (config / "image").write_text("test-image\n", encoding="utf-8")
            (config / "runtime").write_text(f"{runtime}\n", encoding="utf-8")
            (config / "email").write_text("ci@example.com\n", encoding="utf-8")

            command = textwrap.dedent(
                f"""
                export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}
                source {shlex.quote(str(ROOT / 'dingofs-testsuite-tool'))}
                run_deferred_notification \
                    {shlex.quote(str(manifest))} \
                    https://reports.example/original \
                    https://reports.example/ai \
                    success yes ''
                """
            )
            env = os.environ.copy()
            metadata = jenkins_metadata()
            env.update(metadata)
            result = subprocess.run(
                ["bash", "-c", command],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            args = runtime_args.read_text(encoding="utf-8").splitlines()
            for name, value in metadata.items():
                self.assertIn(f"{name}={value}", args)


if __name__ == "__main__":
    unittest.main()
