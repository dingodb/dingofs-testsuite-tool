#!/usr/bin/env python3
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "dingofs-testsuite-tool"


class CommitInfoPathTests(unittest.TestCase):
    def test_daily_commit_info_path_uses_home_and_allows_override(self):
        script = CLI.read_text(encoding="utf-8")

        self.assertIn(
            'local commit_info_file="${DTT_COMMIT_INFO_FILE:-${HOME}/jenkins_workdir/script-main/commit_info.yaml}"',
            script,
        )
        self.assertNotIn(
            'local commit_info_file="__USER_HOME__/jenkins_workdir/script-main/commit_info.yaml"',
            script,
        )


if __name__ == "__main__":
    unittest.main()
