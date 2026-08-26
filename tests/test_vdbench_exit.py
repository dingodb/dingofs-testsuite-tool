from pathlib import Path
import shlex
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class VdbenchExitTest(unittest.TestCase):
    def test_returns_one_when_vdbench_does_not_report_success(self):
        source = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        library = source.rsplit('\nmain "$@"', 1)[0]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            vdbench_dir = temp / "vdbench"
            output = temp / "output"
            mount = temp / "mount"
            vdbench_dir.mkdir()
            output.mkdir()
            mount.mkdir()

            config = temp / "failure.par"
            config.write_text("fsd=fsd1,anchor=/data\n", encoding="utf-8")
            fake_vdbench = vdbench_dir / "vdbench"
            fake_vdbench.write_text(
                "#!/bin/bash\n"
                "echo \"java.lang.RuntimeException: 'data_errors=1' requested.\"\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_vdbench.chmod(0o755)

            harness = textwrap.dedent(
                f"""
                get_scenario_paths() {{ printf '%s\n' {shlex.quote(str(config))}; }}
                python3() {{ :; }}
                log_result() {{ :; }}
                send_wechat_notification() {{ :; }}
                send_email_notification() {{ :; }}
                VDBENCH_DIR={shlex.quote(str(vdbench_dir))}
                OUTPUT={shlex.quote(str(output))}
                MOUNT={shlex.quote(str(mount))}
                SCENARIO=stability
                RUN_TIMESTAMP=test-run
                WECHAT_ENABLED=no
                EMAIL_ENABLED=no

                set +e
                vdbench_run
                exit $?
                """
            )
            script = temp / "run-vdbench.sh"
            script.write_text(library + "\n" + harness, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(script)], text=True, capture_output=True, check=False
            )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("vdbench status: FAIL", result.stdout)


if __name__ == "__main__":
    unittest.main()
