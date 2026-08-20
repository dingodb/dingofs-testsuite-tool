import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SmokeNotificationTest(unittest.TestCase):
    def test_smoke_email_renders_suite_errors_and_skipped_modules(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_bin = temp / "bin"
            fake_bin.mkdir()
            captured = temp / "swaks-args"
            swaks = fake_bin / "swaks"
            swaks.write_text(
                "#!/bin/bash\nprintf '%s\\n' \"$@\" > \"$NOTIFY_ARGS_FILE\"\n",
                encoding="utf-8",
            )
            swaks.chmod(0o755)
            details = (
                "int_dirstat[FAIL] pass:0 fail:0 error:1 skip:2 excluded:0 total:3\n"
                "int_xattr[SKIP] pass:0 fail:0 error:0 skip:0 excluded:1 total:0"
            )
            command = (
                f"source {ROOT / 'scripts' / 'notify.sh'}; "
                "send_email_notification smoke smoke FAIL 1s \"$SMOKE_DETAILS\""
            )
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "EMAIL": "yes",
                    "EMAIL_TO": "smoke@example.com",
                    "NOTIFY_ARGS_FILE": str(captured),
                    "SMOKE_DETAILS": details,
                }
            )
            result = subprocess.run(
                ["bash", "-c", command],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            rendered = captured.read_text(encoding="utf-8")
            self.assertIn("错误 (Error)", rendered)
            self.assertRegex(
                rendered,
                re.compile(
                    r"int_dirstat.*?<td>0</td><td>0</td><td>1</td>"
                    r"<td>2</td><td>3</td></tr>",
                    re.DOTALL,
                ),
            )
            self.assertRegex(
                rendered,
                re.compile(
                    r"int_xattr.*?<td>0</td><td>0</td><td>0</td>"
                    r"<td>0</td><td>0</td></tr>",
                    re.DOTALL,
                ),
            )


if __name__ == "__main__":
    unittest.main()
