import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "scripts" / "sync_chaos_tool.sh"


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


class SyncChaosToolTest(unittest.TestCase):
    def _create_source(self, root):
        source = root / "source"
        source.mkdir()
        _git(source, "init", "-b", "v5.2")
        _git(source, "config", "user.name", "Test User")
        _git(source, "config", "user.email", "test@example.com")
        (source / ".gitignore").write_text(
            ".pytest_cache/\n__pycache__/\nlogs/\nruns/\nvar/\n",
            encoding="utf-8",
        )
        (source / "chaos_tool.py").write_text("VERSION = 'new'\n", encoding="utf-8")
        _git(source, "add", ".")
        _git(source, "commit", "-m", "source snapshot")
        (source / "logs").mkdir()
        (source / "logs" / "ignored.log").write_text("ignored\n", encoding="utf-8")
        return source

    def _run_sync(self, source, target):
        env = os.environ.copy()
        env["DINGOFS_CHAOS_TOOL_SRC"] = str(source)
        env["DINGOFS_CHAOS_TOOL_DEST"] = str(target)
        return subprocess.run(
            ["bash", str(SYNC_SCRIPT)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_clean_source_replaces_target_repo_and_removes_runtime_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = self._create_source(temp)
            target = temp / "target"
            (target / "logs").mkdir(parents=True)
            (target / "stale.py").write_text("stale\n", encoding="utf-8")
            (target / "logs" / "old.log").write_text("old\n", encoding="utf-8")

            result = self._run_sync(source, target)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                (target / "chaos_tool.py").read_text(encoding="utf-8"),
                "VERSION = 'new'\n",
            )
            self.assertFalse((target / "stale.py").exists())
            self.assertFalse((target / "logs").exists())
            self.assertEqual(_git(target, "rev-parse", "HEAD"), _git(source, "rev-parse", "HEAD"))
            self.assertEqual(_git(target, "status", "--short"), "")

    def test_dirty_source_is_rejected_without_changing_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = self._create_source(temp)
            target = temp / "target"
            target.mkdir()
            marker = target / "keep-me"
            marker.write_text("original\n", encoding="utf-8")
            (source / "chaos_tool.py").write_text("VERSION = 'dirty'\n", encoding="utf-8")

            result = self._run_sync(source, target)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("uncommitted", (result.stdout + result.stderr).lower())
            self.assertEqual(marker.read_text(encoding="utf-8"), "original\n")

    def test_default_source_uses_project_local_chaos_tool_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            scripts = project / "scripts"
            scripts.mkdir()
            sync_script = scripts / "sync_chaos_tool.sh"
            shutil.copy2(SYNC_SCRIPT, sync_script)

            chaos_tool = project / "dingofs-chaos-tool"
            chaos_tool.mkdir()
            _git(chaos_tool, "init", "-b", "v5.2")
            _git(chaos_tool, "config", "user.name", "Test User")
            _git(chaos_tool, "config", "user.email", "test@example.com")
            marker = chaos_tool / "chaos_tool.py"
            marker.write_text("VERSION = 'project-local'\n", encoding="utf-8")
            _git(chaos_tool, "add", ".")
            _git(chaos_tool, "commit", "-m", "project-local snapshot")
            expected_head = _git(chaos_tool, "rev-parse", "HEAD")

            env = os.environ.copy()
            env.pop("DINGOFS_CHAOS_TOOL_SRC", None)
            env.pop("DINGOFS_CHAOS_TOOL_DEST", None)
            result = subprocess.run(
                ["bash", str(sync_script)],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(_git(chaos_tool, "rev-parse", "HEAD"), expected_head)
            self.assertEqual(marker.read_text(encoding="utf-8"), "VERSION = 'project-local'\n")
            self.assertEqual(_git(chaos_tool, "status", "--short"), "")

    def test_build_synchronizes_chaos_tool_before_docker_build(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            build_script = temp / "build.sh"
            shutil.copy2(ROOT / "build.sh", build_script)
            (temp / "dingofs-integration-test").mkdir()
            scripts = temp / "scripts"
            scripts.mkdir()
            sync_marker = temp / "sync-complete"
            sync_script = scripts / "sync_chaos_tool.sh"
            sync_script.write_text(
                f"#!/bin/bash\ntouch {sync_marker}\n",
                encoding="utf-8",
            )
            sync_script.chmod(0o755)

            fake_bin = temp / "fake-bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
            fake_git.chmod(0o755)
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                textwrap.dedent(
                    f"""
                    #!/bin/bash
                    if [[ ! -f {sync_marker} ]]; then
                        echo "chaos-tool sync did not run before docker" >&2
                        exit 23
                    fi
                    exit 0
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            result = subprocess.run(
                [str(build_script), "--debug"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(sync_marker.exists())


if __name__ == "__main__":
    unittest.main()
