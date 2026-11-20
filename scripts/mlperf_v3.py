"""Pinned MLPerf Storage 3.0.46 internal-comparison adapters."""
import argparse
from datetime import datetime, timezone
from html import escape
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import sys
import uuid
from types import SimpleNamespace

import mlperf_benchmark as legacy

VERSION = '3.0.46'
FORMAT = 'dtt-mlperf-v2'
KV_MODELS = ('tiny-1b', 'mistral-7b', 'llama2-7b', 'llama3.1-8b', 'llama3.1-70b-instruct')
CHECKPOINT_MODELS = ('custom', 'llama3-8b', 'llama3-70b', 'llama3-405b', 'llama3-1t')


def legacy_arguments(model, processes, output, env):
    """Bridge supported single-host legacy presets without silently dropping intent."""
    unsupported = (env.get('EXTRA_PARAMS') or env.get('HOSTS', '127.0.0.1') not in ('127.0.0.1', 'localhost')
        or env.get('NUM_CLIENT_HOSTS', '1') != '1' or env.get('ACCELERATOR_TYPE', 'h100') != 'h100'
        or env.get('SKIP_DATAGEN', 'auto') not in ('auto', 'false')
        or env.get('SUBMISSION_MODE', 'closed') != 'closed')
    if unsupported:
        raise ValueError('unsupported legacy options on MLPerf 3.0; use -s benchmark with explicit scenario options')
    args = ['--mount', '/data', '--output', output, '--concurrency', processes,
            '--rounds', env.get('LOOPS', '1')]
    if model == 'checkpointing':
        return args + ['--mlperf-scenario', 'checkpointing', '--mlperf-model', env.get('CHECKPOINTING_MODEL', 'llama3-8b')]
    scale = env.get('SCALE', 'small')
    presets = {'small': {'resnet50':500, 'unet3d':500, 'cosmoflow':2000},
               'medium': {'resnet50':5000, 'unet3d':5000, 'cosmoflow':50000}}
    count = presets.get(scale, {}).get(model, scale)
    if not str(count).isdigit() or int(count) < 1:
        raise ValueError('MLPerf 3.0 requires explicit data size; use -s benchmark --file-count N (no small-scale fallback)')
    return args + ['--mlperf-scenario', 'training', '--mlperf-model', model, '--file-count', str(count),
                   '--mlperf-accelerators', env.get('NUM_ACCELERATORS', '1')]


def nonnegative(value):
    value = float(value)
    if not math.isfinite(value) or value < 0 or value > 1048576:
        raise argparse.ArgumentTypeError('expected finite memory size between 0 and 1048576 GiB')
    return value


def parser():
    p = argparse.ArgumentParser(description='MLPerf Storage 3.0 internal comparisons')
    p.add_argument('--mount', default='/data')
    p.add_argument('--output', default='/output')
    p.add_argument('--mlperf-scenario', choices=('training', 'checkpointing', 'kvcache'), default='training')
    p.add_argument('--mlperf-model')
    p.add_argument('--mlperf-epochs', type=legacy.bounded_int(1000))
    p.add_argument('--mlperf-accelerators', type=legacy.bounded_int(1024))
    p.add_argument('--file-count', type=legacy.bounded_int(10**12))
    p.add_argument('--concurrency', type=legacy.bounded_int(1024), default=4)
    p.add_argument('--rounds', type=legacy.bounded_int(100), default=1)
    p.add_argument('--checkpoint-mode', choices=('write', 'read', 'write-read'))
    p.add_argument('--checkpoint-count', type=legacy.bounded_int(1000))
    p.add_argument('--checkpoint-size', type=legacy.bounded_int(1024**5))
    p.add_argument('--runtime-seconds', type=legacy.bounded_int(86400))
    p.add_argument('--total-size', type=legacy.bounded_int(1024**5))
    p.add_argument('--gpu-memory-gib', type=nonnegative)
    p.add_argument('--cpu-memory-gib', type=nonnegative)
    p.add_argument('--dry-run', action='store_true')
    return p


def build_plan(args):
    scene = args.mlperf_scenario
    groups = {
        'training': ('mlperf_epochs', 'mlperf_accelerators', 'file_count'),
        'checkpointing': ('checkpoint_mode', 'checkpoint_count', 'checkpoint_size'),
        'kvcache': ('runtime_seconds', 'total_size', 'gpu_memory_gib', 'cpu_memory_gib'),
    }
    for other, fields in groups.items():
        if other != scene and any(getattr(args, field) is not None for field in fields):
            raise ValueError('parameters for %s cannot be used with %s' % (other, scene))
    model = args.mlperf_model or {'training': 'resnet50', 'checkpointing': 'custom', 'kvcache': 'llama3.1-8b'}[scene]
    if scene == 'training':
        if model not in legacy.MODELS or args.file_count is None:
            raise ValueError('training requires a supported model and --file-count')
        args.mlperf_model = model
        args.mlperf_epochs = args.mlperf_epochs or 5
        args.mlperf_accelerators = args.mlperf_accelerators or 1
        plan = legacy.build_plan(args)
    else:
        allowed = CHECKPOINT_MODELS if scene == 'checkpointing' else KV_MODELS
        if model not in allowed:
            raise ValueError('unsupported %s model: %s' % (scene, model))
        for value in (args.mount, args.output):
            if any(char in value for char in '\r\n\x00:\\[]'):
                raise ValueError('invalid mount/output path')
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:12]
        plan = dict(tool='mlperf', mlperf_model=model, concurrency=args.concurrency, rounds=args.rounds,
                    mount=str(Path(args.mount).absolute()), run_id=run_id, file_count=0, file_size='0',
                    rw='readwrite', direct=False, block_size=0, iodepth=1, read_percent=None,
                    output_dir=str(Path(args.output).absolute() / ('performance-mlperf-' + run_id)),
                    data_dir=str(Path(args.mount).absolute() / 'dtt-mlperf' / run_id / scene))
        if scene == 'checkpointing':
            size = args.checkpoint_size or 1024**3
            if model != 'custom' and args.checkpoint_size is not None:
                raise ValueError('--checkpoint-size requires the explicit custom model')
            # Nominal transformer parameter counts; serialization can add overhead.
            nominal = {'llama3-8b': 8_030_261_248, 'llama3-70b': 70_553_706_496,
                       'llama3-405b': 405_853_388_800, 'llama3-1t': 1_000_000_000_000}
            if model != 'custom':
                size = nominal[model] * 14
            mode, count = args.checkpoint_mode or 'write-read', args.checkpoint_count or 1
            plan.update(checkpoint_mode=mode, checkpoint_count=count, checkpoint_size=size,
                        preparation_required=mode == 'read', total_size=str(size * count))
        else:
            capacity = args.total_size or 1024**3
            plan.update(runtime_seconds=args.runtime_seconds or 60, capacity_bytes=capacity,
                        total_size=str(capacity), gpu_memory_gib=args.gpu_memory_gib or 0.0,
                        cpu_memory_gib=args.cpu_memory_gib or 0.0, preparation_required=False)
    plan.update(format=FORMAT, engine_version=VERSION, mlperf_scenario=scene,
                compliance_note='MLPerf Storage 3.0 what-if/custom workload; internal comparison, not an official submission.')
    return plan


def native_commands(plan, results, preparation=False):
    results = Path(results)
    scene, model = plan['mlperf_scenario'], plan['mlperf_model']
    binary = os.environ.get('DTT_MLPSTORAGE_BIN', 'mlpstorage')
    if scene == 'kvcache':
        root = Path(os.environ.get('DTT_MLPSTORAGE_ROOT', '/opt/mlpstorage-src'))
        return [[sys.executable, str(root / 'kv_cache_benchmark/kv-cache.py'),
                 '--model', model, '--num-users', str(plan['concurrency']),
                 '--duration', str(plan['runtime_seconds']), '--cache-dir', plan['data_dir'],
                 '--storage-capacity-gb', str(plan['capacity_bytes'] / 1024**3),
                 '--gpu-mem-gb', str(plan['gpu_memory_gib']), '--cpu-mem-gb', str(plan['cpu_memory_gib']),
                 '--max-concurrent-allocs', str(plan['concurrency']), '--generation-mode', 'none',
                 '--seed', '42', '--output', str(results / 'kv-result.json')]]
    memory = max(1, os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') // 1024**3)
    shared = ['--results-dir', str(results), '--systemname', 'dtt', '--allow-run-as-root', '--allow-invalid-params']
    if scene == 'training':
        phase = 'datagen' if preparation else 'run'
        cmd = [binary, 'whatif', 'training', model, phase, 'file', *shared,
               '--data-dir', plan['data_dir'], '--params', 'dataset.num_files_train=%d' % plan['file_count'],
               'train.epochs=%d' % plan['mlperf_epochs']]
        if preparation:
            cmd += ['--num-processes', str(plan['concurrency'])]
        else:
            cmd += ['--num-accelerators', str(plan['mlperf_accelerators']), '--accelerator-type', 'h100',
                    '--client-host-memory-in-gb', str(memory), '--num-client-hosts', '1', '--loops', '1']
    else:
        mode = plan['checkpoint_mode']
        writes = plan['checkpoint_count'] if preparation or mode != 'read' else 0
        reads = plan['checkpoint_count'] if not preparation and mode != 'write' else 0
        cmd = [binary, 'whatif', 'checkpointing', 'run', 'file', '--model',
               'llama3-8b' if model == 'custom' else model, *shared,
               '--num-processes', str(plan['concurrency']), '--client-host-memory-in-gb', str(memory),
               '--checkpoint-folder', plan['data_dir'], '--num-checkpoints-write', str(writes),
               '--num-checkpoints-read', str(reads), '--loops', '1', '--params', 'checkpoint.time_between_checkpoints=0']
        if model == 'custom':
            # Explicit custom byte-sized state, not a silently scaled Llama model.
            per_rank = math.ceil(plan['checkpoint_size'] / plan['concurrency'] / 4) * 4
            cmd += ['model.type=custom', 'model.num_layers=-1', 'model.model_size_bytes=%d' % per_rank,
                    'model.optimization_groups=[]', 'model.parallelism.zero_stage=0',
                    'model.parallelism.tensor=%d' % plan['concurrency'], 'model.parallelism.pipeline=1']
    return [[binary, 'init', 'dtt-internal', str(results)], cmd]


def number(value, key, positive=False):
    result = legacy.finite_number(value, key, positive=positive)
    if result < 0:
        raise ValueError('negative native ' + key)
    return result


def native_metrics(plan, results):
    scene = plan['mlperf_scenario']
    if scene == 'kvcache':
        raw = legacy.read_json(results / 'kv-result.json')
        config = raw.get('effective_config')
        expected = dict(model=plan['mlperf_model'], num_users=plan['concurrency'], duration=plan['runtime_seconds'],
                        cache_dir=plan['data_dir'], storage_capacity_gb=plan['capacity_bytes']/1024**3,
                        gpu_mem_gb=plan['gpu_memory_gib'], cpu_mem_gb=plan['cpu_memory_gib'],
                        max_concurrent_allocs=plan['concurrency'], generation_mode='none', seed=42)
        if not isinstance(config, dict) or any(config.get(k) != v for k, v in expected.items()):
            raise ValueError('native KV effective configuration mismatch or missing; upgrade DTT image')
        summary = raw.get('summary', {})
        requests = number(summary.get('total_requests'), 'total_requests', True)
        elapsed = number(summary.get('elapsed_time'), 'elapsed_time', True)
        if elapsed < plan['runtime_seconds'] * 0.9:
            raise ValueError('incomplete KV cache duration')
        metrics = {'requests': requests, 'measurement_seconds': elapsed,
                   'tokens_per_second': number(summary.get('avg_throughput_tokens_per_sec'), 'tokens/s', True),
                   'requests_per_second': number(summary.get('requests_per_second'), 'requests/s', True)}
        for field in ('end_to_end_latency_ms', 'storage_io_latency_ms'):
            for quantile in ('mean', 'p95', 'p99'):
                metrics[field + '_' + quantile] = number(summary.get(field, {}).get(quantile), field + quantile)
        stats = summary.get('cache_stats', {})
        for key in ('total_read_bytes', 'total_write_bytes'):
            if key in stats:
                metrics[key] = number(stats[key], key)
        return metrics
    summaries = list(results.rglob('summary.json'))
    if len(summaries) != 1:
        raise ValueError('expected exactly one native summary.json')
    leaf = summaries[0].parent
    metadata_files = list(leaf.glob('*_metadata.json'))
    if len(metadata_files) != 1:
        raise ValueError('missing unique native metadata')
    meta = legacy.read_json(metadata_files[0])
    expected_model = 'llama3-8b' if plan['mlperf_model'] == 'custom' else plan['mlperf_model']
    if str(meta.get('benchmark_type', '')).lower() != scene or meta.get('model') != expected_model:
        raise ValueError('native scenario/model mismatch')
    summary = legacy.read_native_summary(summaries[0])
    if not summary.get('start') or not summary.get('end'):
        raise ValueError('native run is incomplete')
    metric = summary.get('metric', {})
    epochs = legacy.read_json(leaf / '0_per_epoch_stats.json')
    if scene == 'training':
        if summary.get('epochs') != plan['mlperf_epochs'] or summary.get('num_accelerators') != plan['mlperf_accelerators']:
            raise ValueError('native training epochs/accelerators mismatch')
        params = meta.get('parameters', {})
        if (str(params.get('dataset', {}).get('num_files_train')) != str(plan['file_count']) or
                str(params.get('train', {}).get('epochs')) != str(plan['mlperf_epochs'])):
            raise ValueError('native training parameters mismatch')
        if not isinstance(epochs, dict) or set(epochs) != {str(i) for i in range(1, plan['mlperf_epochs']+1)}:
            raise ValueError('native epoch statistics incomplete')
        for row in epochs.values():
            if not isinstance(row, dict) or not row.get('start') or not row.get('end'):
                raise ValueError('native epoch start/end missing')
            number(float(row.get('duration', 'nan')), 'epoch duration')
        for key, positive, percent in (('train_throughput_samples_per_second', True, False),
                                       ('train_au_percentage', False, True)):
            series = metric.get(key)
            if not isinstance(series, list) or len(series) != plan['mlperf_epochs']:
                raise ValueError('native epoch metric series incomplete')
            for value in series:
                legacy.finite_number(value, key, positive=positive, percent=percent)
        return {'samples_per_second': number(metric.get('train_throughput_mean_samples_per_second'), 'samples/s', True),
                'io_mb_per_second': number(metric.get('train_io_mean_MB_per_second'), 'IO MiB/s', True),
                'accelerator_utilization_percent': legacy.finite_number(metric.get('train_au_mean_percentage'), 'AU', percent=True)}
    params = meta.get('parameters', {})
    checkpoint = params.get('checkpoint', {})
    expected_folder = str(Path(plan['data_dir']) / expected_model)
    if meta.get('num_processes') != plan['concurrency'] or checkpoint.get('checkpoint_folder') != expected_folder:
        raise ValueError('native checkpoint processes/directory mismatch')
    for phase, field in (('write','num_checkpoints_write'), ('read','num_checkpoints_read')):
        if checkpoint.get(field) != (plan['checkpoint_count'] if phase in plan['checkpoint_mode'] else 0):
            raise ValueError('native checkpoint phase/count mismatch')
    multiplier = 1
    if plan['mlperf_model'] == 'custom':
        model = params.get('model', {})
        per_rank = math.ceil(plan['checkpoint_size']/plan['concurrency']/4)*4
        expected_model_params = dict(type='custom', num_layers='-1', model_size_bytes=str(per_rank), optimization_groups='[]')
        parallel = model.get('parallelism', {})
        if (any(str(model.get(k)) != v for k, v in expected_model_params.items()) or
            any(str(parallel.get(k)) != str(v) for k, v in dict(tensor=plan['concurrency'],pipeline=1,zero_stage=0,data=1).items())):
            raise ValueError('native custom checkpoint size/parallelism mismatch')
        multiplier = plan['concurrency']
        if not math.isclose(number(metric.get('checkpoint_size_GB'), 'checkpoint size', True)*1024**3, per_rank):
            raise ValueError('native checkpoint serialized size mismatch')
    rank_files = list(leaf.glob('*_per_epoch_stats.json'))
    if {p.name for p in rank_files} != {f'{i}_per_epoch_stats.json' for i in range(plan['concurrency'])}:
        raise ValueError('native checkpoint rank results incomplete')
    metrics = {}
    for phase, native in (('write', 'save'), ('read', 'load')):
        if phase not in plan['checkpoint_mode']:
            continue
        for rank_file in rank_files:
            rank_epochs = legacy.read_json(rank_file)
            records = [item for epoch in rank_epochs.values() for key, item in epoch.items() if native + '_ckpt' in key]
            if len(records) != plan['checkpoint_count']:
                raise ValueError('incomplete checkpoint ' + phase + ' phase')
            for row in records:
                if not row.get('start') or not row.get('end'):
                    raise ValueError('incomplete checkpoint rank phase timestamps')
                number(row.get('duration'), 'checkpoint rank duration', True)
        metrics[phase + '_gib_per_second'] = number(metric.get(native + '_checkpoint_io_mean_GB_per_second'), phase + ' bandwidth', True)*multiplier
        metrics[phase + '_seconds'] = number(metric.get(native + '_checkpoint_duration_mean_seconds'), phase + ' duration', True)
    # DLIO custom model reports per-rank bytes; transformer models already
    # report global bytes. Normalize both to aggregate size/bandwidth.
    metrics['checkpoint_gib'] = number(metric.get('checkpoint_size_GB'), 'checkpoint size', True)*multiplier
    return metrics


def write_report(report, output):
    passed = [r for r in report['rounds'] if r['status'] == 'passed']
    keys = sorted({k for r in passed for k in r['metrics']})
    report['statistics'] = dict(complete=report['status'] == 'passed' and len(passed) == report['plan']['rounds'],
        requested_rounds=report['plan']['rounds'], successful_rounds=len(passed), metrics={
            k: dict(mean=statistics.mean([r['metrics'][k] for r in passed]),
                    min=min(r['metrics'][k] for r in passed), max=max(r['metrics'][k] for r in passed)) for k in keys})
    (output / 'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    (output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>MLPerf Storage 3.0 — ' +
        escape(report['plan']['mlperf_scenario']) + '</h1><p>' + escape(report['plan']['compliance_note']) +
        '</p><pre>' + escape(json.dumps(report, indent=2, ensure_ascii=False)) + '</pre>', encoding='utf-8')
    return report


def execute(plan):
    output = Path(plan['output_dir'])
    output.mkdir(parents=True, exist_ok=False)
    report = dict(format=FORMAT, engine_version=VERSION, plan=plan, status='running', rounds=[], error='', preparation=None)
    try:
        installed = importlib.metadata.version('mlpstorage')
        if installed != VERSION:
            raise ValueError('requires MLPerf Storage %s; installed %s. Upgrade DTT image.' % (VERSION, installed))
        if plan['mlperf_scenario'] == 'checkpointing' and plan['mlperf_model'] == 'custom':
            from mlpstorage_py.benchmarks.dlio import CheckpointingBenchmark
            probe = SimpleNamespace(params_dict={'model.type':'custom','model.model_size_bytes':'8388608'},
                                    args=SimpleNamespace(num_processes=2,num_checkpoints_write=2))
            try:
                capacity = CheckpointingBenchmark.required_bytes_for_capacity_gate(probe)
            except Exception as exc:
                raise ValueError('custom checkpoint capacity patch missing; upgrade DTT image') from exc
            if capacity != 33554432:
                raise ValueError('custom checkpoint capacity patch missing; upgrade DTT image')
            report['engine_patch'] = 'dtt-custom-capacity-1'
        if not Path(plan['mount']).is_dir():
            raise ValueError('mount directory does not exist')
        data = Path(plan['data_dir'])
        if data.parent.is_symlink() or data.parent.parent.is_symlink():
            raise ValueError('dataset path must not traverse a symbolic link')
        data.mkdir(parents=True, exist_ok=False)
        if shutil.disk_usage(data).free < int(plan['total_size']):
            raise ValueError('insufficient available space for requested dataset/capacity')

        def run_phase(name, preparation=False):
            results = output / (name + '-native')
            if plan['mlperf_scenario'] == 'kvcache':
                results.mkdir()
            commands = native_commands(plan, results, preparation)
            elapsed = 0
            for index, command in enumerate(commands):
                log = '%s-%d.log' % (name, index)
                rc, seconds = legacy.run_command(command, output / log)
                elapsed += seconds
                if rc:
                    raise ValueError('%s failed (%d); see %s' % (name, rc, log))
            return results, elapsed, commands

        if plan['mlperf_scenario'] == 'training' or plan.get('preparation_required'):
            prepared, seconds, commands = run_phase('preparation', True)
            if plan['mlperf_scenario'] == 'checkpointing':
                native_metrics(dict(plan, checkpoint_mode='write'), prepared)
            report['preparation'] = dict(status='passed', elapsed_seconds=seconds, commands=commands)
        for i in range(1, plan['rounds'] + 1):
            row = dict(round=i, status='failed', metrics={}, native_reports=[], error='')
            report['rounds'].append(row)
            results, seconds, commands = run_phase('round-%03d' % i)
            row.update(command_wall_seconds=seconds, commands=commands)
            row['metrics'] = native_metrics(plan, results)
            for index, path in enumerate(sorted(results.rglob('*.json'))):
                name = 'round-%03d-native-%03d.json' % (i, index)
                shutil.copyfile(path, output / name)
                row['native_reports'].append(name)
            row['status'] = 'passed'
            write_report(report, output)
        report['status'] = 'passed'
    except (Exception, KeyboardInterrupt) as exc:
        report['status'] = 'failed'
        report['error'] = str(exc) or 'Interrupted by user'
        if report['rounds']:
            report['rounds'][-1]['error'] = report['error']
    return write_report(report, output)


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        plan = build_plan(args)
        if args.dry_run:
            print(json.dumps(plan, allow_nan=False))
            return 0
        report = execute(plan)
        print('MLPerf report: ' + plan['output_dir'] + '/summary.json')
        if report['error']:
            print(report['error'], file=sys.stderr)
        return 0 if report['status'] == 'passed' else 1
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
