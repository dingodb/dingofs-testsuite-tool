#!/usr/bin/env python3
"""Machine-readable adapter for the pinned MLPerf Storage v2 training workloads."""

import argparse
from datetime import datetime, timezone
from html import escape
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import uuid


# Nominal H100 v2 file bytes, samples/file and batch/accelerator.
MODELS = {'resnet50': (143439748, 1251, 400),
          'unet3d': (146600628, 1, 7),
          'cosmoflow': (2828486, 1, 1)}
FORMAT = 'dtt-mlperf-v1'


def bounded_int(maximum):
    def convert(value):
        if not re.fullmatch(r'[1-9][0-9]*', value) or len(value) > 12:
            raise argparse.ArgumentTypeError('expected a positive integer')
        number = int(value)
        if number > maximum:
            raise argparse.ArgumentTypeError('must be at most %d' % maximum)
        return number
    return convert


def parser():
    p = argparse.ArgumentParser(description='Internal MLPerf Storage v2 training I/O comparison')
    p.add_argument('--mount', default='/data')
    p.add_argument('--output', default='/output')
    p.add_argument('--mlperf-model', choices=tuple(MODELS), default='resnet50')
    p.add_argument('--mlperf-epochs', type=bounded_int(1000), default=5)
    p.add_argument('--mlperf-accelerators', type=bounded_int(1024), default=1)
    p.add_argument('--concurrency', type=bounded_int(1024), default=4)
    p.add_argument('--file-count', type=bounded_int(10**12), required=True)
    p.add_argument('--rounds', type=bounded_int(100), default=1)
    p.add_argument('--dry-run', action='store_true')
    return p


def build_plan(args):
    nominal, samples_per_file, batch = MODELS[args.mlperf_model]
    minimum = max(args.mlperf_accelerators,
                  math.ceil(3 * batch * args.mlperf_accelerators / samples_per_file))
    if args.mlperf_model == 'cosmoflow':
        minimum = max(minimum, 4 * args.mlperf_accelerators)
    if args.file_count < minimum or args.file_count % args.mlperf_accelerators:
        raise ValueError('--file-count must provide three complete batches per accelerator '
                         '(at least %d files) and be divisible by --mlperf-accelerators' % minimum)
    for value in (args.mount, args.output):
        if any(char in value for char in '\r\n\x00:\\[]'):
            raise ValueError('mount/output paths cannot contain newline, colon, backslash or brackets')
    mount, output = Path(args.mount).absolute(), Path(args.output).absolute()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:12]
    return dict(format=FORMAT, tool='mlperf', mlperf_model=args.mlperf_model,
                mlperf_epochs=args.mlperf_epochs, mlperf_accelerators=args.mlperf_accelerators,
                concurrency=args.concurrency, file_size=str(nominal),
                file_count=args.file_count, total_size=str(nominal * args.file_count),
                rounds=args.rounds, rw='read', direct=False, block_size=0,
                iodepth=1, read_percent=None, mount=str(mount),
                output_dir=str(output / ('performance-mlperf-' + run_id)),
                data_dir=str(mount / 'dtt-mlperf' / run_id / args.mlperf_model),
                run_id=run_id,
                compliance_note='Simulated H100 accelerators; custom dataset size and epochs are internal comparisons, not MLPerf-compliant submission results.')


def finite_number(value, name, *, positive=False, percent=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('invalid native ' + name)
    if (positive and value <= 0) or (percent and not 0 <= value <= 100):
        raise ValueError('invalid native ' + name)
    return float(value)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + value)))


def read_native_summary(path):
    nan = object()

    def parse_constant(value):
        if value == 'NaN':
            return nan
        raise ValueError('nonfinite JSON: ' + value)

    summary = json.loads(path.read_text(encoding='utf-8'), parse_constant=parse_constant)
    optional = ('save_checkpoint_io_mean_GB_per_second',
                'save_checkpoint_io_stdev_GB_per_second',
                'save_checkpoint_duration_mean_seconds',
                'save_checkpoint_duration_stdev_seconds')
    if isinstance(summary, dict) and isinstance(summary.get('metric'), dict):
        for key in optional:
            if summary['metric'].get(key) is nan:
                del summary['metric'][key]

    def require_finite(value):
        if value is nan or isinstance(value, float) and not math.isfinite(value):
            raise ValueError('nonfinite JSON: NaN')
        if isinstance(value, dict):
            for item in value.values():
                require_finite(item)
        elif isinstance(value, list):
            for item in value:
                require_finite(item)

    require_finite(summary)
    return summary


def native_metrics(plan, native_dir, output, prefix):
    summaries = list(native_dir.rglob('summary.json'))
    if len(summaries) != 1:
        raise ValueError('expected exactly one native summary.json; found %d' % len(summaries))
    summary_path = summaries[0]
    expected = ('training', plan['mlperf_model'], 'run')
    if tuple(summary_path.relative_to(native_dir).parts[:3]) != expected:
        raise ValueError('native result model/phase does not match request')
    leaf = summary_path.parent
    epoch_path = leaf / '0_per_epoch_stats.json'
    if not epoch_path.is_file():
        raise ValueError('missing native 0_per_epoch_stats.json')
    metadata_paths = list(leaf.glob('training_*_metadata.json'))
    if len(metadata_paths) != 1:
        raise ValueError('expected exactly one native training metadata file; found %d' % len(metadata_paths))
    metadata = read_json(metadata_paths[0])
    native_args = metadata.get('args') if isinstance(metadata, dict) else None
    native_params = metadata.get('params_dict') if isinstance(metadata, dict) else None
    expected_args = {'model': plan['mlperf_model'],
                     'num_accelerators': plan['mlperf_accelerators'],
                     'accelerator_type': 'h100', 'data_dir': plan['data_dir'],
                     'results_dir': str(native_dir), 'loops': 1}
    expected_params = {'dataset.num_files_train': plan['file_count'],
                       'train.epochs': plan['mlperf_epochs']}
    if (metadata.get('benchmark_type') != 'training' or
            not isinstance(native_args, dict) or not isinstance(native_params, dict) or
            any(native_args.get(key) != value for key, value in expected_args.items()) or
            any(str(native_params.get(key)) != str(value) for key, value in expected_params.items())):
        raise ValueError('native model or training parameters do not match request')
    summary, epoch_stats = read_native_summary(summary_path), read_json(epoch_path)
    epochs = plan['mlperf_epochs']
    if type(summary.get('epochs')) is not int or summary['epochs'] != epochs:
        raise ValueError('native epochs do not match request')
    if type(summary.get('num_accelerators')) is not int or summary['num_accelerators'] != plan['mlperf_accelerators']:
        raise ValueError('native accelerator count does not match request')
    if not summary.get('start') or not summary.get('end'):
        raise ValueError('native summary missing start/end')
    metric = summary.get('metric')
    if not isinstance(metric, dict):
        raise ValueError('native summary missing metric')
    for key, positive, percent in (('train_throughput_samples_per_second', True, False),
                                   ('train_au_percentage', False, True)):
        series = metric.get(key)
        if not isinstance(series, list) or len(series) != epochs:
            raise ValueError('native %s length differs from epochs' % key)
        for value in series:
            finite_number(value, key, positive=positive, percent=percent)
    samples = finite_number(metric.get('train_throughput_mean_samples_per_second'),
                            'train_throughput_mean_samples_per_second', positive=True)
    utilization = finite_number(metric.get('train_au_mean_percentage'),
                                'train_au_mean_percentage', percent=True)
    io_mb = finite_number(metric.get('train_io_mean_MB_per_second'),
                          'train_io_mean_MB_per_second', positive=True)
    if not isinstance(epoch_stats, dict) or set(epoch_stats) != {str(i) for i in range(1, epochs + 1)}:
        raise ValueError('native epoch statistics incomplete')
    duration = 0.0
    measurable = True
    for i in range(1, epochs + 1):
        row = epoch_stats[str(i)]
        if not isinstance(row, dict) or not row.get('start') or not row.get('end'):
            raise ValueError('native epoch start/end missing')
        raw_duration = row.get('duration')
        if not isinstance(raw_duration, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', raw_duration):
            raise ValueError('invalid native epoch duration')
        epoch_duration = finite_number(float(raw_duration), 'epoch duration')
        if epoch_duration < 0:
            raise ValueError('invalid native epoch duration')
        measurable = measurable and epoch_duration > 0
        duration += epoch_duration
    attached = []
    for source, suffix in ((summary_path, 'summary'), (epoch_path, 'per-epoch-stats'),
                           (metadata_paths[0], 'metadata')):
        dest = output / (prefix + '-native-' + suffix + '.json')
        shutil.copyfile(source, dest)
        attached.append(dest.name)
    metrics = dict(samples_per_second=samples, accelerator_utilization_percent=utilization,
                   io_mb_per_second=io_mb)
    if measurable:
        metrics['measurement_seconds'] = duration
    return metrics, attached


def run_command(argv, log_path):
    started = time.monotonic()
    with log_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            result = process.wait()
        except KeyboardInterrupt:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait()
            raise
    return result, time.monotonic() - started


def summarize(report):
    passed = [row for row in report['rounds'] if row['status'] == 'passed']
    metrics = {}
    for key in ('samples_per_second', 'accelerator_utilization_percent',
                'io_mb_per_second', 'measurement_seconds'):
        values = [row['metrics'][key] for row in passed if key in row['metrics']]
        if values:
            metrics[key] = dict(mean=statistics.mean(values), min=min(values), max=max(values))
    report['statistics'] = dict(complete=report['status'] == 'passed' and len(passed) == report['plan']['rounds'],
                                requested_rounds=report['plan']['rounds'], successful_rounds=len(passed),
                                metrics=metrics)
    return report


def write_report(report, output):
    summarize(report)
    (output / 'summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    rows = ''.join('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
        row['round'], escape(row['status']), escape(str(row.get('metrics', {}).get('samples_per_second', ''))),
        escape(row.get('error', ''))) for row in report['rounds'])
    html = ('<!doctype html><meta charset="utf-8"><title>MLPerf Storage training I/O</title>'
            '<h1>MLPerf Storage training I/O</h1><p>%s</p><p>%s</p>'
            '<p>Simulated H100; internal comparison only. Not an official MLPerf compliance result.</p>'
            '<table><tr><th>Round</th><th>Status</th><th>Samples/s</th><th>Error</th></tr>%s</table>') % (
                escape(report['status']), escape(report.get('error', '')), rows)
    (output / 'index.html').write_text(html, encoding='utf-8')
    return report


def execute(plan):
    output = Path(plan['output_dir'])
    output.mkdir(parents=True, exist_ok=False)
    report = dict(format=FORMAT, plan=plan, status='running', rounds=[], error='',
                  preparation=None, started_at=datetime.now(timezone.utc).isoformat())
    try:
        mount = Path(plan['mount'])
        if not mount.is_dir():
            raise ValueError('mount directory does not exist: ' + str(mount))
        data_dir = Path(plan['data_dir'])
        if data_dir.parent.is_symlink() or data_dir.parent.parent.is_symlink():
            raise ValueError('dataset path must not traverse a symbolic link')
        binary = shutil.which(os.environ.get('DTT_MLPSTORAGE_BIN', 'mlpstorage'))
        if not binary:
            raise ValueError('mlpstorage executable not found')
        data_dir.mkdir(parents=True, exist_ok=False)
        client_memory_gb = max(1, (os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')) // (1024**3))
        common = [binary, 'training', 'datagen', '--model', plan['mlperf_model'],
                  '--num-processes', str(plan['concurrency']), '--data-dir', str(data_dir),
                  '--results-dir', str(output / 'datagen-native'), '--params',
                  'dataset.num_files_train=%d' % plan['file_count'], 'train.epochs=%d' % plan['mlperf_epochs'],
                  '--open', '--allow-invalid-params', '--allow-run-as-root']
        rc, elapsed = run_command(common, output / 'datagen.log')
        report['preparation'] = dict(status='passed' if rc == 0 else 'failed',
                                     elapsed_seconds=elapsed, log='datagen.log')
        if rc:
            raise ValueError('datagen failed (%d); see datagen.log' % rc)
        for number in range(1, plan['rounds'] + 1):
            prefix = 'round-%03d' % number
            native_dir = output / (prefix + '-native')
            argv = [binary, 'training', 'run', '--model', plan['mlperf_model'],
                    '--num-accelerators', str(plan['mlperf_accelerators']),
                    '--accelerator-type', 'h100', '--num-client-hosts', '1',
                    '--client-host-memory-in-gb', str(client_memory_gb),
                    '--data-dir', str(data_dir), '--results-dir', str(native_dir),
                    '--params', 'dataset.num_files_train=%d' % plan['file_count'],
                    'train.epochs=%d' % plan['mlperf_epochs'], '--loops', '1',
                    '--open', '--allow-invalid-params', '--allow-run-as-root']
            row = dict(round=number, status='failed', metrics={}, native_reports=[],
                       error='', log=prefix + '.log')
            report['rounds'].append(row)
            try:
                rc, elapsed = run_command(argv, output / row['log'])
                row['command_wall_seconds'] = elapsed
                if rc:
                    raise ValueError('training run failed (%d); see %s' % (rc, row['log']))
                row['metrics'], row['native_reports'] = native_metrics(plan, native_dir, output, prefix)
                row['status'] = 'passed'
            except Exception as exc:
                row['error'] = str(exc)
                report['error'] = row['error']
                break
            write_report(report, output)
        else:
            report['status'] = 'passed'
    except KeyboardInterrupt:
        report['error'] = 'Interrupted by user'
        if report['rounds']:
            report['rounds'][-1]['error'] = report['error']
    except Exception as exc:
        report['error'] = str(exc)
    if report['status'] != 'passed':
        report['status'] = 'failed'
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    return write_report(report, output)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        plan = build_plan(args)
        if args.dry_run:
            print(json.dumps(plan, ensure_ascii=False, allow_nan=False))
            return 0
        report = execute(plan)
        print('MLPerf report: ' + str(Path(plan['output_dir']) / 'summary.json'))
        if report['error']:
            print('Error: ' + report['error'], file=sys.stderr)
        return 0 if report['status'] == 'passed' else 1
    except (ValueError, OSError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    raise SystemExit(main())
