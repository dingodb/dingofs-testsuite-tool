import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shlex


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / 'scripts' / 'mlperf_benchmark.py'


FAKE_MLP = '''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['DTT_TEST_CALLS'], 'a') as f: f.write(json.dumps(args) + '\\n')
kind = args[1]
results = pathlib.Path(args[args.index('--results-dir') + 1])
if kind == 'datagen': sys.exit(0)
if os.environ.get('DTT_TEST_FAIL') == 'run': sys.exit(7)
leaf = results / 'training' / 'resnet50' / 'run' / '20231118_120000'
leaf.mkdir(parents=True)
epoch = int(next(x.split('=', 1)[1] for x in args if x.startswith('train.epochs=')))
metric = {'train_throughput_samples_per_second': [12.5] * epoch,
          'train_throughput_mean_samples_per_second': 12.5,
          'train_au_percentage': [87.5] * epoch,
          'train_au_mean_percentage': 87.5,
          'train_io_mean_MB_per_second': 120.0}
if os.environ.get('DTT_TEST_BAD') == 'zero': metric['train_throughput_mean_samples_per_second'] = 0
if os.environ.get('DTT_TEST_BAD') == 'nonfinite': metric['train_au_mean_percentage'] = float('nan')
if os.environ.get('DTT_TEST_BAD') == 'missing': metric.pop('train_throughput_mean_samples_per_second')
summary = {'num_accelerators': int(args[args.index('--num-accelerators') + 1]),
           'hostname': 'test', 'metric': metric, 'start': '2023-11-18T12:00:00',
           'end': '2023-11-18T12:00:02', 'epochs': epoch}
if os.environ.get('DTT_TEST_BAD') == 'epochs': summary['epochs'] -= 1
(leaf / 'summary.json').write_text(json.dumps(summary))
model = 'unet3d' if os.environ.get('DTT_TEST_BAD') == 'wrongmodel' else args[args.index('--model') + 1]
count = 999 if os.environ.get('DTT_TEST_BAD') == 'wrongcount' else int(next(x.split('=', 1)[1] for x in args if x.startswith('dataset.num_files_train=')))
metadata = {'args': {'model': model, 'num_accelerators': summary['num_accelerators'],
                     'accelerator_type': args[args.index('--accelerator-type') + 1],
                     'data_dir': args[args.index('--data-dir') + 1],
                     'results_dir': str(results), 'loops': int(args[args.index('--loops') + 1])},
            'params_dict': {'dataset.num_files_train': count, 'train.epochs': epoch},
            'benchmark_type': 'training'}
(leaf / 'training_20231118_120000_metadata.json').write_text(json.dumps(metadata))
stats = {str(i): {'start': '2023-11-18T12:00:00', 'end': '2023-11-18T12:00:01',
                  'duration': '1.00'} for i in range(1, epoch + 1)}
if os.environ.get('DTT_TEST_DURATION'):
    if os.environ['DTT_TEST_DURATION'] == 'missing': stats['1'].pop('duration')
    else: stats['1']['duration'] = os.environ['DTT_TEST_DURATION']
(leaf / '0_per_epoch_stats.json').write_text(json.dumps(stats))
if os.environ.get('DTT_TEST_BAD') == 'duplicate':
    other = results / 'training' / 'resnet50' / 'run' / '20231118_120001'
    other.mkdir(parents=True)
    (other / 'summary.json').write_text(json.dumps(summary))
'''


class MlperfBenchmarkTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='dtt-mlperf-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.mount = self.root / 'mount'
        self.output = self.root / 'output'
        self.calls = self.root / 'calls.jsonl'
        self.binary = self.root / 'mlpstorage'
        self.binary.write_text(FAKE_MLP)
        self.binary.chmod(0o755)
        self.env = dict(os.environ, DTT_MLPSTORAGE_BIN=str(self.binary), DTT_TEST_CALLS=str(self.calls))

    def adapter(self, *options, env=None):
        return subprocess.run([sys.executable, str(ADAPTER), '--mount', str(self.mount),
                               '--output', str(self.output), '--file-count', '4', *options],
                              text=True, capture_output=True, env=env or self.env)

    def test_dry_run_is_pure_json_and_has_normalized_plan(self):
        result = self.adapter('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual({key: plan[key] for key in ('format', 'tool', 'mlperf_model',
                         'mlperf_epochs', 'mlperf_accelerators', 'concurrency',
                         'file_size', 'file_count', 'total_size', 'rounds',
                         'rw', 'direct', 'block_size', 'iodepth', 'read_percent')},
                         {'format': 'dtt-mlperf-v1', 'tool': 'mlperf', 'mlperf_model': 'resnet50',
                          'mlperf_epochs': 5, 'mlperf_accelerators': 1, 'concurrency': 4,
                          'file_size': '143439748', 'file_count': 4,
                          'total_size': '573758992', 'rounds': 1, 'rw': 'read',
                          'direct': False, 'block_size': 0, 'iodepth': 1,
                          'read_percent': None})
        self.assertFalse(self.mount.exists())
        self.assertFalse(self.output.exists())
        self.assertFalse(self.calls.exists())

    def test_invalid_model_epoch_count_and_runtime_are_rejected(self):
        for extra in (('--mlperf-model', 'bad'), ('--mlperf-epochs', '0'),
                      ('--mlperf-epochs', '1.5'), ('--file-count', '3', '--mlperf-accelerators', '2'),
                      ('--runtime-seconds', '5')):
            with self.subTest(extra=extra):
                result = self.adapter('--dry-run', *extra)
                self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(self.calls.exists())

    def test_native_rounds_have_distinct_results_and_raw_evidence(self):
        self.mount.mkdir()
        self.output.mkdir()
        result = self.adapter('--mlperf-epochs', '2', '--rounds', '2')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary_path = next(self.output.glob('performance-mlperf-*/summary.json'))
        report = json.loads(summary_path.read_text())
        self.assertEqual(report['status'], 'passed')
        self.assertTrue(report['statistics']['complete'])
        self.assertEqual(report['statistics']['successful_rounds'], 2)
        self.assertEqual(report['statistics']['metrics']['samples_per_second']['mean'], 12.5)
        self.assertEqual(report['rounds'][0]['metrics']['accelerator_utilization_percent'], 87.5)
        self.assertEqual(report['rounds'][0]['metrics']['measurement_seconds'], 2.0)
        self.assertNotEqual(report['rounds'][0]['native_reports'], report['rounds'][1]['native_reports'])
        for row in report['rounds']:
            for path in row['native_reports']:
                self.assertTrue((summary_path.parent / path).is_file())
        self.assertTrue((summary_path.parent / 'index.html').is_file())
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual([call[1] for call in calls], ['datagen', 'run', 'run'])
        self.assertIn('--open', calls[1])
        self.assertIn('--allow-invalid-params', calls[1])
        self.assertEqual(calls[1][calls[1].index('--loops') + 1], '1')
        self.assertGreater(int(calls[1][calls[1].index('--client-host-memory-in-gb') + 1]), 0)

    def test_zero_rounded_epoch_duration_keeps_valid_round_without_measurement(self):
        self.mount.mkdir()
        self.output.mkdir()
        result = self.adapter('--mlperf-epochs', '2', env=dict(self.env, DTT_TEST_DURATION='0.00'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(next(self.output.glob('performance-mlperf-*/summary.json')).read_text())
        self.assertEqual(report['status'], 'passed')
        self.assertTrue(report['statistics']['complete'])
        self.assertEqual(report['rounds'][0]['metrics']['samples_per_second'], 12.5)
        self.assertNotIn('measurement_seconds', report['rounds'][0]['metrics'])
        self.assertNotIn('measurement_seconds', report['statistics']['metrics'])

    def test_missing_negative_and_nonfinite_epoch_duration_still_fail(self):
        for value in ('missing', '-0.01', 'nan', 'inf'):
            with self.subTest(duration=value):
                temp = tempfile.TemporaryDirectory()
                self.addCleanup(temp.cleanup)
                self.output = Path(temp.name)
                self.mount.mkdir(exist_ok=True)
                result = self.adapter('--mlperf-epochs', '2',
                                      env=dict(self.env, DTT_TEST_DURATION=value))
                self.assertNotEqual(result.returncode, 0)
                report = json.loads(next(self.output.glob('performance-mlperf-*/summary.json')).read_text())
                self.assertEqual(report['status'], 'failed')

    def test_invalid_native_metrics_epochs_or_duplicate_summary_fail(self):
        for bad in ('zero', 'nonfinite', 'missing', 'epochs', 'duplicate', 'wrongmodel', 'wrongcount'):
            with self.subTest(bad=bad):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                self.output = Path(tmp.name)
                self.mount.mkdir(exist_ok=True)
                env = dict(self.env, DTT_TEST_BAD=bad)
                result = self.adapter(env=env)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                report = json.loads(next(self.output.glob('performance-mlperf-*/summary.json')).read_text())
                self.assertEqual(report['status'], 'failed')
                self.assertFalse(report['statistics']['complete'])

    def test_failed_run_retains_partial_report_and_log(self):
        self.mount.mkdir()
        self.output.mkdir()
        result = self.adapter(env=dict(self.env, DTT_TEST_FAIL='run'))
        self.assertNotEqual(result.returncode, 0)
        report_path = next(self.output.glob('performance-mlperf-*/summary.json'))
        report = json.loads(report_path.read_text())
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['rounds'][0]['status'], 'failed')
        self.assertTrue(list(report_path.parent.glob('round-001*.log')))

    def test_wrapper_routes_benchmark_without_tty_and_forwards_all_fields(self):
        self.mount.mkdir()
        config = self.root / 'config'
        config.mkdir()
        runtime = self.root / 'runtime'
        recorded = self.root / 'runtime.json'
        runtime.write_text('#!/usr/bin/env python3\nimport json, pathlib, sys\n'
                           f'pathlib.Path({str(recorded)!r}).write_text(json.dumps(sys.argv[1:]))\n'
                           'print(json.dumps({"format":"dtt-mlperf-v1"}))\n')
        runtime.chmod(0o755)
        for key, value in {'image': 'test-image', 'testdir': self.mount,
                           'output': self.output, 'runtime': runtime}.items():
            (config / key).write_text(str(value) + '\n')
        options = ['-t', 'mlperf', '-s', 'benchmark', '--mlperf-model', 'unet3d',
                   '--mlperf-epochs', '3', '--mlperf-accelerators', '2',
                   '--concurrency', '5', '--file-count', '14', '--rounds', '2']
        command = (f'export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}\n'
                   f'source {shlex.quote(str(ROOT / "dingofs-testsuite-tool"))}\n'
                   '_is_rootless() { return 0; }\n'
                   f'dingofs-testsuite-tool {shlex.join(options)}')
        result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'format': 'dtt-mlperf-v1'})
        argv = json.loads(recorded.read_text())
        self.assertNotIn('-it', argv)
        self.assertEqual(argv[argv.index('--mlperf-model') + 1], 'unet3d')
        self.assertEqual(argv[argv.index('--mlperf-epochs') + 1], '3')
        self.assertEqual(argv[argv.index('--mlperf-accelerators') + 1], '2')
        self.assertEqual(argv[argv.index('--concurrency') + 1], '5')
        self.assertEqual(argv[argv.index('--file-count') + 1], '14')
        self.assertEqual(argv[argv.index('--rounds') + 1], '2')

    def test_wrapper_dry_run_needs_no_image_or_runtime(self):
        config = self.root / 'config'
        config.mkdir()
        (config / 'testdir').write_text(str(self.mount) + '\n')
        (config / 'output').write_text(str(self.output) + '\n')
        command = (f'export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}\n'
                   f'source {shlex.quote(str(ROOT / "dingofs-testsuite-tool"))}\n'
                   'dingofs-testsuite-tool -t mlperf -s benchmark --file-count 4 --dry-run')
        result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['format'], 'dtt-mlperf-v1')
        self.assertFalse(self.mount.exists())
        self.assertFalse(self.output.exists())

    def test_entrypoint_routes_benchmark_to_adapter_with_pure_dry_run(self):
        runner = self.root / 'runner.py'
        recorded = self.root / 'entrypoint.json'
        runner.write_text('import json, pathlib, sys\n'
                          f'pathlib.Path({str(recorded)!r}).write_text(json.dumps(sys.argv[1:]))\n'
                          'print(json.dumps({"format":"dtt-mlperf-v1"}))\n')
        harness = self.root / 'harness.sh'
        harness.write_text('export DTT_ENTRYPOINT_SOURCE_ONLY=1\n'
                           f'source {shlex.quote(str(ROOT / "entrypoint.sh"))}\n'
                           'unset DTT_ENTRYPOINT_SOURCE_ONLY\nmain "$@"\n')
        result = subprocess.run(['bash', str(harness), '-t', 'mlperf', '-s', 'benchmark',
                                 '-m', str(self.mount), '-o', str(self.output),
                                 '--mlperf-model', 'unet3d', '--mlperf-epochs', '3',
                                 '--mlperf-accelerators', '2', '--concurrency', '5',
                                 '--file-count', '14', '--rounds', '2', '--dry-run'],
                                capture_output=True, text=True,
                                env=dict(self.env, DTT_MLPERF_RUNNER=str(runner)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'format': 'dtt-mlperf-v1'})
        argv = json.loads(recorded.read_text())
        self.assertEqual(argv[argv.index('--mlperf-model') + 1], 'unet3d')
        self.assertEqual(argv[argv.index('--file-count') + 1], '14')
        self.assertIn('--dry-run', argv)
        self.assertFalse(self.mount.exists())
        self.assertFalse(self.output.exists())

    def test_legacy_scenario_rejects_new_file_count_instead_of_ignoring_it(self):
        config = self.root / 'config'
        config.mkdir()
        for key, value in {'image': 'test-image', 'testdir': self.mount,
                           'output': self.output}.items():
            (config / key).write_text(str(value) + '\n')
        command = (f'export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}\n'
                   f'source {shlex.quote(str(ROOT / "dingofs-testsuite-tool"))}\n'
                   'dingofs-testsuite-tool -t mlperf -s resnet50 --file-count 4')
        wrapper = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
        self.assertNotEqual(wrapper.returncode, 0)
        harness = (f'export DTT_ENTRYPOINT_SOURCE_ONLY=1\n'
                   f'source {shlex.quote(str(ROOT / "entrypoint.sh"))}\n'
                   'parse_args -t mlperf -s resnet50 --file-count 4')
        entry = subprocess.run(['bash', '-c', harness], capture_output=True, text=True)
        self.assertNotEqual(entry.returncode, 0)


if __name__ == '__main__':
    unittest.main()
