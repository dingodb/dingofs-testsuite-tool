#!/usr/bin/env python3
"""Run bounded single-client benchmarks and retain per-round evidence."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time

from performance_plan import build_plan, build_step, parser
from performance_report import write_report
from performance_tools import parse_metrics


def run_process(argv, log, timeout):
    """Own the process group, including cleanup after timeout or interruption."""
    with Path(log).open('wb') as output:
        process = subprocess.Popen(argv, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        except BaseException as exc:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 2
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            # A leader may exit before its descendants. Give the whole group
            # a grace period, then terminate survivors independently of wait().
            while time.monotonic() < deadline:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if isinstance(exc, subprocess.TimeoutExpired):
                raise RuntimeError('tool timed out after %g seconds' % timeout) from None
            raise


def log_tail(path):
    with Path(path).open('rb') as file:
        file.seek(max(0, file.seek(0, 2) - 4096))
        return file.read().decode('utf-8', errors='replace').strip()


def validate_dataset(plan):
    count = 0
    for entry in os.scandir(plan['data_dir']):
        information = entry.stat(follow_symlinks=False)
        if not stat.S_ISREG(information.st_mode) or information.st_size != plan['file_size_bytes']:
            raise ValueError('dataset file type/size mismatch: ' + entry.name)
        count += 1
    if count != plan['file_count']:
        raise ValueError('dataset contains %d files, expected %d' % (count, plan['file_count']))


def run_step(plan, step, binary, timeout):
    row = dict(round=step['round'], phase=step['phase'], status='failed',
               error='', metrics={}, artifacts={})
    for key in ('result_path', 'log_path', 'command_path', 'config_path'):
        if key in step:
            label = {'result_path': 'json', 'log_path': 'log', 'command_path': 'command', 'config_path': 'config'}[key]
            row['artifacts'][label] = Path(step[key]).name
    argv = [binary, *step['argv'][1:]]
    start = time.monotonic()
    try:
        if 'config' in step:
            Path(step['config_path']).write_text(step['config'], encoding='utf-8')
        Path(step['command_path']).write_text(shlex.join(argv) + '\n', encoding='utf-8')
        print(('准备数据' if not step['measured'] else '测量第 %d/%d 轮' % (step['round'], plan['rounds'])) + '…', flush=True)
        result = run_process(argv, step['log_path'], timeout)
        row['elapsed_seconds'] = time.monotonic() - start
        row['returncode'] = result
        if result:
            raise RuntimeError('tool exited with %d: %s' % (result, log_tail(step['log_path'])))
        metrics = parse_metrics(plan['tool'], step['result_path'], 'write' if not step['measured'] else plan['mode'])
        if metrics['io_bytes'] != plan['total_size_bytes']:
            raise ValueError('incomplete I/O: %d bytes, expected %d bytes' % (metrics['io_bytes'], plan['total_size_bytes']))
        row['metrics'] = metrics
        if not step['measured'] or step['round'] == 1:
            validate_dataset(plan)
        row['status'] = 'passed'
    except KeyboardInterrupt:
        row.update(status='interrupted', error='Interrupted by user')
    except Exception as exc:
        row['error'] = str(exc)
    row.setdefault('elapsed_seconds', time.monotonic() - start)
    return row


def execute(plan, timeout=86400):
    output = Path(plan['output_dir'])
    output.mkdir(parents=True, exist_ok=False)
    (output / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    report = dict(plan=plan, status='running', rounds=[], preparation=None,
                  started_at=datetime.now(timezone.utc).isoformat(), error='')
    start = time.monotonic()
    try:
        mount = Path(plan['mount'])
        if not mount.is_dir():
            raise ValueError('mount directory does not exist: ' + str(mount))
        if (mount / 'dtt-performance').is_symlink():
            raise ValueError('dtt-performance dataset parent must not be a symbolic link')
        requested = os.environ.get('DTT_' + plan['tool'].upper() + '_BIN', plan['tool'])
        binary = shutil.which(requested)
        if not binary:
            raise ValueError('benchmark executable not found: ' + requested)
        version_log = output / 'tool-version.log'
        result = run_process([binary, '--version'], version_log, min(timeout, 30))
        if result:
            raise ValueError('cannot query tool version: ' + log_tail(version_log))
        report['tool_version'] = version_log.read_text(errors='replace').strip()
        if plan['tool'] == 'fio' and not report['tool_version'].startswith('fio-'):
            raise ValueError('this fio executable is not the Flexible I/O Tester: ' + binary)
        Path(plan['data_dir']).mkdir(parents=True, exist_ok=False)
        if plan['needs_prepare']:
            report['preparation'] = run_step(plan, build_step(plan, 'prepare', 0), binary, timeout)
            if report['preparation']['status'] != 'passed':
                report['status'] = report['preparation']['status']
                report['error'] = report['preparation']['error']
        if report['status'] == 'running':
            for number in range(1, plan['rounds'] + 1):
                row = run_step(plan, build_step(plan, plan['mode'], number), binary, timeout)
                report['rounds'].append(row)
                report['elapsed_seconds'] = time.monotonic() - start
                if row['status'] != 'passed':
                    report['status'], report['error'] = row['status'], row['error']
                    break
                write_report(report, output)
            else:
                report['status'] = 'passed'
    except KeyboardInterrupt:
        report.update(status='interrupted', error='Interrupted by user')
    except Exception as exc:
        report.update(status='failed', error=str(exc))
    report['elapsed_seconds'] = time.monotonic() - start
    return write_report(report, output)


def main(argv=None):
    arguments = parser().parse_args(argv)
    try:
        plan = build_plan(arguments)
        if arguments.dry_run:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        print('%s / %s：direct=%d，并发=%d，文件=%d × %d bytes，总量=%d bytes，block=%d bytes，%d 轮' % (
            plan['tool'], plan['mode'], plan['direct'], plan['concurrency'], plan['file_count'],
            plan['file_size_bytes'], plan['total_size_bytes'], plan['block_size_bytes'], plan['rounds']), flush=True)
        report = execute(plan)
        print('状态：' + report['status'])
        if report['error']:
            print('错误：' + report['error'])
        print('HTML 报告：' + str(Path(plan['output_dir']) / 'index.html'))
        print('测试数据保留在：' + plan['data_dir'])
        return 0 if report['status'] == 'passed' else 130 if report['status'] == 'interrupted' else 1
    except (ValueError, OSError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
