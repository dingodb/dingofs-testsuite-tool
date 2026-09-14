"""Only fake runtimes/transports: no storage test, Jenkins call or real email."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DailyConsistencyTest(unittest.TestCase):
    def test_daily_mounts_credentials_readonly_without_exposing_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            config.mkdir()
            output = root / "output"
            output.mkdir()
            args = root / "args"
            runtime = root / "runtime"
            runtime.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$CAPTURE_ARGS"\nexit 7\n')
            runtime.chmod(0o755)
            (config / "runtime").write_text(str(runtime) + "\n")
            (config / "output").write_text(str(output) + "\n")
            (config / "image").write_text("fake-image\n")
            credential = config / "jenkins_consistency.json"
            credential.write_text(json.dumps(dict(ssh_user="jenkins", ssh_host="172.30.14.128")))
            key, known = root / "key", root / "known_hosts"
            key.write_text("test-private-key")
            known.write_text("trusted-public-host-key")
            command = "source %s; _is_rootless() { false; }; cmd_daily --include client,cache_node" % shlex.quote(str(ROOT / "dingofs-testsuite-tool"))
            result = subprocess.run(["bash", "-c", command], capture_output=True, text=True,
                                    env={**os.environ, "DINGOFS_TESTSUITE_CONFIG_DIR": str(config),
                                         "DTT_JENKINS_CONFIG": "", "CAPTURE_ARGS": str(args),
                                         "DTT_JENKINS_SSH_KEY": str(key), "DTT_JENKINS_KNOWN_HOSTS": str(known)})
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            recorded = args.read_text().splitlines()
            self.assertIn(str(credential) + ":/tmp/dtt-jenkins-consistency.json:ro", recorded)
            self.assertIn("DTT_JENKINS_CONSISTENCY=1", recorded)
            self.assertIn("DTT_JENKINS_CONFIG=/tmp/dtt-jenkins-consistency.json", recorded)
            self.assertIn(str(key) + ":/tmp/dtt-jenkins-ssh-key:ro", recorded)
            self.assertIn(str(known) + ":/tmp/dtt-jenkins-known-hosts:ro", recorded)
            self.assertIn("DTT_JENKINS_SSH_KEY=/tmp/dtt-jenkins-ssh-key", recorded)
            self.assertNotIn("test-private-key", args.read_text() + result.stdout + result.stderr)

    def test_deferred_daily_renders_saved_snapshot_without_querying_jenkins(self):
        self._check_deferred_daily(False)

    def test_deferred_daily_renders_multiple_jobs_without_querying_jenkins(self):
        self._check_deferred_daily(True)

    def _check_deferred_daily(self, multi):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            captured = root / "mail"
            swaks = fake_bin / "swaks"
            swaks.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$MAIL_CAPTURE"\n')
            swaks.chmod(0o755)
            chat = root / "chat"
            curl = fake_bin / "curl"
            curl.write_text('#!/bin/bash\nwhile (( $# )); do\n'
                            'if [[ "$1" == "-d" ]]; then printf "%s\\n" "$2" >> "$CHAT_CAPTURE"; break; fi\n'
                            'shift\ndone\nprintf \'{"errcode":0}\\n\'\n')
            curl.chmod(0o755)
            manifest = root / "run_manifest.json"
            manifest.write_text(json.dumps(dict(mode="daily", started_at="2026-09-14",
                suites=[dict(name="client", total=1, **{"pass": 1, "fail": 0, "error": 0})],
                consistency=dict(status="RUNNING", job_url="http://jenkins.example/job/parent/",
                    duration_ms=16800000, success_count=2, latest_build=104, first_build=102,
                    started_at="2026-09-14 08:00:00 +08:00", as_of="2026-09-14 12:40:00 +08:00",
                    history_complete=True))))
            if multi:
                data = json.loads(manifest.read_text())
                second = dict(data["consistency"], job_url="http://jenkins.example/job/second/",
                              status="FAILURE", duration_ms=0, success_count=0,
                              message="统计说明\n" * 600)
                data["consistency"] = [data["consistency"], second]
                manifest.write_text(json.dumps(data))
            command = "source %s; send_ai_manifest_notification %s" % (
                shlex.quote(str(ROOT / "scripts/notify.sh")), shlex.quote(str(manifest)))
            result = subprocess.run(["bash", "-c", command], capture_output=True, text=True,
                env={**os.environ, "PATH": str(fake_bin) + ":" + os.environ["PATH"],
                     "EMAIL": "yes", "WECHAT": "yes", "WEBHOOK_URL": "https://example.invalid/webhook",
                     "CHAT_CAPTURE": str(chat), "EMAIL_TO": "recipient@example.com",
                     "EMAILPASS": "test-password", "DTT_DEFER_NOTIFICATIONS": "no",
                     "MAIL_CAPTURE": str(captured)})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("4小时40分0秒", captured.read_text())
            self.assertIn("统计时间", captured.read_text())
            chunks = [json.loads(line)["markdown"]["content"] for line in chat.read_text().splitlines()]
            self.assertTrue(all(len(chunk.encode("utf-8")) <= 4096 for chunk in chunks))
            self.assertIn("[parent](http://jenkins.example/job/parent/)", "".join(chunks))
            if multi:
                self.assertGreater(len(chunks), 1)
                self.assertIn("[second](http://jenkins.example/job/second/)", "".join(chunks))
                self.assertIn('href="http://jenkins.example/job/second/">second</a>', captured.read_text())
                self.assertIn("失败", captured.read_text())


if __name__ == "__main__":
    unittest.main()
