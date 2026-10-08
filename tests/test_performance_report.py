"""Behavioral tests for the offline performance result report."""
import copy
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import performance_report
except ImportError:
    performance_report = None


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.text = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def example_report():
    return {
        "status": "passed", "started_at": "2026-10-05T03:00:00Z",
        "elapsed_seconds": 20.0, "tool_version": "fio-3.39", "error": "",
        "plan": {"tool": "fio", "mode": "readwrite", "direct": 1,
                 "concurrency": 4, "file_size_bytes": 1048576,
                 "file_count": 8, "total_size_bytes": 8388608,
                 "block_size_bytes": 4096, "rounds": 2, "iodepth": 8,
                 "read_percent": 70, "data_dir": "/mnt/dingo/perf",
                 "mount": "/mnt/dingo", "output_dir": "/tmp/results"},
        "rounds": [
            {"round": 1, "status": "passed", "elapsed_seconds": 2.0,
             "metrics": {"bandwidth_mib_s": 100, "read_mib_s": 70,
                         "write_mib_s": 30, "iops": 25600,
                         "latency_mean_us": 40, "io_bytes": 8388608},
             "artifacts": {"log": "round-001.log", "json": "round-001.json",
                           "command": "round-001.command", "config": "round-001.fio"}},
            {"round": 2, "status": "passed", "elapsed_seconds": 4.0,
             "metrics": {"bandwidth_mib_s": 200, "read_mib_s": 140,
                         "write_mib_s": 60, "iops": 51200,
                         "io_bytes": 8388608}, "artifacts": {"log": "round-002.log"}},
        ],
    }


class PerformanceReportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(performance_report, "performance_report module must be implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "report"

    def render(self, report):
        result = performance_report.write_report(report, self.output)
        source = (self.output / "index.html").read_text(encoding="utf-8")
        return result, source, Document(source)

    def test_arithmetic_means_exclude_failed_rounds(self):
        rows = example_report()["rounds"]
        rows.append({"round": 3, "status": "failed", "elapsed_seconds": 99,
                     "metrics": {"bandwidth_mib_s": 9999, "iops": 99999}})
        stats = performance_report.compute_statistics(rows)
        self.assertEqual(stats["successful_rounds"], 2)
        self.assertEqual(stats["completed_rounds"], 3)
        self.assertEqual(stats["metrics"]["bandwidth_mib_s"],
                         {"mean": 150.0, "min": 100, "max": 200, "samples": 2})
        self.assertEqual(stats["metrics"]["elapsed_seconds"]["mean"], 3.0)
        self.assertEqual(stats["metrics"]["iops"]["mean"], 38400.0)

    def test_missing_latency_is_not_counted_as_zero(self):
        stats = performance_report.compute_statistics(example_report()["rounds"])
        self.assertEqual(stats["metrics"]["latency_mean_us"],
                         {"mean": 40.0, "min": 40, "max": 40, "samples": 1})
        self.assertNotIn("p99", stats["metrics"])

    def test_empty_results_have_no_fabricated_measurements(self):
        stats = performance_report.compute_statistics([])
        self.assertEqual(stats["successful_rounds"], 0)
        for metric in stats["metrics"].values():
            self.assertEqual(metric, {"mean": None, "min": None, "max": None, "samples": 0})

    def test_nonfinite_values_are_omitted_from_averages_and_json(self):
        report = example_report()
        report["rounds"][1]["metrics"]["bandwidth_mib_s"] = float("inf")
        report["rounds"][1]["metrics"]["latency_mean_us"] = float("nan")
        report["elapsed_seconds"] = float("-inf")
        result, _, _ = self.render(report)
        self.assertEqual(result["statistics"]["metrics"]["bandwidth_mib_s"]["mean"], 100)
        self.assertEqual(result["statistics"]["metrics"]["latency_mean_us"]["samples"], 1)
        self.assertIsNone(result["elapsed_seconds"])
        raw = (self.output / "summary.json").read_text(encoding="utf-8")
        parsed = json.loads(raw, parse_constant=lambda token: self.fail("Invalid JSON number: " + token))
        self.assertEqual(parsed, result)

    def test_writes_complete_report_without_mutating_caller(self):
        report = example_report()
        original = copy.deepcopy(report)
        result, _, doc = self.render(report)
        self.assertEqual(report, original)
        self.assertTrue(result["statistics"]["complete"])
        self.assertEqual(result["statistics"]["requested_rounds"], 2)
        self.assertEqual(result["statistics"]["metrics"]["read_mib_s"]["mean"], 105)
        text = " ".join(doc.text)
        for value in ("fio", "readwrite", "/mnt/dingo/perf", "8388608", "4096", "70", "fio-3.39"):
            self.assertIn(value, text)
        self.assertTrue(any(tag == "html" and attrs.get("lang") == "zh-CN" for tag, attrs in doc.tags))

    def test_preparation_is_excluded_from_averages(self):
        report = example_report()
        report["preparation"] = {"status": "passed", "elapsed_seconds": 1000,
                                 "metrics": {"bandwidth_mib_s": 9000}, "artifacts": {"log": "prepare.log"}}
        result, _, doc = self.render(report)
        self.assertEqual(result["statistics"]["metrics"]["bandwidth_mib_s"]["mean"], 150)
        self.assertIn("prepare.log", [attrs.get("href") for tag, attrs in doc.tags if tag == "a"])

    def test_partial_failed_and_interrupted_runs_remain_visibly_incomplete(self):
        for status in ("passed", "failed", "interrupted"):
            with self.subTest(status=status):
                report = example_report()
                report["status"] = status
                report["plan"]["rounds"] = 3
                result, _, doc = self.render(report)
                self.assertFalse(result["statistics"]["complete"])
                text = " ".join(doc.text)
                self.assertIn("2 / 3", text)
                self.assertIn("未完成", text)
                if status == "failed":
                    self.assertIn("失败", text)
                elif status == "interrupted":
                    self.assertIn("中断", text)

    def test_failed_status_cannot_be_masked_by_all_successful_rows(self):
        report = example_report()
        report["status"] = "failed"
        result, _, doc = self.render(report)
        self.assertFalse(result["statistics"]["complete"])
        self.assertIn("失败", " ".join(doc.text))

    def test_errors_and_parameters_are_html_escaped(self):
        attack = '<img src=x onerror="alert(1)"><script>alert(2)</script>'
        report = example_report()
        report["error"] = attack
        report["tool_version"] = attack
        report["plan"]["data_dir"] = attack
        report["rounds"][0]["error"] = attack
        _, source, doc = self.render(report)
        self.assertNotIn(attack, source)
        self.assertFalse(any(tag == "img" for tag, _ in doc.tags))
        self.assertIn(attack, "".join(doc.text))
        self.assertFalse(any("onerror" in attrs for _, attrs in doc.tags))

    def test_plan_interpretation_notes_are_displayed_and_escaped(self):
        report = example_report()
        cache_note = 'Direct I/O 不保证绕过服务端缓存；<img src=x onerror="alert(1)">'
        metric_note = ('带宽/IOPS/延迟采用工具原生数据阶段指标；耗时包含进程启动与同步。'
                       'fio end_fsync 与 elbencho 独立 SYNC 的计时口径不同，跨工具对比需结合耗时和原始结果。'
                       '随机模式表示随机偏移，不保证两工具的跨文件访问顺序一致。')
        report["plan"]["cache_note"] = cache_note
        report["plan"]["metric_note"] = metric_note
        result, source, doc = self.render(report)
        self.assertIn(cache_note, "".join(doc.text))
        self.assertIn(metric_note, "".join(doc.text))
        self.assertNotIn(cache_note, source)
        self.assertFalse(any(tag == "img" for tag, _ in doc.tags))
        self.assertEqual(result["plan"]["metric_note"], metric_note)

    def test_ratio_and_depth_labels_describe_configuration_for_both_tools(self):
        for tool in ("fio", "elbencho"):
            with self.subTest(tool=tool):
                report = example_report()
                report["plan"]["tool"] = tool
                _, _, doc = self.render(report)
                text = " ".join(doc.text)
                self.assertIn("目标读比例", text)
                self.assertIn("每个 worker 的 I/O 深度", text)

    def test_artifact_links_allow_only_safe_local_relative_paths(self):
        unsafe = ["https://evil.invalid/x", "//evil.invalid/x", "../secret", "/etc/passwd",
                  "sub/../../secret", "javascript:alert(1)", "sub\\..\\secret",
                  "%2e%2e/secret", "sub/%252e%252e/secret", "x\n.html", "x?go=1", "x#payload"]
        report = example_report()
        report["rounds"][0]["artifacts"] = dict(zip(("unsafe" + str(i) for i in range(len(unsafe))), unsafe))
        report["rounds"][1]["artifacts"] = {"log": "nested/round 002.log"}
        _, _, doc = self.render(report)
        hrefs = [attrs["href"] for tag, attrs in doc.tags if tag == "a"]
        self.assertIn("nested/round%20002.log", hrefs)
        self.assertIn("summary.json", hrefs)
        for path in unsafe:
            self.assertNotIn(path, hrefs)
        self.assertEqual(len(hrefs), 2)

    def test_page_is_offline_and_has_round_filter_and_chart(self):
        report = example_report()
        report["rounds"][1]["status"] = "failed"
        _, _, doc = self.render(report)
        self.assertTrue(any(tag == "select" and attrs.get("id") == "status-filter" for tag, attrs in doc.tags))
        statuses = {attrs["data-status"] for tag, attrs in doc.tags if tag == "tr" and "data-status" in attrs}
        self.assertEqual(statuses, {"passed", "failed"})
        self.assertTrue(any(tag == "svg" for tag, _ in doc.tags))
        self.assertFalse(any(tag in ("script", "link", "iframe") and ("src" in attrs or "href" in attrs)
                             for tag, attrs in doc.tags))


if __name__ == "__main__":
    unittest.main()
