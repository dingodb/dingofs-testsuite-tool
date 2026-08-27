from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ElbenchoSmallReportTest(unittest.TestCase):
    def _run_small(self, fail_operation="", fail_threads="", extra_args=None):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        temp = Path(temp_dir.name)
        mount = temp / "mount"
        output = temp / "output"
        bin_dir = temp / "bin"
        calls_file = temp / "calls"
        mount.mkdir()
        output.mkdir()
        bin_dir.mkdir()

        fake_elbencho = bin_dir / "elbencho"
        fake_elbencho.write_text(
            "#!/bin/bash\n"
            "operation=read\n"
            "threads=\n"
            "previous=\n"
            "for argument in \"$@\"; do\n"
            "    [[ \"$argument\" == '-w' ]] && operation=write\n"
            "    if [[ \"$previous\" == '-t' ]]; then threads=\"$argument\"; fi\n"
            "    previous=\"$argument\"\n"
            "done\n"
            f"printf '%s,%s\\n' \"$operation\" \"$threads\" >> {calls_file}\n"
            "echo 'Throughput MiB/s: 123.45'\n"
            "echo 'Files latency: avg=1.25 max=4.50'\n"
            "if [[ \"$operation\" == \"$FAIL_OPERATION\" ]] && "
            "[[ \"$threads\" == \"$FAIL_THREADS\" ]]; then exit 7; fi\n",
            encoding="utf-8",
        )
        fake_elbencho.chmod(0o755)

        environment = os.environ.copy()
        environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
        environment["FAIL_OPERATION"] = fail_operation
        environment["FAIL_THREADS"] = fail_threads
        result = subprocess.run(
            [
                "bash",
                str(ROOT / "scenarios/elbencho/small.sh"),
                str(mount),
                str(output),
                *(extra_args or []),
            ],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )

        reports = list(output.glob("elbencho_small_*/elbencho_small_summary_*.md"))
        report = reports[0].read_text(encoding="utf-8") if reports else ""
        calls = (
            calls_file.read_text(encoding="utf-8").splitlines()
            if calls_file.exists()
            else []
        )
        return result, report, calls

    def test_report_lists_commands_separately_and_splits_write_and_read_results(self):
        result, report, calls = self._run_small()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 12)
        self.assertIn("## 实际执行命令", report)
        self.assertEqual(report.count("```bash"), 12)
        self.assertIn("elbencho ", report)
        self.assertIn(" -w -t 1 ", report)
        self.assertIn(" -r -t 32 ", report)
        self.assertIn("## 写测试结果", report)
        self.assertIn("## 读测试结果", report)
        self.assertIn("| 1 | PASS | 0 | 123.45 | 1.25 | 4.50 |", report)
        self.assertIn("| 32 | PASS | 0 | 123.45 | 1.25 | 4.50 |", report)

        results_section = report.split("## 写测试结果", 1)[1]
        self.assertNotIn("`elbencho ", results_section)

    def test_failed_test_is_reported_and_remaining_tests_still_run(self):
        result, report, calls = self._run_small("write", "4")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(len(calls), 12)
        self.assertIn("| 4 | FAIL | 7 | 123.45 | 1.25 | 4.50 |", report)
        self.assertIn("| 32 | PASS | 0 | 123.45 | 1.25 | 4.50 |", report)

    def test_custom_parameters_control_workload_and_report(self):
        result, report, calls = self._run_small(
            extra_args=[
                "--file-size", "10m",
                "--file-count", "100",
                "--block-size", "1m",
                "--threads", "2,8",
            ]
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls, ["write,2", "read,2", "write,8", "read,8"])
        self.assertIn("| 文件大小 | 10m |", report)
        self.assertIn("| 块大小 | 1m |", report)
        self.assertIn("| 每目录文件数 | 100 |", report)
        self.assertIn("| 并发度 | 2,8 |", report)
        self.assertIn(" -w -t 2 -n 1 -N 100 -s 10m -b 1m ", report)
        self.assertIn(" -r -t 8 -n 1 -N 100 -s 10m -b 1m ", report)


if __name__ == "__main__":
    unittest.main()
