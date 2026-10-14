"""Pure planning for the shared, finite fio/elbencho benchmark interface."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

MODES = ('read', 'write', 'randread', 'randwrite', 'rw', 'randrw')


def positive(value):
    if not re.fullmatch(r'[1-9][0-9]*', str(value)):
        raise argparse.ArgumentTypeError('expected a positive integer')
    return int(value)


def size(value):
    match = re.fullmatch(r'([1-9][0-9]*)([KMGTPE]?)(?:i?B)?', str(value), re.I)
    if not match:
        raise argparse.ArgumentTypeError('expected a positive byte size, e.g. 4K, 256M, 1GiB')
    return int(match[1]) * 1024 ** (('KMGTPE'.index(match[2].upper()) + 1) if match[2] else 0)


def parser():
    p = argparse.ArgumentParser(description='Single-client finite performance benchmark; sizes and file count are global totals.')
    p.add_argument('--tool', required=True, choices=('fio', 'elbencho'))
    p.add_argument('--mount', default='/data')
    p.add_argument('--output', default='/output')
    p.add_argument('--rw', choices=MODES, default='write')
    p.add_argument('--direct', choices=(0, 1), type=int, default=1)
    p.add_argument('--concurrency', type=positive, default=4)
    p.add_argument('--file-size', type=size)
    p.add_argument('--file-count', type=positive)
    p.add_argument('--total-size', type=size)
    p.add_argument('--block-size', type=size)
    p.add_argument('--rounds', type=positive, default=1)
    p.add_argument('--iodepth', type=positive, default=1)
    p.add_argument('--read-percent', type=int)
    p.add_argument('--dry-run', action='store_true')
    return p


def build_plan(args):
    count, file_size, total = args.file_count, args.file_size, args.total_size
    if total is not None:
        if count is not None and file_size is not None:
            if total != count * file_size:
                raise ValueError('--total-size must equal --file-count times --file-size')
        elif file_size is not None:
            if total % file_size:
                raise ValueError('--total-size must be divisible by --file-size')
            count = total // file_size
        else:
            count = count or args.concurrency
            if total % count:
                raise ValueError('--total-size must be divisible by --file-count')
            file_size = total // count
    else:
        count = count or args.concurrency
        file_size = file_size or 256 * 1024**2
        total = count * file_size
    if count < args.concurrency:
        raise ValueError('--file-count must be at least --concurrency; reduce concurrency or add files')
    block = args.block_size
    if block is None:
        block = 1024**2
        while block > file_size or file_size % block:
            block //= 2
    if block > file_size or file_size % block:
        raise ValueError('--block-size must be <= file size and divide it exactly')
    if args.direct and (block % 4096 or file_size % 4096):
        raise ValueError('direct I/O requires 4KiB-aligned file and block sizes; use --direct 0 for smaller files')
    if args.tool == 'elbencho' and args.rw.startswith('rand') and total % (block * args.concurrency):
        raise ValueError('elbencho random total size must be divisible by block-size * concurrency; otherwise the tool silently reduces the volume')
    if args.read_percent is not None and args.rw not in ('rw', 'randrw'):
        raise ValueError('--read-percent is only valid for --rw rw or randrw')
    percent = args.read_percent if args.read_percent is not None else 50
    if not 0 <= percent <= 100:
        raise ValueError('--read-percent must be between 0 and 100')
    for value in (args.mount, args.output):
        if any(char in value for char in '\r\n\x00:\\[]'):
            raise ValueError('mount/output paths cannot contain newline, colon, backslash or brackets')
    mount, output = Path(args.mount).absolute(), Path(args.output).absolute()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:12]
    return dict(
        tool=args.tool, mode=args.rw, direct=args.direct, concurrency=args.concurrency,
        file_size_bytes=file_size, file_count=count, total_size_bytes=total,
        block_size_bytes=block, rounds=args.rounds, iodepth=args.iodepth,
        read_percent=percent if args.rw in ('rw', 'randrw') else None,
        mount=str(mount), output_dir=str(output / ('performance-' + args.tool + '-' + run_id)),
        data_dir=str(mount / 'dtt-performance' / run_id / args.tool), run_id=run_id,
        peak_dataset_bytes=total, needs_prepare=args.rw in ('read', 'randread', 'rw', 'randrw'),
        cache_note='未清除操作系统或存储缓存；buffered/direct 按配置执行，不宣称冷缓存。',
        metric_note='带宽、IOPS、延迟采用工具原生数据阶段指标；耗时包含进程启动与同步。fio end_fsync 与 elbencho 独立 SYNC 的计时口径不同，跨工具对比需结合耗时和原始结果。随机模式表示随机偏移，不保证两工具的跨文件访问顺序一致。',
    )


def build_step(plan, phase, round_number):
    prepare = phase == 'prepare'
    mode = 'write' if prepare else phase
    prefix = 'prepare' if prepare else 'round-%03d' % round_number
    output = Path(plan['output_dir'])
    step = dict(phase=phase, round=round_number, measured=not prepare,
                result_path=str(output / (prefix + '.json')),
                log_path=str(output / (prefix + '.log')),
                command_path=str(output / (prefix + '.command')))
    if plan['tool'] == 'fio':
        lines = ['[global]', 'ioengine=libaio', 'thread=1', 'group_reporting=1',
                 'directory=' + plan['data_dir'], 'filesize=%d' % plan['file_size_bytes'],
                 'bs=%d' % plan['block_size_bytes'], 'direct=%d' % plan['direct'],
                 'iodepth=%d' % plan['iodepth'], 'rw=' + mode,
                 'fallocate=none', 'create_on_open=1', 'invalidate=0',
                 'refill_buffers=1', 'scramble_buffers=1', 'randrepeat=0',
                 'exitall_on_error=1', 'openfiles=1', 'file_service_type=sequential',
                 'allow_file_create=%d' % (mode in ('write', 'randwrite'))]
        if mode in ('write', 'randwrite', 'rw', 'randrw'):
            lines.append('end_fsync=1')
        if mode in ('rw', 'randrw'):
            lines.append('rwmixread=%d' % plan['read_percent'])
        quotient, remainder = divmod(plan['file_count'], plan['concurrency'])
        for worker in range(plan['concurrency']):
            count = quotient + (worker < remainder)
            lines += ['', '[worker-%d]' % worker, 'numjobs=1', 'nrfiles=%d' % count,
                      'size=%d' % (count * plan['file_size_bytes']),
                      'filename_format=worker-%d.$filenum' % worker]
        step['config'] = '\n'.join(lines) + '\n'
        step['config_path'] = str(output / (prefix + '.fio'))
        step['argv'] = ['fio', step['config_path'], '--output-format=json', '--output=' + step['result_path']]
    else:
        write = mode in ('write', 'randwrite', 'rw', 'randrw')
        argv = ['elbencho', '-w' if write else '-r', '-t', str(plan['concurrency']),
                '-s', str(plan['file_size_bytes']), '-b', str(plan['block_size_bytes']),
                '--iodepth', str(plan['iodepth']), '--lat', '--jsonfile', step['result_path']]
        if plan['direct']:
            argv.append('--direct')
        if mode.startswith('rand'):
            argv += ['--rand', '--randamount', str(plan['total_size_bytes'])]
        if mode in ('rw', 'randrw'):
            argv += ['--rwmixpct', str(plan['read_percent'])]
        if write:
            argv += ['--blockvarpct', '100', '--blockvaralgo', 'balanced', '--sync']
        argv.append(plan['data_dir'] + '/file[0-%d]' % (plan['file_count'] - 1))
        step['argv'] = argv
    return step
