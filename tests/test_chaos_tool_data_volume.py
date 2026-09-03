from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_SCRIPT = ROOT / "scripts" / "configure_chaos_tool_runtime.sh"


class ChaosToolDataVolumeTest(unittest.TestCase):
    def test_runtime_layout_keeps_code_immutable_and_data_under_var(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            chaos_root = Path(temp_dir) / "dingofs-chaos-tool"
            catalog = chaos_root / "config" / "catalog"
            catalog.mkdir(parents=True)
            (catalog / "custom.yaml").write_text("{}\n", encoding="utf-8")

            result = subprocess.run(
                ["bash", str(LAYOUT_SCRIPT), str(chaos_root)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            expected_links = {
                "runs": "var/runs",
                "logs": "var/logs",
                "reports": "var/reports",
                "config/catalog/custom.yaml": "../../var/catalog/custom.yaml",
            }
            for relative_path, target in expected_links.items():
                path = chaos_root / relative_path
                self.assertTrue(path.is_symlink(), relative_path)
                self.assertEqual(os.readlink(path), target)

            (chaos_root / "runs" / "result.json").write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                (chaos_root / "var" / "runs" / "result.json").read_text(encoding="utf-8"),
                "{}\n",
            )
            self.assertEqual(
                (chaos_root / "var" / "catalog" / "custom.yaml").read_text(encoding="utf-8"),
                "{}\n",
            )

    def test_debug_mounts_data_volume_without_masking_image_code(self):
        wrapper = ROOT / "dingofs-testsuite-tool"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            output = temp / "output"
            calls_file = temp / "runtime-calls"
            runtime = temp / "fake-runtime"
            config.mkdir()
            output.mkdir()
            runtime.write_text(
                textwrap.dedent(
                    f"""
                    #!/bin/bash
                    printf 'CALL' >> {shlex.quote(str(calls_file))}
                    printf '\\t%s' "$@" >> {shlex.quote(str(calls_file))}
                    printf '\\n' >> {shlex.quote(str(calls_file))}
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            runtime.chmod(0o755)
            (config / "image").write_text("test-image\n", encoding="utf-8")
            (config / "runtime").write_text(f"{runtime}\n", encoding="utf-8")
            (config / "output").write_text(f"{output}\n", encoding="utf-8")

            command = textwrap.dedent(
                f"""
                export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}
                unset DINGOFS_CHAOS_TOOL_VOLUME
                source {shlex.quote(str(wrapper))}
                _is_rootless() {{ return 0; }}
                cmd_debug </dev/null
                """
            )
            result = subprocess.run(
                ["bash", "-c", command],
                text=True,
                capture_output=True,
                check=False,
            )
            calls = [
                line.split("\t")[1:]
                for line in calls_file.read_text(encoding="utf-8").splitlines()
                if line.startswith("CALL\t")
            ]

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 2)
        expected_mount = (
            "dingofs-chaos-tool-data:/opt/dingofs-chaos-tool/var:rw"
        )
        for call in calls:
            mounts = [call[index + 1] for index, arg in enumerate(call[:-1]) if arg == "-v"]
            self.assertIn(expected_mount, mounts)
            self.assertNotIn(
                "dingofs-chaos-tool-data:/opt/dingofs-chaos-tool:rw",
                mounts,
            )

    def test_fault_run_mounts_data_volume_without_masking_image_code(self):
        wrapper = ROOT / "dingofs-testsuite-tool"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            mount = temp / "mount"
            output = temp / "output"
            calls_file = temp / "runtime-calls"
            runtime = temp / "fake-runtime"
            config.mkdir()
            mount.mkdir()
            output.mkdir()
            runtime.write_text(
                textwrap.dedent(
                    f"""
                    #!/bin/bash
                    printf 'CALL' >> {shlex.quote(str(calls_file))}
                    printf '\\t%s' "$@" >> {shlex.quote(str(calls_file))}
                    printf '\\n' >> {shlex.quote(str(calls_file))}
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            runtime.chmod(0o755)
            (config / "image").write_text("test-image\n", encoding="utf-8")
            (config / "runtime").write_text(f"{runtime}\n", encoding="utf-8")
            (config / "testdir").write_text(f"{mount}\n", encoding="utf-8")
            (config / "output").write_text(f"{output}\n", encoding="utf-8")

            command = textwrap.dedent(
                f"""
                export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}
                unset DINGOFS_CHAOS_TOOL_VOLUME
                source {shlex.quote(str(wrapper))}
                _is_rootless() {{ return 0; }}
                run_testsuite -t int -s fault
                """
            )
            result = subprocess.run(
                ["bash", "-c", command],
                text=True,
                capture_output=True,
                check=False,
            )
            calls = [
                line.split("\t")[1:]
                for line in calls_file.read_text(encoding="utf-8").splitlines()
                if line.startswith("CALL\t")
            ]

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 2)
        expected_mount = (
            "dingofs-chaos-tool-data:/opt/dingofs-chaos-tool/var:rw"
        )
        for call in calls:
            mounts = [call[index + 1] for index, arg in enumerate(call[:-1]) if arg == "-v"]
            self.assertIn(expected_mount, mounts)
            self.assertNotIn(
                "dingofs-chaos-tool-data:/opt/dingofs-chaos-tool:rw",
                mounts,
            )


if __name__ == "__main__":
    unittest.main()
