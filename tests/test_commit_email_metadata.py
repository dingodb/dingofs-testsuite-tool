import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CommitEmailMetadataTest(unittest.TestCase):
    def _render_email(self, metadata):
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
            env = os.environ.copy()
            for name in (
                "DTT_PR_NUMBER",
                "DTT_PR_AUTHOR",
                "DTT_TEST_COMMIT_SHA",
                "DTT_TEST_COMMIT_AUTHOR_NAME",
                "DTT_TEST_COMMIT_AUTHOR_EMAIL",
                "DTT_TEST_COMMIT_SUBJECT",
                "DTT_TEST_COMMIT_URL",
                "DTT_JENKINS_BUILD_URL",
            ):
                env.pop(name, None)
            env.update(
                {
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "EMAIL": "yes",
                    "EMAIL_TO": "ci@example.com",
                    "NOTIFY_ARGS_FILE": str(captured),
                    **metadata,
                }
            )
            command = (
                f"source {ROOT / 'scripts' / 'notify.sh'}; "
                "send_email_notification vdbench stability SUCCESS 1s ''"
            )
            result = subprocess.run(
                ["bash", "-c", command],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return captured.read_text(encoding="utf-8")

    def test_email_renders_escaped_commit_context(self):
        rendered = self._render_email(
            {
                "DTT_PR_NUMBER": "1083",
                "DTT_PR_AUTHOR": "octo<&cat",
                "DTT_TEST_COMMIT_SHA": "0123456789abcdef",
                "DTT_TEST_COMMIT_AUTHOR_NAME": 'A <B> & "C"',
                "DTT_TEST_COMMIT_AUTHOR_EMAIL": "author@example.com",
                "DTT_TEST_COMMIT_SUBJECT": (
                    "fix <cache> & report\n"
                    "<img src=x onerror=alert(1)>|injected"
                ),
                "DTT_TEST_COMMIT_URL": "https://github.com/dingodb/dingofs/commit/0123?a=1&b=2",
                "DTT_JENKINS_BUILD_URL": "http://jenkins.example/job/7/?a=1&b=2",
            }
        )

        self.assertIn("提交信息", rendered)
        self.assertIn("1083", rendered)
        self.assertIn("octo&lt;&amp;cat", rendered)
        self.assertIn("0123456789abcdef", rendered)
        self.assertIn("A &lt;B&gt; &amp; &quot;C&quot;", rendered)
        self.assertIn("author@example.com", rendered)
        self.assertIn("fix &lt;cache&gt; &amp; report", rendered)
        self.assertIn(
            "&lt;img src=x onerror=alert(1)&gt;|injected",
            rendered,
        )
        self.assertNotIn("<img src=x onerror=alert(1)>", rendered)
        self.assertIn(
            "<a href='https://github.com/dingodb/dingofs/commit/0123?a=1&amp;b=2'>"
            "https://github.com/dingodb/dingofs/commit/0123?a=1&amp;b=2</a>",
            rendered,
        )
        self.assertIn(
            "<a href='http://jenkins.example/job/7/?a=1&amp;b=2'>"
            "http://jenkins.example/job/7/?a=1&amp;b=2</a>",
            rendered,
        )
        self.assertNotIn('A <B> & "C"', rendered)

    def test_email_omits_commit_context_without_metadata(self):
        rendered = self._render_email({})

        self.assertNotIn("提交信息", rendered)


if __name__ == "__main__":
    unittest.main()
