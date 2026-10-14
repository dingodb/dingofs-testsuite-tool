#!/usr/bin/env python3
"""Single-client AI Storage workloads. Planning never opens a storage tool or dataset."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import socket
import statistics
import subprocess
import time
import uuid

SCENARIOS = {
    'fio': ('ai-storage-b01-read', 'ai-storage-b01-write', 'ai-storage-t02-read',
            'ai-storage-t03-read', 'ai-storage-t03-write', 'ai-storage-c01'),
    'elbencho': ('ai-storage-t01-read', 'ai-storage-t03-read', 'ai-storage-t03-write', 'ai-storage-l01-read'),
    'mdtest': ('ai-storage-t03',),
}

SMALL_FILE_MATRIX = (
    (4096, (4096,)),
    (65536, (4096, 16384, 65536)),
    (262144, (4096, 16384, 65536, 262144)),
    (1048576, (4096, 16384, 65536, 262144, 1048576)),
    (10485760, (4096, 16384, 65536, 262144, 1048576, 2097152)),
)


def size(value):
    match = re.fullmatch(r'([1-9][0-9]*)([KMGTPE]?)(?:i?B)?', str(value), re.I)
    if not match:
        raise argparse.ArgumentTypeError('expected a positive byte size, e.g. 256G')
    return int(match[1]) * 1024 ** ('KMGTPE'.index(match[2].upper()) + 1 if match[2] else 0)


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('expected a positive integer')
    return number


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tool', required=True, choices=SCENARIOS)
    p.add_argument('--scenario', required=True)
    p.add_argument('--mount', default='/data')
    p.add_argument('--output', default='/output')
    p.add_argument('--dataset-size', type=size, help='total bytes across this client, not per job')
    p.add_argument('--file-size', type=size, help='one small file or one elbencho shard')
    p.add_argument('--file-count', type=positive, help='total file count, not per worker')
    p.add_argument('--bs', type=size)
    p.add_argument('--jobs', type=positive)
    p.add_argument('--threads', type=positive)
    p.add_argument('--iodepth', type=positive, default=1)
    p.add_argument('--direct', type=int, choices=(0, 1))
    p.add_argument('--repeats', type=positive, default=3)
    p.add_argument('--runtime', type=positive, help='T02 measured seconds (default 600)')
    p.add_argument('--ramp-time', type=positive, default=30)
    p.add_argument('--phase', choices=('all', 'prepare', 'measure'), default='all')
    p.add_argument('--data-id', help='dataset identity; required for measure, returned by prepare')
    p.add_argument('--layout', choices=('unique', 'shared'), default='unique')
    p.add_argument('--cache-note', default='Cache state uncontrolled; not a cold-cache claim.')
    p.add_argument('--dry-run', action='store_true')
    return p


def build_plan(a):
    if a.scenario not in SCENARIOS[a.tool]:
        raise ValueError('unsupported tool/scenario combination')
    small = a.scenario.startswith('ai-storage-t03')
    checkpoint = a.scenario == 'ai-storage-c01'
    metadata = a.tool == 'mdtest'
    if a.runtime and a.scenario != 'ai-storage-t02-read':
        raise ValueError('--runtime is supported only for T02; other scenes are finite passes')
    if a.phase != 'all' and (checkpoint or metadata or
                             (a.tool == 'elbencho' and a.scenario.endswith('write'))):
        raise ValueError('this scene uses new data each round and requires --phase all')
    if a.phase == 'measure' and not a.data_id:
        raise ValueError('--phase measure requires --data-id from a successful prepare')
    if checkpoint and a.repeats != 3:
        raise ValueError('C01 requires exactly three new checkpoint rounds')
    data_id = a.data_id or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:12]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', data_id):
        raise ValueError('invalid --data-id (use letters, digits, dot, dash or underscore)')
    for path in (a.mount, a.output):
        if any(c in path for c in '\n\r:\\'):
            raise ValueError('paths cannot contain newlines, colon or backslash')
    jobs = a.jobs or (1 if metadata else 4)
    workers = (a.threads or 4) if a.tool == 'elbencho' else jobs
    direct = a.direct if a.direct is not None else (0 if checkpoint else 1)
    if a.scenario == 'ai-storage-t02-read' and not direct:
        raise ValueError('T02 requires --direct 1')
    if metadata:
        if a.dataset_size or a.file_size or a.bs:
            raise ValueError('pure metadata has no data size or block size')
        count, file_size, total, bs = a.file_count or 100000, 0, 0, 0
    elif small:
        file_size = a.file_size or 256 * 1024
        count = a.file_count or 100000
        total = file_size * count
        bs = a.bs or min(file_size, 64 * 1024)
        if a.dataset_size and a.dataset_size != total:
            raise ValueError('small-file total must equal file size times total file count')
    elif a.tool == 'elbencho':
        model = a.scenario == 'ai-storage-l01-read'
        file_size = a.file_size or (4 if model else 1) * 1024**3
        total = a.dataset_size or (64 * 1024**3 if model else 1024**4)
        if total % file_size:
            raise ValueError('dataset size must be divisible by shard size')
        count = total // file_size
        if a.file_count and count != a.file_count:
            raise ValueError('file count disagrees with dataset/shard size')
        bs = a.bs or 1024**2
    else:
        total = a.dataset_size or (64 if checkpoint else 256) * 1024**3
        if total % jobs:
            raise ValueError('dataset size must be divisible by jobs')
        count, file_size, bs = jobs, total // jobs, a.bs or (64 * 1024 if 't02' in a.scenario else 1024**2)
        if a.file_size or a.file_count:
            raise ValueError('large fio scenes use --dataset-size and --jobs to define shards')
    if (small or metadata) and count % workers:
        raise ValueError('total file count must be divisible by worker count')
    if not metadata and (bs > file_size or file_size % bs or (direct and bs % 4096)):
        raise ValueError('block size must divide file size and direct I/O must be 4KiB aligned')
    root = Path(a.mount).absolute() / 'dtt-ai-storage' / data_id / a.tool
    # Read and overwrite variants can share their prepared dataset.
    root = root / a.scenario.removesuffix('-read').removesuffix('-write')
    output = Path(a.output).absolute() / ('ai-storage-' + uuid.uuid4().hex[:12])
    plan = dict(tool=a.tool, scenario=a.scenario, data_id=data_id, data_root=str(root), mount=str(Path(a.mount).absolute()),
        output=str(output), dataset_bytes=total, file_size=file_size, file_count=count,
        block_size=bs, workers=workers, iodepth=a.iodepth, direct=direct, repeats=a.repeats,
        phase=a.phase, cache_note=a.cache_note, client_count=1, layout=a.layout,
        runtime=a.runtime or (600 if 't02' in a.scenario else 0), steps=[],
        dataset_scope='single-client total',
        peak_dataset_bytes=total * (a.repeats if checkpoint or (a.tool == 'elbencho' and a.scenario.endswith('write')) else 1))

    def step(phase, round_number, data, fresh=False):
        index = len(plan['steps'])
        prefix = str(output / ('%02d-%s-%s' % (index, round_number, phase)))
        write = phase in ('prepare', 'write', 'create')
        item = dict(phase=phase, round=round_number, data_path=str(data),
                    fresh=fresh, measured=phase not in ('prepare','verify'),
                    result_path=prefix + '.json', log_path=prefix + '.log')
        if a.tool == 'fio':
            cfg = ['[global]', 'ioengine=libaio', 'thread=1', 'group_reporting=1',
                'numjobs=%d' % workers, 'directory=' + str(data),
                'filename_format=file.$jobnum.$filenum', 'size=%d' % (total // workers),
                'filesize=%d' % file_size, 'nrfiles=%d' % (count // workers),
                'bs=%d' % bs, 'direct=%d' % direct, 'iodepth=%d' % a.iodepth,
                'rw=' + ('write' if write else ('randread' if 't02' in a.scenario else 'read')),
                'refill_buffers=1', 'scramble_buffers=1', 'randrepeat=0',
                'fallocate=none', 'create_on_open=1', 'invalidate=0',
                'allow_file_create=%d' % fresh, 'exitall_on_error=1',
                'percentile_list=95:99:99.9']
            if small:
                cfg += ['openfiles=1', 'file_service_type=sequential']
            if write:
                cfg += ['end_fsync=1']
            if checkpoint and phase in ('write','verify'):
                cfg += ['verify=crc32c', 'verify_state_save=0', 'do_verify=%d' % (phase == 'verify')]
                if phase == 'verify':
                    cfg += ['verify_only=1','verify_fatal=1']
            if phase == 'read' and 't02' in a.scenario:
                cfg += ['time_based=1', 'runtime=%d' % plan['runtime'], 'ramp_time=%d' % a.ramp_time]
            item['fio_config'] = '\n'.join(cfg + ['[work]', ''])
            item['argv'] = ['fio', prefix+'.fio', '--output-format=json', '--output='+item['result_path']]
        elif a.tool == 'elbencho':
            argv = ['elbencho', '-w' if write else '-r', '-t',str(workers), '-s',str(file_size),
                    '-b',str(bs),'--iodepth',str(a.iodepth),'--lat','--latpercent','--cpu',
                    '--jsonfile',item['result_path']]
            if direct:
                argv += ['--direct']
            if write:
                argv += ['--blockvarpct','100','--blockvaralgo','balanced']
            if phase == 'prepare':
                argv += ['--sync']
            if small:
                argv += ['-n','1','-N',str(count // workers)]
                if write:
                    argv += ['-d']
                argv += [str(data)]
            else:
                argv += [str(data / ('file[0-%d]' % (count-1)))]
            item['argv'] = argv
        else:
            argv = ['mpirun', '--host','localhost:'+str(workers),'-np',str(workers),'mdtest','-f',str(workers),'-l',str(workers),
                    '-F','-n',str(count // workers),'-z','0','-i','1','-d',str(data),
                    {'create':'-C','stat':'-T','remove':'-r'}[phase]]
            if a.layout == 'unique':
                argv += ['-u']
            item['argv'] = argv
        plan['steps'].append(item)

    if checkpoint or metadata or (a.tool == 'elbencho' and a.scenario.endswith('write')):
        for n in range(1, a.repeats+1):
            data = root / ('round-%d' % n)
            if metadata:
                for phase in ('create','stat','remove'):
                    step(phase,n,data,phase=='create')
            else:
                step('write',n,data,True)
                if checkpoint:
                    step('read',n,data)
                    step('verify',n,data)
    else:
        data = root / 'dataset'
        if a.phase in ('all','prepare'):
            step('prepare',0,data,True)
        if a.phase in ('all','measure'):
            for n in range(1,a.repeats+1):
                step('write' if a.scenario.endswith('write') else 'read',n,data)
    return plan


def dataset_identity(plan):
    return {key: plan[key] for key in
            ('tool','dataset_bytes','file_size','file_count','workers','layout')}


def check_files(plan, data):
    """Check real files; a successful full-write result supplies provenance."""
    count = total = 0
    for parent, dirs, files in os.walk(data):
        for name in dirs + files:
            path = Path(parent)/name
            if path.is_symlink():
                raise ValueError('dataset contains a symlink: ' + str(path))
        for name in files:
            path = Path(parent)/name
            if not path.is_file() or path.stat().st_size != plan['file_size']:
                raise ValueError('dataset file type/size mismatch: ' + str(path))
            count += 1
            total += path.stat().st_size
    if (count, total) != (plan['file_count'], plan['dataset_bytes']):
        raise ValueError('dataset count/size mismatch: %d files, %d bytes' % (count, total))


def tool_metrics(plan, step):
    direction = 'write' if step['phase'] in ('write','prepare') else 'read'
    if plan['tool'] == 'fio':
        jobs = json.loads(Path(step['result_path']).read_text())['jobs']
        if not jobs or any(int(job.get('error',0)) for job in jobs):
            raise ValueError('fio reported a job error or no jobs')
        actual = sum(int(job.get(direction,{}).get('io_bytes',0)) for job in jobs)
        # Keep individual percentiles/queue distributions; do not average P99.
        metrics = {'actual_bytes':actual, 'jobs':jobs}
    elif plan['tool'] == 'elbencho':
        phases = []
        for line in Path(step['result_path']).read_text().splitlines():
            if line.strip():
                value=json.loads(line)
                phases.extend(value if isinstance(value,list) else [value])
        matching = [p for p in phases if p.get('phase_type','').upper()==direction.upper()]
        if len(matching) != 1:
            raise ValueError('elbencho result must contain one completed data phase')
        metrics = {'actual_bytes':int(matching[0]['last_done']['bytes']), 'phases':phases}
    else:
        name = {'create':'creation','stat':'stat','remove':'removal'}[step['phase']]
        log = Path(step['log_path']).read_text(errors='replace')
        matches = re.findall(r'File\s+'+name+r'\s*:?\s+([0-9.eE+\-]+)\s+([0-9.eE+\-]+)\s+([0-9.eE+\-]+)',log,re.I)
        if not matches:
            raise ValueError('mdtest summary missing for '+name)
        rate=float(matches[-1][2])
        if rate <= 0:
            raise ValueError('mdtest reported no completed operations')
        version = re.search(r'mdtest-(\S+) was launched',log)
        if not version:
            raise ValueError('mdtest version banner missing')
        return {'operations_per_second':rate, 'tool_version':version[1]}
    # Timed T02 can do more/fewer bytes; every finite data phase must finish.
    timed = plan['runtime'] and step['phase']=='read'
    if metrics['actual_bytes'] <= 0 or (not timed and metrics['actual_bytes'] != plan['dataset_bytes']):
        raise ValueError('incomplete I/O: got %d bytes, expected %d' %
                         (metrics['actual_bytes'],plan['dataset_bytes']))
    return metrics


def write_summary(plan, report):
    groups = {}
    for result in report['results']:
        if result.get('success') and result['measured']:
            groups.setdefault(result['phase'],[]).append(result)
    report['statistics'] = {}
    for phase, rows in groups.items():
        stats = {'samples':len(rows)}
        for key in ('elapsed_seconds','effective_GiB_per_second','files_per_second','operations_per_second'):
            values = [r[key] for r in rows if key in r]
            if values:
                stats[key] = dict(median=statistics.median(values),min=min(values),max=max(values))
        report['statistics'][phase] = stats
    output = Path(plan['output'])
    (output/'summary.json').write_text(json.dumps(report,indent=2))
    lines = ['# AI Storage 单客户端存储测试', '', '状态：'+report['status'],
        '', '场景：'+plan['tool']+' / '+plan['scenario'],
        '', '数据目录：`'+plan['data_root']+'`',
        '', '缓存说明：'+plan['cache_note'],
        '', '每组逻辑数据量：%d bytes；文件数：%d；单文件：%d bytes；请求块：%d bytes。' %
            (plan['dataset_bytes'],plan['file_count'],plan['file_size'],plan['block_size']),
        '', '并发：%d；请求队列深度：%d；direct=%d。实际队列分布和延迟保留在原始结果中。' %
            (plan['workers'],plan['iodepth'],plan['direct']),
        '', '预填充与校验不计入性能统计；耗时使用外部单调时钟，包含进程启动和最后同步。',
        ('数据回收由矩阵管理；成功组合按 matrix-plan.json 策略回收，失败保留现场。' if plan.get('managed_by_matrix')
         else '本单组合运行不自动清理文件。') + '不自动清除缓存。存储协议、节点分布、QoS 和缩减比需结合 environment.json 和存储侧记录核实。',
        '', '| 阶段 | 轮数 | 耗时中位数 [最小, 最大] 秒 | 有效 GiB/s 中位数 |',
        '|---|---:|---|---:|']
    for phase, stats in report['statistics'].items():
        times = stats['elapsed_seconds']
        bw = stats.get('effective_GiB_per_second',{}).get('median')
        lines.append('| %s | %d | %.3f [%.3f, %.3f] | %s |' %
                     (phase,stats['samples'],times['median'],times['min'],times['max'],
                      '—' if bw is None else '%.3f' % bw))
    if report.get('error'):
        lines += ['', '错误：'+report['error']]
    lines += ['', '完整参数、实际字节数、独立轮次指标及原始结果路径见 summary.json 和 plan.json。',
              'T02 的有效吞吐包含预热的外部耗时；测量窗口带宽与延迟以 fio 原始 JSON 为准。']
    (output/'summary.md').write_text('\n'.join(lines)+'\n')


def execute(plan):
    output = Path(plan['output'])
    output.mkdir(parents=True, exist_ok=False)
    (output/'plan.json').write_text(json.dumps(plan,indent=2))
    report = {'status':'RUNNING','plan':plan,'results':[],'statistics':{}}
    start = time.monotonic()
    try:
        if not Path(plan['mount']).is_dir():
            raise ValueError('mount directory does not exist')
        tool = plan['tool']
        binaries = {name:shutil.which(name) for name in ([tool,'mpirun'] if tool=='mdtest' else [tool])}
        if not all(binaries.values()):
            raise ValueError('missing benchmark executable: '+str(binaries))
        versions = {}
        for name, binary in binaries.items():
            if name == 'mdtest':
                # mdtest has no portable --version option; its run banner is authoritative.
                versions[name] = 'pending first phase banner'
                continue
            result = subprocess.run([binary,'--version'],capture_output=True,text=True,timeout=30)
            if result.returncode:
                raise ValueError('cannot query tool version: '+name)
            versions[name] = (result.stdout + result.stderr).strip()
        if tool=='fio' and not versions['fio'].startswith('fio-'):
            raise ValueError('fio executable is not the Flexible I/O tester')
        environment = {'hostname':socket.gethostname(),'versions':versions,
                       'cache_note':plan['cache_note'], 'storage_observations':'Record storage nodes, access protocol, NIC, QoS and reduction ratio where applicable.'}
        for name in ('meminfo','mounts','self/mountinfo'):
            path=Path('/proc')/name
            if path.exists():
                environment[name]=path.read_text()
        (output/'environment.json').write_text(json.dumps(environment,indent=2))
        root = Path(plan['data_root'])
        if plan['phase'] != 'measure':
            # Exclusive identity reservation prevents overwriting another run.
            root.mkdir(parents=True,exist_ok=False)
        elif root.is_symlink() or not root.is_dir():
            raise ValueError('prepared dataset directory missing or symlinked')
        for step in plan['steps']:
            row={key:step[key] for key in ('phase','round','measured','log_path','result_path')}
            row['success']=False
            report['results'].append(row)
            data=Path(step['data_path'])
            manifest=root/(data.name+'.manifest.json')
            if step['fresh']:
                if plan['dataset_bytes'] and shutil.disk_usage(root).free < plan['dataset_bytes'] * 1.05:
                    raise ValueError('insufficient free space for next dataset plus 5% headroom')
                data.mkdir(exist_ok=False)
            elif tool!='mdtest':
                if data.is_symlink() or not data.is_dir():
                    raise ValueError('prepared dataset missing or symlinked')
                if json.loads(manifest.read_text()) != dataset_identity(plan):
                    raise ValueError('prepared dataset identity mismatch')
                check_files(plan,data)
            argv=list(step['argv'])
            argv[0]=binaries[argv[0]]
            if tool=='mdtest':
                argv[argv.index('mdtest')]=binaries['mdtest']
                if os.geteuid()==0:
                    argv.insert(1,'--allow-run-as-root')
            if 'fio_config' in step:
                Path(argv[1]).write_text(step['fio_config'])
            Path(step['log_path']+'.command.json').write_text(json.dumps(argv))
            print('%s round=%s %s -> %s' % (tool,step['round'],step['phase'],step['log_path']),flush=True)
            t0=time.monotonic()
            with open(step['log_path'],'w') as log:
                result=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT)
            row.update(elapsed_seconds=time.monotonic()-t0,returncode=result.returncode)
            if result.returncode:
                raise ValueError('tool exited %d; see %s' % (result.returncode,step['log_path']))
            row.update(tool_metrics(plan,step))
            if tool=='mdtest':
                environment['versions']['mdtest']=row['tool_version']
                (output/'environment.json').write_text(json.dumps(environment,indent=2))
                if step['phase'] in ('create','stat'):
                    check_files(plan,data)
            if tool!='mdtest' and step['phase'] in ('prepare','write'):
                check_files(plan,data)
                manifest.write_text(json.dumps(dataset_identity(plan)))
            if 'actual_bytes' in row:
                row['effective_GiB_per_second']=row['actual_bytes']/row['elapsed_seconds']/1024**3
                if not (plan['runtime'] and step['phase']=='read'):
                    row['files_per_second']=plan['file_count']/row['elapsed_seconds']
            row['success']=True
            write_summary(plan,report)
        report['status']='PASS'
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        report.update(status='FAIL',error=str(error) or 'interrupted')
    finally:
        report['total_elapsed_seconds']=time.monotonic()-start
        write_summary(plan,report)
        print('AI Storage %s; report: %s' % (report['status'],output/'summary.md'),flush=True)
    return 0 if report['status']=='PASS' else 1


def build_matrix(a):
    """Filter the documented pairs; never cross-product unrelated parameters."""
    if a.phase == 'measure' and not a.data_id:
        raise ValueError('--phase measure requires --data-id from prepare')
    base_id = a.data_id or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:12]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,69}', base_id):
        raise ValueError('matrix data-id must be a safe identifier of at most 70 characters')
    pairs = [(fs, bs) for fs, blocks in SMALL_FILE_MATRIX for bs in blocks
             if (a.file_size is None or a.file_size == fs) and (a.bs is None or a.bs == bs)]
    if not pairs:
        raise ValueError('no documented file-size/block-size pairs match; specify both for a custom pair')
    plans = []
    seen = set()
    create_write = a.tool == 'elbencho' and a.scenario.endswith('-write')
    for fs, bs in pairs:
        if a.phase == 'prepare' and fs in seen:
            continue
        options = argparse.Namespace(**vars(a))
        options.file_size, options.bs = fs, bs
        options.data_id = base_id + '-f' + str(fs)
        if create_write:
            options.data_id += '-b' + str(bs)
        elif a.phase == 'all' and fs in seen:
            options.phase = 'measure'
        plan=build_plan(options)
        plan['managed_by_matrix']=True
        plans.append(plan)
        seen.add(fs)
    return dict(kind='small-file-matrix', tool=a.tool, scenario=a.scenario, phase=a.phase,
                data_id=base_id, combination_count=len(plans), plans=plans,
                output=str(Path(a.output).absolute()/('ai-storage-matrix-'+uuid.uuid4().hex[:12])),
                cleanup_generated_data=a.phase=='all',
                peak_dataset_bytes=(max(p['peak_dataset_bytes'] for p in plans) if a.phase=='all'
                                    else sum({p['data_root']:p['dataset_bytes'] for p in plans}.values())))


def execute_matrix(matrix):
    output=Path(matrix['output'])
    output.mkdir(parents=True,exist_ok=False)
    (output/'matrix-plan.json').write_text(json.dumps(matrix,indent=2))
    summary={'status':'RUNNING','total':len(matrix['plans']),'passed':0,'failed':0,
             'not_run':len(matrix['plans']),'results':[]}
    owned=set()
    started=time.monotonic()

    def save():
        summary['total_elapsed_seconds']=time.monotonic()-started
        summary['not_run']=summary['total']-len(summary['results'])
        (output/'matrix-summary.json').write_text(json.dumps(summary,indent=2))
        lines=['# AI Storage 小文件组合汇总','', '状态：'+summary['status'],
               '', '通过 %d；失败 %d；未运行 %d；总耗时 %.3f 秒。' %
               (summary['passed'],summary['failed'],summary['not_run'],summary['total_elapsed_seconds']),
               '', '| file_size (bytes) | block_size (bytes) | 状态 | 组合报告 |',
               '|---:|---:|---|---|']
        for row in summary['results']:
            lines.append('| %d | %d | %s | [summary](%s) |' %
                         (row['file_size'],row['block_size'],row['status'],row['report']))
        if summary.get('error'):
            lines += ['',summary['error']]
        (output/'matrix-summary.md').write_text('\n'.join(lines)+'\n')

    try:
        save()
        for index, plan in enumerate(matrix['plans']):
            print('Combination %d/%d: file_size=%d block_size=%d' %
                  (index+1,len(matrix['plans']),plan['file_size'],plan['block_size']),flush=True)
            code=execute(plan)
            row={'file_size':plan['file_size'],'block_size':plan['block_size'],
                 'status':'PASS' if code==0 else 'FAIL',
                 'report':str(Path(plan['output'])/'summary.md'), 'data_root':plan['data_root']}
            detail=Path(plan['output'])/'summary.json'
            if detail.exists():
                row['statistics']=json.loads(detail.read_text()).get('statistics',{})
            summary['results'].append(row)
            summary['passed' if code==0 else 'failed']+=1
            if code:
                summary['status']='FAIL'
                break
            root=Path(plan['data_root'])
            if plan['phase']=='all':
                owned.add(str(root))
            used_later=any(p['data_root']==str(root) for p in matrix['plans'][index+1:])
            if matrix['cleanup_generated_data'] and str(root) in owned and not used_later:
                # Only a successful exclusive root created by this batch is eligible.
                if root.is_symlink() or not root.is_dir():
                    raise ValueError('generated data directory changed before cleanup: '+str(root))
                shutil.rmtree(root)
                row['data_reclaimed']=True
            save()
        else:
            summary['status']='PASS'
    except (OSError, ValueError, KeyboardInterrupt) as error:
        summary.update(status='FAIL',error=str(error) or 'interrupted')
    finally:
        save()
        print('AI Storage matrix %s; report: %s' % (summary['status'],output/'matrix-summary.md'),flush=True)
    return 0 if summary['status']=='PASS' else 1


def main(argv=None):
    p = parser()
    a = p.parse_args(argv)
    try:
        if a.tool in ('fio','elbencho') and a.scenario in ('ai-storage-t03-read','ai-storage-t03-write') and not (a.file_size and a.bs):
            matrix=build_matrix(a)
            if a.dry_run:
                print(json.dumps(matrix,indent=2))
                return 0
            return execute_matrix(matrix)
        plan = build_plan(a)
        if a.dry_run:
            print(json.dumps(plan, indent=2))
            return 0
        return execute(plan)
    except (ValueError, OSError) as error:
        p.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
