import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import time
import unittest

import test_elbencho_cli

ROOT = Path(__file__).resolve().parents[1]


class PerformanceCliTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='dtt performance ')
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)
        self.mount = self.temp / 'mount with spaces'
        self.output = self.temp / 'output with spaces'
        self.mount.mkdir()
        self.output.mkdir()

    def wrapper(self, options, entry_function="dingofs-testsuite-tool", side_effects=None):
        config = self.temp / 'config'
        config.mkdir(exist_ok=True)
        recorded = self.temp / 'runtime-args.json'
        # Runtime paths historically allow a command plus arguments, so use a
        # space-free executable while testing user-controlled mount paths.
        bin_dir = tempfile.TemporaryDirectory(prefix='dtt-runtime-')
        self.addCleanup(bin_dir.cleanup)
        runtime = Path(bin_dir.name) / 'runtime'
        runtime.write_text('#!/usr/bin/env python3\nimport json, pathlib, sys\n'
                           f'pathlib.Path({str(recorded)!r}).write_text(json.dumps(sys.argv[1:]))\n')
        runtime.chmod(0o755)
        for key, value in {'image': 'test-image', 'testdir': self.mount,
                           'output': self.output, 'runtime': runtime}.items():
            (config / key).write_text(str(value) + '\n')
        hooks = ''
        if side_effects is not None:
            side_effects.unlink(missing_ok=True)
            for name in ('_run_setup_env', 'cmd_setup_env', 'cmd_cleanup_env',
                         'prepare_tool_ai_runtime', 'finalize_tool_ai_runtime'):
                hooks += (f'{name}() {{ echo {name} >> '
                          f'{shlex.quote(str(side_effects))}; return 97; }}\n')
        command = (f'export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}\n'
                   f'source {shlex.quote(str(ROOT / "dingofs-testsuite-tool"))}\n'
                   '_is_rootless() { return 0; }\n' + hooks +
                   f'{entry_function} {shlex.join(options)}')
        result = subprocess.run(['bash', '-c', command], text=True, capture_output=True)
        argv = json.loads(recorded.read_text()) if recorded.exists() else []
        return result, argv

    def entrypoint(self, options, exit_code=0, notifications=False, real_logging=False):
        recorded = self.temp / 'runner-args.json'
        runner = self.temp / 'fake runner.py'
        runner.write_text('import json, pathlib, sys\n'
                          f'pathlib.Path({str(recorded)!r}).write_text(json.dumps(sys.argv[1:]))\n'
                          f'sys.exit({exit_code})\n')
        events = self.temp / 'events'
        harness = self.temp / 'entrypoint harness.sh'
        harness.write_text(
            'export DTT_ENTRYPOINT_SOURCE_ONLY=1\n'
            f'source {shlex.quote(str(ROOT / "entrypoint.sh"))}\n'
            'unset DTT_ENTRYPOINT_SOURCE_ONLY\n' +
            ('' if real_logging else f'log_result() {{ printf "log:%s\\n" "$3" >> {shlex.quote(str(events))}; }}\n') +
            f'send_wechat_notification() {{ echo wechat >> {shlex.quote(str(events))}; }}\n'
            f'send_email_notification() {{ echo email >> {shlex.quote(str(events))}; }}\n'
            'main "$@"\n')
        env = dict(os.environ, DTT_PERFORMANCE_RUNNER=str(runner),
                   WECHAT='yes' if notifications else 'no',
                   EMAIL='yes' if notifications else 'no', DTT_AI_ENABLED='0')
        result = subprocess.run(['bash', str(harness), '-m', str(self.mount),
                                 '-o', str(self.output), *options],
                                text=True, capture_output=True, env=env)
        argv = json.loads(recorded.read_text()) if recorded.exists() else []
        return result, argv, events.read_text().splitlines() if events.exists() else []

    def test_common_help_is_available_for_both_tools(self):
        for tool in ('fio', 'elbencho'):
            with self.subTest(tool=tool):
                result, _ = self.wrapper(['-t', tool, '--help'])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('--concurrency', result.stdout)
                self.assertIn('--total-size', result.stdout)
                self.assertIn('--dry-run', result.stdout)

    def test_no_scenario_selects_benchmark_and_preserves_mount_boundaries(self):
        for tool in ('fio', 'elbencho'):
            with self.subTest(tool=tool):
                result, argv = self.wrapper(['-t', tool])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(argv[argv.index('-s') + 1], 'benchmark')
                self.assertIn(f'{self.mount}:/data', argv)
                self.assertIn(f'{self.output}:/output', argv)
                self.assertEqual(argv[argv.index('-m') + 1], '/data')

    def test_common_options_reach_both_tools_without_becoming_per_worker_counts(self):
        for tool in ('fio', 'elbencho'):
            with self.subTest(tool=tool):
                expected = ['--direct', '0', '--concurrency', '3', '--file-size', '8MiB',
                            '--file-count', '7', '--total-size', '56MiB',
                            '--block-size', '4KiB', '--rw', 'randrw', '--rounds', '2',
                            '--iodepth', '8', '--read-percent', '70', '--dry-run']
                result, argv = self.wrapper(['-t', tool, '-s', 'benchmark', *expected])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(argv[argv.index('--direct'):], expected)

    def test_new_options_translate_legacy_direction_to_one_benchmark(self):
        for scene, mode in [('seq_read', 'read'), ('seq_write', 'write'),
                            ('rand_read', 'randread'), ('rand_write', 'randwrite')]:
            with self.subTest(scene=scene):
                result, argv = self.wrapper(['--concurrency', '2', '-t', 'fio', '-s', scene])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(argv[argv.index('-s') + 1], 'benchmark')
                self.assertEqual(argv[argv.index('--rw') + 1], mode)

    def test_fio_file_count_activates_global_benchmark_route(self):
        result, argv = self.wrapper(['-t', 'fio', '-s', 'seq_write', '--file-count', '3'])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(argv[argv.index('-s') + 1], 'benchmark')
        self.assertEqual(argv[argv.index('--file-count') + 1], '3')

    def test_benchmark_aliases_are_canonicalized(self):
        for option in ('--numjobs', '--threads'):
            with self.subTest(option=option):
                result, argv = self.wrapper(['-t', 'fio', option, '3', '--operation', 'read'])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(argv[argv.index('--concurrency') + 1], '3')
                self.assertEqual(argv[argv.index('--rw') + 1], 'read')
                self.assertNotIn(option, argv)
                self.assertNotIn('--operation', argv)

    def test_invalid_and_conflicting_options_fail_before_runtime(self):
        cases = [
            ['--concurrency', '0'], ['--rounds', '-1'], ['--iodepth', '0'],
            ['--file-count', '0'], ['--rw', 'delete'], ['--read-percent', '101'],
            ['--read-percent', '-1'], ['--direct', '2'], ['--operation', 'delete'],
            ['--concurrency', '2', '--numjobs', '3'],
            ['--threads', '2', '--numjobs', '3'], ['--rw', 'read', '--operation', 'write'],
            ['-s', 'seq_read', '--rw', 'write'], ['-s', 'small', '--dry-run'],
            ['-s', 'custom', '--rounds', '2'], ['-s', 'all', '--concurrency', '2'],
            ['-s', 'ai-storage-t03-read', '--dry-run'], ['--dir-count', '2'],
        ]
        for options in cases:
            with self.subTest(options=options):
                result, argv = self.wrapper(['-t', 'fio', *options])
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(argv, [])

    def test_missing_values_fail_before_runtime(self):
        for option in ('--concurrency', '--total-size', '--rw', '--rounds', '--iodepth',
                       '--read-percent', '--numjobs', '--direct', '--file-count'):
            with self.subTest(option=option):
                result, argv = self.wrapper(['-t', 'fio', option])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(argv, [])
                self.assertIn('requires a value', result.stdout + result.stderr)

    def test_entrypoint_rejects_empty_option_values(self):
        for option in ('--concurrency', '--total-size', '--rw', '--rounds', '--iodepth',
                       '--read-percent', '--numjobs', '--direct', '--file-count'):
            with self.subTest(option=option):
                result, argv, events = self.entrypoint(['-t', 'fio', option, ''])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(argv, [])
                self.assertEqual(events, [])

    def test_entrypoint_dispatches_canonical_options_and_propagates_failure(self):
        options = ['--direct', '0', '--concurrency', '3', '--file-size', '8MiB',
                   '--file-count', '7', '--total-size', '56MiB', '--block-size', '4KiB',
                   '--rw', 'randrw', '--rounds', '2', '--iodepth', '8', '--read-percent', '70']
        result, argv, events = self.entrypoint(['-t', 'fio', *options], exit_code=17)
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertEqual(argv, ['--tool', 'fio', '--mount', str(self.mount),
                                '--output', str(self.output), *options])
        self.assertEqual(events, ['log:17'])

    def test_successful_fio_benchmark_is_logged_successfully(self):
        result, _, _ = self.entrypoint(['-t', 'fio'], real_logging=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result_log = (self.output / 'result.log').read_text()
        self.assertIn('Status: SUCCESS', result_log)
        self.assertNotIn('Status: FAIL', result_log)

    def test_dry_run_rejects_environment_and_ai_actions_before_dispatch(self):
        actions = [
            ['--setup-env', 'test-env'], ['--setup-env', 'test-env', '--cleanup'],
            ['--cleanup-env', 'test-env'], ['--ai-analysis'],
        ]
        for entry_function in ('dingofs-testsuite-tool', 'run_testsuite'):
            for action in actions:
                for options in ([*action, '-t', 'fio', '--dry-run'],
                                ['--dry-run', '-t', 'fio', *action]):
                    with self.subTest(entry_function=entry_function, options=options):
                        events = self.temp / 'side-effect-events'
                        result, argv = self.wrapper(options, entry_function, events)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertFalse(events.exists(), 'dry-run invoked an external action')
                        self.assertEqual(argv, [])
                        self.assertIn('--dry-run', result.stdout + result.stderr)

    def test_entrypoint_forwards_stop_signals_and_reaps_runner(self):
        for stop_signal in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(stop_signal=stop_signal):
                ready = self.temp / f'runner-{stop_signal}.pid'
                marker = self.temp / f'runner-{stop_signal}.interrupted'
                runner = self.temp / f'long-runner-{stop_signal}.py'
                runner.write_text(
                    'import os, pathlib, signal, sys, time\n'
                    'def interrupted(signum, frame):\n'
                    f'    pathlib.Path({str(marker)!r}).write_text(str(signum))\n'
                    '    time.sleep(0.15)\n'
                    '    sys.exit(130)\n'
                    'signal.signal(signal.SIGTERM, interrupted)\n'
                    'signal.signal(signal.SIGINT, interrupted)\n'
                    f'pathlib.Path({str(ready)!r}).write_text(str(os.getpid()))\n'
                    'while True: signal.pause()\n')
                env = dict(os.environ, DTT_PERFORMANCE_RUNNER=str(runner),
                           WECHAT='no', EMAIL='no', DTT_AI_ENABLED='0')
                process = subprocess.Popen(
                    ['bash', str(ROOT / 'entrypoint.sh'), '-t', 'fio',
                     '-m', str(self.mount), '-o', str(self.output)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    env=env, start_new_session=True)
                try:
                    deadline = time.monotonic() + 5
                    while not ready.exists() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(ready.exists(), 'runner did not become ready')
                    runner_pid = int(ready.read_text())
                    process.send_signal(stop_signal)
                    try:
                        stdout, stderr = process.communicate(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.fail('entrypoint did not forward the signal and reap its runner')
                    self.assertEqual(process.returncode, 130, stdout + stderr)
                    self.assertEqual(marker.read_text(), str(stop_signal))
                    with self.assertRaises(ProcessLookupError):
                        os.kill(runner_pid, 0)
                finally:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.communicate(timeout=3)

    def test_entrypoint_dry_run_never_logs_or_notifies(self):
        result, argv, events = self.entrypoint(['-t', 'elbencho', '--dry-run'], notifications=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('--dry-run', argv)
        self.assertEqual(events, [])
        self.assertEqual(list(self.mount.iterdir()), [])
        self.assertEqual(list(self.output.iterdir()), [])

    def test_entrypoint_rejects_invalid_options_before_runner(self):
        for options in (['--concurrency', '0'], ['--rw', 'delete'],
                        ['-s', 'seq_read', '--rw', 'write'],
                        ['--concurrency', '2', '--threads', '3']):
            with self.subTest(options=options):
                result, argv, events = self.entrypoint(['-t', 'elbencho', *options])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(argv, [])
                self.assertEqual(events, [])

    def test_script_scenarios_reject_direct_instead_of_ignoring_it(self):
        for scene in ('small', 'full', 'custom'):
            with self.subTest(scene=scene):
                result, argv = self.wrapper(['-t', 'elbencho', '-s', scene, '--direct', '0'])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(argv, [])
                self.assertIn('benchmark', result.stdout + result.stderr)
        helper = test_elbencho_cli.ElbenchoCliTest()
        result, argv = helper._run_small_entrypoint('--direct 0')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(argv, [])
        self.assertIn('benchmark', result.stdout + result.stderr)

    def test_legacy_elbencho_honors_buffered_io(self):
        helper = test_elbencho_cli.ElbenchoCliTest()
        result, calls = helper._run_entrypoint('--direct 0', scenario='seq_write')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('--direct', calls[0])
        result, argv = self.wrapper(['-t', 'elbencho', '-s', 'seq_write', '--direct', '0'])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(argv[argv.index('--direct') + 1], '0')


    def test_managed_performance_runtime_overrides_old_image_scripts(self):
        from unittest.mock import patch
        runtime = self.temp / 'performance runtime'
        runtime.mkdir()
        names = ['entrypoint.sh', 'performance_benchmark.py', 'performance_plan.py', 'performance_report.py', 'performance_tools.py']
        for name in names: (runtime / name).write_text('fixture')
        with patch.dict(os.environ, DTT_PERFORMANCE_RUNTIME_DIR=str(runtime)):
            result, argv = self.wrapper(['-t', 'fio', '-s', 'benchmark'])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in names:
            target = '/entrypoint.sh' if name == 'entrypoint.sh' else '/scripts/' + name
            self.assertIn(str(runtime / name) + ':' + target + ':ro', argv)


if __name__ == '__main__':
    unittest.main()
