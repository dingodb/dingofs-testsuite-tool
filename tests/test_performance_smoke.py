"""Opt-in tiny real-tool runs; only new TemporaryDirectory data is touched."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from performance_benchmark import execute
from performance_plan import build_plan, parser


@unittest.skipUnless(os.environ.get('DTT_RUN_REAL_PERFORMANCE') == '1',
                     'set DTT_RUN_REAL_PERFORMANCE=1 to run local fio and elbencho')
class PerformanceRealSmokeTest(unittest.TestCase):
    def test_both_tools_all_modes_buffered_and_direct(self):
        for tool in ('fio', 'elbencho'):
            self.assertIsNotNone(shutil.which(os.environ.get('DTT_' + tool.upper() + '_BIN', tool)))
            for direct in ('0', '1'):
                for mode in ('write', 'read', 'randwrite', 'randread', 'rw', 'randrw'):
                    with self.subTest(tool=tool, direct=direct, mode=mode):
                        with tempfile.TemporaryDirectory(prefix='dtt-perf-real-') as temp:
                            plan = build_plan(parser().parse_args([
                                '--tool', tool, '--mount', temp, '--output', temp,
                                '--rw', mode, '--direct', direct, '--concurrency', '2',
                                '--file-count', '4', '--file-size', '64K', '--block-size', '4K',
                                '--rounds', '2',
                            ]))
                            report = execute(plan, timeout=60)
                            self.assertEqual(report['status'], 'passed', report.get('error'))
                            self.assertEqual(report['statistics']['successful_rounds'], 2)
                            self.assertTrue(report['statistics']['complete'])
                            for row in report['rounds']:
                                self.assertEqual(row['metrics']['io_bytes'], 262144)
                                self.assertGreater(row['metrics']['bandwidth_mib_s'], 0)
                            rows = report['rounds']
                            self.assertAlmostEqual(report['statistics']['metrics']['bandwidth_mib_s']['mean'],
                                (rows[0]['metrics']['bandwidth_mib_s'] + rows[1]['metrics']['bandwidth_mib_s']) / 2)
                            path = Path(plan['output_dir'])
                            self.assertEqual(json.loads((path / 'summary.json').read_text())['status'], 'passed')
                            self.assertIn('逐轮结果', (path / 'index.html').read_text())

    def test_uneven_small_files_and_greater_queue_depth(self):
        for tool in ('fio', 'elbencho'):
            with self.subTest(tool=tool), tempfile.TemporaryDirectory(prefix='dtt-perf-real-') as temp:
                plan = build_plan(parser().parse_args([
                    '--tool', tool, '--mount', temp, '--output', temp, '--rw', 'read',
                    '--direct', '0', '--concurrency', '3', '--file-count', '5',
                    '--file-size', '128', '--block-size', '128', '--iodepth', '2',
                ]))
                report = execute(plan, timeout=60)
                self.assertEqual(report['status'], 'passed', report.get('error'))
                self.assertEqual(report['rounds'][0]['metrics']['io_bytes'], 640)


if __name__ == '__main__':
    unittest.main()
