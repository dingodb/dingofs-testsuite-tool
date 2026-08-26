from pathlib import Path
import json
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ElbenchoReportTest(unittest.TestCase):
    def test_json_lines_generate_markdown_with_parameters_metrics_and_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            command = (
                "elbencho -w -b 4K -t 10 --direct -s 10m "
                "--jsonfile /output/elbencho_test/seq_write.json "
                "-n 1 -N 10 -d /data"
            )
            config = {
                "path_type": "dir",
                "paths": "1",
                "hosts": "1",
                "threads": "10",
                "dirs": "1",
                "files": "10",
                "file_size": "10485760",
                "block_size": "4096",
                "direct_io": "true",
                "random_offsets": "false",
                "io_depth": "1",
                "version": "3.0-37",
                "command": command,
            }
            phases = [
                {
                    "phase_type": "MKDIRS",
                    "config": config,
                    "first_done": {
                        "elapsed_time_ms": "377",
                        "entries/s": "2",
                        "entries": "1",
                        "cpu%": "0",
                    },
                    "last_done": {
                        "elapsed_time_ms": "1319",
                        "entries/s": "7",
                        "entries": "10",
                        "cpu%": "0",
                    },
                },
                {
                    "phase_type": "WRITE",
                    "config": config,
                    "first_done": {
                        "elapsed_time_ms": "3339",
                        "entries/s": "25",
                        "iops": "71299",
                        "bytes/s": "292043875",
                        "entries": "86",
                        "bytes": "975175680",
                        "cpu%": "9",
                    },
                    "last_done": {
                        "elapsed_time_ms": "3778",
                        "entries/s": "26",
                        "iops": "67758",
                        "bytes/s": "277539020",
                        "entries": "100",
                        "bytes": "1048576000",
                        "cpu%": "8",
                    },
                },
            ]
            (output / "seq_write.json").write_text(
                "\n".join(json.dumps(phase) for phase in phases) + "\n",
                encoding="utf-8",
            )
            (output / "seq_write.log").write_text("raw output\n", encoding="utf-8")
            (output / "result.log").write_text("framework summary\n", encoding="utf-8")
            (output / "seq_write.command").write_text(command + "\n", encoding="utf-8")
            (output / "seq_write.exitcode").write_text("0\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts" / "generate_report.py"),
                    "--tool",
                    "elbencho",
                    "--output-dir",
                    str(output),
                    "--scenario",
                    "seq_write",
                    "--mount",
                    "/data",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            reports = list(output.glob("elbencho_seq_write_summary_*.md"))
            self.assertEqual(len(reports), 1)
            report = reports[0].read_text(encoding="utf-8")
            for expected in (
                "| 工具 | ELBENCHO |",
                "| 场景 | seq_write |",
                "| 状态 | PASS |",
                "| 并发线程数 | 10 |",
                "| 每线程目录数 | 1 |",
                "| 每目录文件数 | 10 |",
                "| 文件大小 | 10.00 MiB |",
                "| 块大小 | 4.00 KiB |",
                "| Direct I/O | true |",
                "| 随机访问 | false |",
                "```bash\n" + command + "\n```",
                "| WRITE | First Done | 3339 | 25 | 71299 | 278.51 | 86 | 930.00 MiB | 9% |",
                "| WRITE | Last Done | 3778 | 26 | 67758 | 264.68 | 100 | 1000.00 MiB | 8% |",
                "`seq_write.json`",
                "`seq_write.log`",
            ):
                self.assertIn(expected, report)
            self.assertNotIn("### result", report)

    def test_failed_scenario_without_json_still_reports_command_and_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            command = "elbencho -r -b 4M -t 8 --direct -s 1G /data/missing"
            (output / "seq_read.command").write_text(command + "\n", encoding="utf-8")
            (output / "seq_read.exitcode").write_text("3\n", encoding="utf-8")
            (output / "seq_read.log").write_text("file not found\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts" / "generate_report.py"),
                    "--tool",
                    "elbencho",
                    "--output-dir",
                    str(output),
                    "--scenario",
                    "seq_read",
                    "--mount",
                    "/data",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = next(output.glob("elbencho_seq_read_summary_*.md")).read_text(
                encoding="utf-8"
            )
            self.assertIn("| 状态 | FAIL |", report)
            self.assertIn(command, report)
            self.assertIn("*无可解析的 JSON 指标数据*", report)
            self.assertIn("`seq_read.log`", report)
            self.assertNotIn("`seq_read.json`", report)

    def test_all_scenario_combines_multiple_workloads_in_one_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            for scenario, phase_type, command in (
                ("seq_write", "WRITE", "elbencho -w -b 4M -t 8 /data"),
                ("rand_write", "WRITE", "elbencho -w --rand -b 4M -t 8 /data"),
            ):
                phase = {
                    "phase_type": phase_type,
                    "config": {
                        "threads": "8",
                        "file_size": "1073741824",
                        "block_size": "4194304",
                        "command": command,
                    },
                    "first_done": {"elapsed_time_ms": "1000"},
                    "last_done": {"elapsed_time_ms": "1100"},
                }
                (output / f"{scenario}.json").write_text(
                    json.dumps(phase) + "\n", encoding="utf-8"
                )
                (output / f"{scenario}.command").write_text(
                    command + "\n", encoding="utf-8"
                )
                (output / f"{scenario}.exitcode").write_text("0\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts" / "generate_report.py"),
                    "--tool",
                    "elbencho",
                    "--output-dir",
                    str(output),
                    "--scenario",
                    "all",
                    "--mount",
                    "/data",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            reports = list(output.glob("elbencho_all_summary_*.md"))
            self.assertEqual(len(reports), 1)
            report = reports[0].read_text(encoding="utf-8")
            self.assertIn("### seq_write", report)
            self.assertIn("### rand_write", report)
            self.assertIn("elbencho -w -b 4M -t 8 /data", report)
            self.assertIn("elbencho -w --rand -b 4M -t 8 /data", report)


if __name__ == "__main__":
    unittest.main()
