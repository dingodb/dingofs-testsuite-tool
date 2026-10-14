import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from performance_benchmark import execute
from performance_plan import build_plan, parser


FAKE_FIO = r'''#!/usr/bin/env python3
import configparser, json, os, pathlib, subprocess, sys, time
if '--version' in sys.argv:
    print('fio-3.35-test')
    sys.exit(0)
out = pathlib.Path(next(a.split('=', 1)[1] for a in sys.argv if a.startswith('--output=')))
with open(os.environ['DTT_TEST_CALLS'], 'a') as f: f.write(out.stem + '\n')
if os.environ.get('DTT_TEST_CHILD_PID'):
    subprocess.Popen([sys.executable, '-c', "import os, pathlib, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); pathlib.Path(os.environ['DTT_TEST_CHILD_PID']).write_text(str(os.getpid())); time.sleep(30)"])
    while not pathlib.Path(os.environ['DTT_TEST_CHILD_PID']).exists(): time.sleep(0.01)
if os.environ.get('DTT_TEST_SLEEP'):
    pathlib.Path(os.environ['DTT_TEST_SLEEP']).write_text(str(os.getpid()))
    time.sleep(15)
if os.environ.get('DTT_TEST_FAIL') == out.stem:
    print('permission denied: sample target')
    sys.exit(7)
cfg = configparser.ConfigParser(interpolation=None)
cfg.read(sys.argv[1]); common = cfg['global']; data = pathlib.Path(common['directory'])
total = 0
for name in cfg.sections():
    if name == 'global': continue
    section = cfg[name]
    for index in range(int(section['nrfiles'])):
        file = data / section['filename_format'].replace('$filenum', str(index))
        if common['rw'] in ('read', 'randread'):
            if not file.exists(): sys.exit(99)
        else:
            with file.open('wb') as f: f.truncate(int(common['filesize']))
        total += file.stat().st_size
round_number = int(out.stem.split('-')[-1]) if out.stem.startswith('round-') else 9
direction = 'read' if common['rw'] in ('read', 'randread') else 'write'
observed = total - 4096 if os.environ.get('DTT_TEST_SHORT') else total
out.write_text(json.dumps({'jobs': [{'error': 0, direction: {
    'io_bytes': observed, 'bw_bytes': round_number * 100 * 1048576,
    'iops': round_number * 1000, 'total_ios': observed // int(common['bs']),
    'lat_ns': {'mean': 2000}
}}]}))
'''


class PerformanceRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='dtt-performance-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.mount = self.root / 'mount with space'
        self.mount.mkdir()
        self.output = self.root / 'reports'
        self.binary = self.root / 'fio'
        self.binary.write_text(FAKE_FIO)
        self.binary.chmod(0o755)
        self.calls = self.root / 'calls'
        self.environment = patch.dict(os.environ, {'DTT_FIO_BIN': str(self.binary), 'DTT_TEST_CALLS': str(self.calls)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def plan(self, *args):
        return build_plan(parser().parse_args([
            '--tool', 'fio', '--mount', str(self.mount), '--output', str(self.output),
            '--concurrency', '2', '--file-count', '5', '--file-size', '4K',
            '--block-size', '4K', *args]))

    def test_three_round_mean_excludes_read_preparation_and_retains_evidence(self):
        plan = self.plan('--rw', 'read', '--rounds', '3')
        report = execute(plan)
        self.assertEqual(report['status'], 'passed', report)
        self.assertEqual(self.calls.read_text().splitlines(), ['prepare', 'round-001', 'round-002', 'round-003'])
        self.assertEqual(report['statistics']['metrics']['bandwidth_mib_s']['mean'], 200)
        self.assertEqual(report['statistics']['successful_rounds'], 3)
        self.assertTrue(report['statistics']['complete'])
        output = Path(plan['output_dir'])
        self.assertTrue((output / 'index.html').is_file())
        self.assertEqual(json.loads((output / 'summary.json').read_text())['status'], 'passed')
        self.assertEqual(len(list(Path(plan['data_dir']).iterdir())), 5)
        self.assertTrue((output / 'round-003.command').is_file())

    def test_failed_round_stops_and_is_not_averaged(self):
        with patch.dict(os.environ, {'DTT_TEST_FAIL': 'round-002'}):
            report = execute(self.plan('--rounds', '3'))
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(self.calls.read_text().splitlines(), ['round-001', 'round-002'])
        self.assertEqual(report['statistics']['successful_rounds'], 1)
        self.assertEqual(report['statistics']['metrics']['bandwidth_mib_s']['mean'], 100)
        self.assertIn('permission denied', report['error'])
        self.assertIn('7', report['error'])
        self.assertFalse(report['statistics']['complete'])

    def test_short_io_cannot_produce_successful_report(self):
        with patch.dict(os.environ, {'DTT_TEST_SHORT': 'yes'}):
            report = execute(self.plan())
        self.assertEqual(report['status'], 'failed')
        self.assertIn('bytes', report['error'])
        self.assertEqual(report['statistics']['successful_rounds'], 0)

    def test_preparation_failure_does_not_start_read_round(self):
        with patch.dict(os.environ, {'DTT_TEST_FAIL': 'prepare'}):
            report = execute(self.plan('--rw', 'read'))
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['preparation']['status'], 'failed')
        self.assertEqual(report['rounds'], [])

    def test_existing_data_directory_is_not_reused_or_removed(self):
        plan = self.plan()
        path = Path(plan['data_dir'])
        path.mkdir(parents=True)
        marker = path / 'user-data'
        marker.write_text('keep me')
        report = execute(plan)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(marker.read_text(), 'keep me')
        self.assertFalse(self.calls.exists())

    def test_timeout_reports_failure_and_reaps_tool(self):
        pidfile = self.root / 'pid'
        with patch.dict(os.environ, {'DTT_TEST_SLEEP': str(pidfile)}):
            report = execute(self.plan(), timeout=0.3)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('timed out', report['error'])
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)

    def test_timeout_kills_descendant_even_when_group_leader_exits(self):
        import signal
        import time
        child_pid = self.root / 'child-pid'
        parent_pid = self.root / 'parent-pid'
        def cleanup_child():
            if child_pid.exists():
                try: os.kill(int(child_pid.read_text()), signal.SIGKILL)
                except ProcessLookupError: pass
        self.addCleanup(cleanup_child)
        with patch.dict(os.environ, {'DTT_TEST_SLEEP': str(parent_pid), 'DTT_TEST_CHILD_PID': str(child_pid)}):
            report = execute(self.plan(), timeout=0.5)
        self.assertEqual(report['status'], 'failed')
        pid = int(child_pid.read_text())
        for _ in range(30):
            status = Path('/proc/%d/stat' % pid)
            if not status.exists() or status.read_text().split()[2] == 'Z':
                return
            time.sleep(0.02)
        self.fail('tool descendant is still running after timeout')

    def test_cli_interrupt_works_when_background_shell_inherited_sigint_ignore(self):
        import signal
        import time
        pidfile = self.root / 'interrupt-tool-pid'
        environment = dict(os.environ, DTT_TEST_SLEEP=str(pidfile))
        process = subprocess.Popen([
            sys.executable, str(ROOT / 'scripts/performance_benchmark.py'), '--tool', 'fio',
            '--mount', str(self.mount), '--output', str(self.output),
            '--file-size', '4K', '--concurrency', '1',
        ], env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN))
        try:
            for _ in range(100):
                if pidfile.exists(): break
                time.sleep(0.02)
            self.assertTrue(pidfile.exists())
            process.send_signal(signal.SIGINT)
            try:
                result = process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.fail('runner ignored SIGINT inherited from a background shell')
            self.assertEqual(result, 130)
            summary = next(self.output.glob('performance-*/summary.json'))
            self.assertEqual(json.loads(summary.read_text())['status'], 'interrupted')
            with self.assertRaises(ProcessLookupError): os.kill(int(pidfile.read_text()), 0)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

    def test_dry_run_creates_neither_data_nor_report(self):
        result = subprocess.run([
            sys.executable, str(ROOT / 'scripts/performance_benchmark.py'), '--tool', 'fio',
            '--mount', str(self.mount), '--output', str(self.output), '--dry-run',
            '--file-size', '4K', '--concurrency', '1',
        ], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['total_size_bytes'], 4096)
        self.assertEqual(list(self.mount.iterdir()), [])
        self.assertFalse(self.output.exists())
        self.assertFalse(self.calls.exists())

    def test_cli_failure_returns_nonzero_and_prints_report_location(self):
        with patch.dict(os.environ, {'DTT_TEST_FAIL': 'round-001'}):
            result = subprocess.run([
                sys.executable, str(ROOT / 'scripts/performance_benchmark.py'), '--tool', 'fio',
                '--mount', str(self.mount), '--output', str(self.output),
                '--file-size', '4K', '--concurrency', '1',
            ], text=True, capture_output=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('index.html', result.stdout)


if __name__ == '__main__':
    unittest.main()
