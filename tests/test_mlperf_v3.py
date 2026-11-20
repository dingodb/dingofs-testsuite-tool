import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import shlex

import pytest

ROOT = Path(__file__).resolve().parents[1]


def plan(*args):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/mlperf_benchmark.py'),
                             '--dry-run', *args], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_training_explicit_v3_preserves_model():
    p = plan('--mlperf-scenario', 'training', '--mlperf-model', 'cosmoflow', '--file-count', '4')
    assert p['format'] == 'dtt-mlperf-v2'
    assert p['engine_version'] == '3.0.46'
    assert p['mlperf_model'] == 'cosmoflow'


def test_checkpoint_read_has_explicit_preparation():
    p = plan('--mlperf-scenario', 'checkpointing', '--mlperf-model', 'custom',
             '--checkpoint-size', '16777216', '--checkpoint-mode', 'read', '--checkpoint-count', '2')
    assert p['preparation_required'] is True
    assert p['checkpoint_mode'] == 'read'
    assert p['total_size'] == '33554432'


def test_kvcache_capacity_and_duration_are_not_dataset_size():
    p = plan('--mlperf-scenario', 'kvcache', '--mlperf-model', 'tiny-1b',
             '--runtime-seconds', '10', '--total-size', '1073741824', '--concurrency', '2')
    assert p['runtime_seconds'] == 10
    assert p['capacity_bytes'] == 1073741824
    assert p['concurrency'] == 2
    assert p['file_count'] == 0


@pytest.mark.parametrize('args', [
    ['--mlperf-scenario', 'kvcache', '--mlperf-model', 'resnet50'],
    ['--mlperf-scenario', 'checkpointing', '--runtime-seconds', '10'],
    ['--mlperf-scenario', 'training', '--checkpoint-mode', 'read', '--file-count', '4'],
    ['--mlperf-scenario', 'kvcache', '--gpu-memory-gib', 'nan'],
])
def test_reject_incompatible_or_nonfinite_parameters(args):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/mlperf_benchmark.py'),
                             '--dry-run', *args], text=True, capture_output=True)
    assert result.returncode != 0


def adapter():
    sys.path.insert(0, str(ROOT / 'scripts'))
    import mlperf_v3
    return mlperf_v3


def test_checkpoint_native_commands_separate_preparation(tmp_path):
    p = plan('--mlperf-scenario', 'checkpointing', '--mlperf-model', 'custom',
             '--checkpoint-size', '16777216', '--checkpoint-mode', 'read', '--checkpoint-count', '2')
    commands = adapter().native_commands(p, tmp_path, preparation=True)
    assert commands[-1][commands[-1].index('--num-checkpoints-write') + 1] == '2'
    assert commands[-1][commands[-1].index('--num-checkpoints-read') + 1] == '0'
    commands = adapter().native_commands(p, tmp_path, preparation=False)
    assert commands[-1][commands[-1].index('--num-checkpoints-write') + 1] == '0'
    assert commands[-1][commands[-1].index('--num-checkpoints-read') + 1] == '2'


def test_custom_checkpoint_parallelism_matches_processes(tmp_path):
    p = plan('--mlperf-scenario','checkpointing','--mlperf-model','custom','--concurrency','2')
    command = adapter().native_commands(p,tmp_path)[-1]
    assert 'model.parallelism.tensor=2' in command


def test_kv_native_command_propagates_capacity(tmp_path):
    p = plan('--mlperf-scenario', 'kvcache', '--mlperf-model', 'tiny-1b',
             '--runtime-seconds', '10', '--total-size', '1073741824')
    argv = adapter().native_commands(p, tmp_path)[0]
    assert argv[argv.index('--storage-capacity-gb') + 1] == '1.0'
    assert argv[argv.index('--duration') + 1] == '10'
    assert '--precondition' not in argv


def test_shell_wrapper_forwards_kvcache(tmp_path):
    command = ('source ' + shlex.quote(str(ROOT / 'dingofs-testsuite-tool')) + '\n' +
               'dingofs-testsuite-tool -t mlperf -s benchmark -m /data -o /output '
               '--mlperf-scenario kvcache --mlperf-model tiny-1b --total-size 1073741824 '
               '--runtime-seconds 10 --dry-run')
    result = subprocess.run(['bash', '-c', command], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['mlperf_scenario'] == 'kvcache'


def test_native_training_metadata_string_overrides(tmp_path):
    p = plan('--mlperf-scenario','training','--mlperf-model','cosmoflow','--file-count','4','--mlperf-epochs','1')
    (tmp_path/'summary.json').write_text(json.dumps({'start':'start','end':'end','epochs':1,'num_accelerators':1,
        'metric':{'train_throughput_mean_samples_per_second':2,'train_io_mean_MB_per_second':3,'train_au_mean_percentage':50,
                  'train_throughput_samples_per_second':[2], 'train_au_percentage':[50]}}))
    (tmp_path/'training_test_metadata.json').write_text(json.dumps({'benchmark_type':'TRAINING','model':'cosmoflow',
        'parameters':{'dataset':{'num_files_train':'4'},'train':{'epochs':'1'}}}))
    (tmp_path/'0_per_epoch_stats.json').write_text('{"1":{"start":"start","end":"end","duration":"0.05"}}')
    assert adapter().native_metrics(p,tmp_path)['samples_per_second'] == 2


@pytest.mark.parametrize('exit_code', [0, 7])
def test_checkpoint_preparation_without_results_cannot_pass(tmp_path, monkeypatch, exit_code):
    p = plan('--mlperf-scenario','checkpointing','--checkpoint-mode','read','--checkpoint-size','1024',
             '--mount',str(tmp_path),'--output',str(tmp_path/'output'))
    module = adapter()
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, 'mlpstorage_py.benchmarks.dlio', SimpleNamespace(
        CheckpointingBenchmark=SimpleNamespace(required_bytes_for_capacity_gate=lambda probe:33554432)))
    monkeypatch.setattr(module.importlib.metadata, 'version', lambda name:'3.0.46')
    monkeypatch.setattr(module.legacy, 'run_command', lambda *args:(exit_code, .1))
    report = module.execute(p)
    assert report['status'] == 'failed'
    assert not report['rounds']
    assert report['preparation'] is None
    assert ('preparation failed' if exit_code else 'expected exactly one native summary') in report['error']


def test_native_wrong_scene_and_nonfinite_are_rejected(tmp_path):
    p = plan('--mlperf-scenario','kvcache','--runtime-seconds','5')
    (tmp_path/'kv-result.json').write_text('{"summary":{"total_requests":NaN}}')
    with pytest.raises(ValueError):
        adapter().native_metrics(p,tmp_path)


def test_legacy_v3_model_bridge_preserves_intent():
    args = adapter().legacy_arguments('cosmoflow', '2', '/output', {
        'SCALE':'4', 'NUM_ACCELERATORS':'1', 'LOOPS':'2'})
    p = adapter().build_plan(adapter().parser().parse_args(args))
    assert (p['mlperf_model'], p['file_count'], p['rounds'], p['concurrency']) == ('cosmoflow',4,2,2)


@pytest.mark.parametrize('env', [{'SCALE':'auto'}, {'EXTRA_PARAMS':'train.epochs=7'},
                                 {'HOSTS':'server1,server2'}, {'SKIP_DATAGEN':'true'}])
def test_legacy_v3_unsupported_options_are_not_ignored(env):
    with pytest.raises(ValueError, match='benchmark'):
        adapter().legacy_arguments('resnet50', '1', '/output', env)


def test_training_incomplete_epoch_rejected(tmp_path):
    test_native_training_metadata_string_overrides(tmp_path)
    (tmp_path/'0_per_epoch_stats.json').write_text('{}')
    p = plan('--mlperf-scenario','training','--mlperf-model','cosmoflow','--file-count','4','--mlperf-epochs','1')
    with pytest.raises(ValueError, match='epoch'):
        adapter().native_metrics(p, tmp_path)


def checkpoint_fixture(tmp_path):
    p = plan('--mlperf-scenario','checkpointing','--checkpoint-size','16777216','--concurrency','2')
    (tmp_path/'summary.json').write_text(json.dumps({'start':'start','end':'end','metric':{
        'save_checkpoint_io_mean_GB_per_second':2, 'save_checkpoint_duration_mean_seconds':.1,
        'load_checkpoint_io_mean_GB_per_second':3, 'load_checkpoint_duration_mean_seconds':.2,
        'checkpoint_size_GB':.0078125}}))
    metadata = {'benchmark_type':'checkpointing','model':'llama3-8b','num_processes':2,'parameters':{
        'model':{'type':'custom','num_layers':'-1','model_size_bytes':'8388608','optimization_groups':'[]',
                 'parallelism':{'tensor':'2','pipeline':'1','zero_stage':'0','data':1}},
        'checkpoint':{'num_checkpoints_write':1,'num_checkpoints_read':1,
                      'checkpoint_folder':p['data_dir']+'/llama3-8b'}}}
    (tmp_path/'checkpointing_metadata.json').write_text(json.dumps(metadata))
    for rank in range(2):
        (tmp_path/f'{rank}_per_epoch_stats.json').write_text(json.dumps({'1':{
            'save_ckpt1':{'start':'start','end':'end','duration':.1},
            'load_ckpt1':{'start':'start','end':'end','duration':.2}}}))
    return p


@pytest.mark.parametrize('mutation', ['size','concurrency','missing_rank','directory'])
def test_checkpoint_effective_identity_required(tmp_path, mutation):
    p = checkpoint_fixture(tmp_path)
    if mutation == 'size': p['checkpoint_size'] = 1024**3
    if mutation == 'concurrency': p['concurrency'] = 8
    if mutation == 'directory': p['data_dir'] += '-wrong'
    if mutation == 'missing_rank': (tmp_path/'1_per_epoch_stats.json').unlink()
    with pytest.raises(ValueError):
        adapter().native_metrics(p,tmp_path)


def test_checkpoint_metrics_are_aggregate(tmp_path):
    p = checkpoint_fixture(tmp_path)
    metrics = adapter().native_metrics(p,tmp_path)
    assert metrics['checkpoint_gib'] == .015625
    assert metrics['write_gib_per_second'] == 4
    assert metrics['read_gib_per_second'] == 6


def test_kv_requires_native_effective_config(tmp_path):
    p = plan('--mlperf-scenario','kvcache','--runtime-seconds','5')
    (tmp_path/'kv-result.json').write_text(json.dumps({'summary':{
        'total_requests':5,'elapsed_time':5,'avg_throughput_tokens_per_sec':10,'requests_per_second':1,
        'end_to_end_latency_ms':{'mean':1,'p95':2,'p99':3},'storage_io_latency_ms':{'mean':1,'p95':2,'p99':3}}}))
    with pytest.raises(ValueError, match='configuration'):
        adapter().native_metrics(p,tmp_path)


@pytest.mark.parametrize('index', range(4))
def test_genuine_native_fixtures_replay(tmp_path, index):
    case = json.loads((ROOT/'tests/fixtures/mlperf_v3_native.json').read_text())['cases'][index]
    for name, content in case['files'].items():
        (tmp_path/name).write_text(json.dumps(content))
    assert adapter().native_metrics(case['plan'], tmp_path) == case['expected_metrics']


@pytest.mark.parametrize('key,value', [('mlperf_model','llama3.1-70b-instruct'),('concurrency',512),
                                      ('capacity_bytes',1024**4),('gpu_memory_gib',1000)])
def test_genuine_kv_wrong_request_rejected(tmp_path, key, value):
    case = json.loads((ROOT/'tests/fixtures/mlperf_v3_native.json').read_text())['cases'][3]
    for name, content in case['files'].items():
        (tmp_path/name).write_text(json.dumps(content))
    case['plan'][key] = value
    with pytest.raises(ValueError, match='configuration'):
        adapter().native_metrics(case['plan'], tmp_path)
