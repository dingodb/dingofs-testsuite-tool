from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("performance_tools", ROOT / "scripts/performance_tools.py")
MODULE = importlib.util.module_from_spec(SPEC) if SPEC else None
if SPEC and Path(SPEC.origin).exists():
    SPEC.loader.exec_module(MODULE)
parse_metrics = getattr(MODULE, "parse_metrics", None)
FIXTURES = ROOT / "tests/fixtures/performance"


class PerformanceToolsTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(parse_metrics), "performance metric parser is not implemented")

    def parse(self, tool, data, mode):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text(data if isinstance(data, str) else json.dumps(data))
            return parse_metrics(tool, path, mode)

    def test_real_fio_mixed_output_keeps_both_directions_and_weighted_latency(self):
        result = parse_metrics("fio", FIXTURES / "fio-rand-mixed.json", "randrw")
        self.assertEqual(result["io_bytes"], 524288)
        self.assertAlmostEqual(result["read_mib_s"], 74.21875)
        self.assertAlmostEqual(result["write_mib_s"], 92.4479160309)
        self.assertAlmostEqual(result["bandwidth_mib_s"], 166.6666660309)
        self.assertAlmostEqual(result["iops"], 42666.666667)
        self.assertAlmostEqual(result["latency_mean_us"], 41.057078125, places=6)

    def test_real_elbencho_mixed_output_reads_nested_counters(self):
        result = parse_metrics("elbencho", FIXTURES / "elbencho-rand-mixed.json", "randrw")
        self.assertEqual(result["io_bytes"], 524288)
        self.assertAlmostEqual(result["bandwidth_mib_s"], 203.3346881866)
        self.assertEqual(result["iops"], 52053)
        self.assertAlmostEqual(result["latency_mean_us"], 36.7734375)
        self.assertGreater(result["read_mib_s"], result["write_mib_s"])

    def test_real_pure_modes_have_only_the_requested_direction(self):
        for tool in ("fio", "elbencho"):
            for mode, other in (("read", "write"), ("write", "read")):
                with self.subTest(tool=tool, mode=mode):
                    result = parse_metrics(tool, FIXTURES / f"{tool}-seq-{mode}.json", mode)
                    self.assertEqual(result["io_bytes"], 524288)
                    self.assertEqual(result[other + "_mib_s"], 0)
                    self.assertGreater(result[mode + "_mib_s"], 0)
                    self.assertGreater(result["iops"], 0)
                    self.assertGreater(result["latency_mean_us"], 0)

    def test_fio_job_error_or_partial_io_is_not_success(self):
        original = json.loads((FIXTURES / "fio-seq-write.json").read_text())
        for key, value in (("error", 5), ("short_ios", 1), ("drop_ios", 1)):
            data = deepcopy(original)
            target = data["jobs"][0] if key == "error" else data["jobs"][0]["write"]
            target[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.parse("fio", data, "write")

    def test_fio_falls_back_to_kib_bandwidth_and_weighted_job_latencies(self):
        jobs = [
            {"error": 0, "read": {"io_bytes": 4096, "bw": 1024, "iops": 1, "total_ios": 1, "lat_ns": {"mean": 1000}}},
            {"error": 0, "read": {"io_bytes": 12288, "bw": 2048, "iops": 3, "total_ios": 3, "lat_ns": {"mean": 9000}}},
        ]
        result = self.parse("fio", {"jobs": jobs}, "read")
        self.assertEqual(result["bandwidth_mib_s"], 3)
        self.assertEqual(result["iops"], 4)
        self.assertEqual(result["latency_mean_us"], 7)

    def test_missing_latency_is_unknown(self):
        result = self.parse("fio", {"jobs": [{"error": 0, "read": {"io_bytes": 4096, "bw_bytes": 4096, "iops": 1}}]}, "read")
        self.assertIsNone(result["latency_mean_us"])

    def test_metadata_phase_does_not_replace_elbencho_data_metrics(self):
        data = (FIXTURES / "elbencho-seq-write.json").read_text()
        result = self.parse("elbencho", '{"phase_type":"MKDIRS","last_done":{"entries":"4"}}\n' + data, "write")
        self.assertEqual(result["io_bytes"], 524288)
        with self.assertRaises(ValueError):
            self.parse("elbencho", data + data, "write")

    def test_zero_one_direction_is_valid_for_small_mixed_workload(self):
        data = {"phase_type": "RWMIX50", "config": {"block_size": "4096"}, "last_done": {"rwmix_read": {"bytes": "4096", "bytes/s": "4096", "iops": "1"}}}
        result = self.parse("elbencho", data, "randrw")
        self.assertEqual(result["io_bytes"], 4096)
        self.assertEqual(result["write_mib_s"], 0)

    def test_invalid_or_missing_result_metrics_fail(self):
        for tool, data, mode in (
            ("fio", "{", "read"), ("fio", {}, "read"),
            ("fio", {"jobs": []}, "read"),
            ("fio", {"jobs": [{"error": 0}]}, "read"),
            ("fio", {"jobs": [{"error": 0, "read": {"io_bytes": 0}}]}, "read"),
            ("elbencho", {}, "read"),
            ("elbencho", {"phase_type": "WRITE", "last_done": {"bytes": "4096"}}, "read"),
            ("elbencho", {"phase_type": "READ", "last_done": {"bytes": "4096"}}, "read"),
        ):
            with self.subTest(tool=tool, data=data), self.assertRaises(ValueError):
                self.parse(tool, data, mode)

    def test_integer_byte_counts_preserve_precision(self):
        data = {"jobs": [{"error": 0, "read": {"io_bytes": 9007199254740993, "bw_bytes": 4096, "iops": 1}}]}
        self.assertEqual(self.parse("fio", data, "read")["io_bytes"], 9007199254740993)

    def test_native_measurement_duration_is_reported_for_both_tools(self):
        fio = self.parse('fio', json.loads((FIXTURES / 'fio-seq-write.json').read_text()), 'write')
        elbencho = self.parse('elbencho', (FIXTURES / 'elbencho-seq-write.json').read_text(), 'write')
        self.assertAlmostEqual(fio['measurement_seconds'], 0.006)
        self.assertAlmostEqual(elbencho['measurement_seconds'], 0.004)

    def test_timed_fio_requires_every_expected_worker_and_uses_shortest_duration(self):
        original = json.loads((FIXTURES / 'fio-seq-write.json').read_text())['jobs'][0]
        first = deepcopy(original)
        first['jobname'] = 'worker-0'
        first['write']['runtime'] = 60000
        second = deepcopy(original)
        second['jobname'] = 'worker-1'
        second['write']['runtime'] = 1000
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fio.json'
            path.write_text(json.dumps({'jobs': [first, second]}))
            result = parse_metrics('fio', path, 'write', expected_workers=2)
            self.assertEqual(result['measurement_seconds'], 1)
            for change in ('zero', 'missing', 'duplicate'):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    rows = deepcopy([first, second])
                    if change == 'zero':
                        rows[1]['write']['io_bytes'] = 0
                    elif change == 'missing':
                        rows.pop()
                    else:
                        rows[1]['jobname'] = 'worker-0'
                    path.write_text(json.dumps({'jobs': rows}))
                    parse_metrics('fio', path, 'write', expected_workers=2)

    def test_invalid_native_measurement_duration_is_rejected(self):
        for tool, key, container in (('fio', 'runtime', 'write'), ('elbencho', 'elapsed_time_ms', 'last_done')):
            original = json.loads((FIXTURES / f'{tool}-seq-write.json').read_text())
            for value in (0, -1, True, 'nan'):
                with self.subTest(tool=tool, value=value):
                    data = deepcopy(original)
                    target = data['jobs'][0][container] if tool == 'fio' else data[container]
                    target[key] = value
                    with self.assertRaises(ValueError):
                        self.parse(tool, data, 'write')

    def test_invalid_latency_is_not_reported_as_unknown(self):
        for tool in ("fio", "elbencho"):
            data = json.loads((FIXTURES / f"{tool}-seq-write.json").read_text())
            if tool == "fio":
                data["jobs"][0]["write"]["lat_ns"]["mean"] = float("nan")
            else:
                data["last_done"]["latency"]["IO"]["avg_us"] = -1
            with self.subTest(tool=tool), self.assertRaises(ValueError):
                self.parse(tool, data, "write")

    def test_nonfinite_negative_or_fractional_metrics_are_rejected(self):
        for tool in ("fio", "elbencho"):
            original = json.loads((FIXTURES / f"{tool}-seq-write.json").read_text())
            keys = ("io_bytes", "bw_bytes", "iops") if tool == "fio" else ("bytes", "bytes/s", "iops")
            for key in keys:
                for value in (float("nan"), float("inf"), -1, True):
                    data = deepcopy(original)
                    target = data["jobs"][0]["write"] if tool == "fio" else data["last_done"]
                    target[key] = value
                    with self.subTest(tool=tool, key=key, value=value), self.assertRaises(ValueError):
                        self.parse(tool, data, "write")
            data = deepcopy(original)
            target = data["jobs"][0]["write"] if tool == "fio" else data["last_done"]
            target[keys[0]] = 1.5
            with self.assertRaises(ValueError):
                self.parse(tool, data, "write")


if __name__ == "__main__":
    unittest.main()
