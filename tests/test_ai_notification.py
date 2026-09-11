import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTIFY = ROOT / "scripts" / "notify.sh"


class AiNotificationTest(unittest.TestCase):
    def _make_fake(self, directory, name, body):
        path = directory / name
        path.write_text("#!/bin/bash\n" + body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def test_deferred_notifications_do_not_call_transports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_bin = temp / "bin"
            fake_bin.mkdir()
            marker = temp / "transport-called"
            self._make_fake(fake_bin, "swaks", "touch \"$TRANSPORT_MARKER\"\n")
            self._make_fake(
                fake_bin,
                "curl",
                "touch \"$TRANSPORT_MARKER\"\necho '{\"errcode\":0}'\n",
            )
            command = (
                "source %s; "
                "send_email_notification fio seq_read FAIL 1s ''; "
                "send_wechat_notification fio seq_read FAIL 1s ''"
            ) % NOTIFY
            env = os.environ.copy()
            env.update(
                {
                    "PATH": "%s:%s" % (fake_bin, env["PATH"]),
                    "EMAIL": "yes",
                    "WECHAT": "yes",
                    "WEBHOOK_URL": "https://example.invalid/webhook",
                    "DTT_DEFER_NOTIFICATIONS": "yes",
                    "TRANSPORT_MARKER": str(marker),
                }
            )

            result = subprocess.run(
                ["bash", "-c", command],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(marker.exists())
            self.assertEqual(result.stdout.count("Notification deferred"), 2)

    def test_manifest_notification_contains_suite_summary_and_both_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_bin = temp / "bin"
            fake_bin.mkdir()
            captured = temp / "swaks-args"
            self._make_fake(
                fake_bin,
                "swaks",
                "printf '%s\\n' \"$@\" > \"$NOTIFY_CAPTURE\"\n",
            )
            manifest = temp / "run_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "mode": "daily",
                        "tool": "int",
                        "scenario": "",
                        "report_links": ["http://host:8889/allure/index.html"],
                        "started_at": "2026-09-11T21:00:00+08:00",
                        "suites": [
                            {
                                "name": "fault",
                                "pass": 4,
                                "fail": 1,
                                "error": 0,
                                "skip": 0,
                                "total": 5,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            command = "source %s; send_ai_manifest_notification %s" % (NOTIFY, manifest)
            env = os.environ.copy()
            env.update(
                {
                    "PATH": "%s:%s" % (fake_bin, env["PATH"]),
                    "EMAIL": "yes",
                    "WECHAT": "no",
                    "EMAIL_TO": "recipient@example.com",
                    "EMAILPASS": "test-password",
                    "NOTIFY_CAPTURE": str(captured),
                    "DTT_DEFER_NOTIFICATIONS": "no",
                    "DTT_ORIGINAL_REPORT_URL": "",
                    "DTT_AI_REPORT_URL": "http://host:8889/ai-analysis/history/run/index.html",
                    "DTT_AI_STATUS_TEXT": "分析成功",
                }
            )

            result = subprocess.run(
                ["bash", "-c", command],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            rendered = captured.read_text(encoding="utf-8")
            self.assertIn(
                "<tr><td>fault</td><td style='color:red'><b>FAIL</b></td>"
                "<td>4</td><td>1</td><td>0</td><td>0</td><td>5</td></tr>",
                rendered,
            )
            self.assertIn("http://host:8889/allure/index.html", rendered)
            self.assertIn("http://host:8889/ai-analysis/history/run/index.html", rendered)
            self.assertIn("分析成功", rendered)


if __name__ == "__main__":
    unittest.main()
