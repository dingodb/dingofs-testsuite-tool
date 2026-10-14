"""AI Storage plans are tested without launching a storage benchmark."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/ai_storage_scenarios.py'


class AIStoragePlans(unittest.TestCase):
    def plan(self, tool, scenario, *extra):
        result = subprocess.run([sys.executable, str(SCRIPT), '--tool', tool,
            '--scenario', scenario, '--mount', '/mnt/test', '--output', '/tmp/results',
            '--data-id', 'example', '--dry-run', *extra], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_total_fio_bytes_are_split_not_multiplied(self):
        plan = self.plan('fio', 'ai-storage-b01-read', '--jobs', '8')
        self.assertEqual(plan['dataset_bytes'], 274877906944)
        cfg = plan['steps'][0]['fio_config']
        self.assertIn('size=34359738368', cfg)
        self.assertIn('numjobs=8', cfg)
        self.assertEqual(plan['steps'][0]['phase'], 'prepare')
        reads = [s for s in plan['steps'] if s['phase'] == 'read']
        self.assertEqual(len(reads), 3)
        self.assertIn('allow_file_create=0', reads[0]['fio_config'])
        self.assertNotIn('time_based=1', reads[0]['fio_config'])

    def test_both_tools_cover_small_reads_and_writes(self):
        for tool in ('fio', 'elbencho'):
            for operation in ('read', 'write'):
                with self.subTest(tool=tool, operation=operation):
                    plan = self.plan(tool, 'ai-storage-t03-' + operation,
                                     '--file-size', '10M', '--bs', '2M', '--jobs', '8', '--threads', '8')
                    self.assertEqual(plan['dataset_bytes'], 1048576000000)
                    self.assertEqual(plan['file_count'], 100000)
                    if tool == 'fio':
                        self.assertIn('nrfiles=12500', plan['steps'][0]['fio_config'])
                        self.assertIn('filesize=10485760', plan['steps'][0]['fio_config'])
                        self.assertEqual(plan['steps'][0]['phase'], 'prepare')
                    else:
                        argv = plan['steps'][0]['argv']
                        self.assertEqual(argv[argv.index('-N') + 1], '12500')
                        self.assertIn('--blockvarpct', argv)
                        writes = [s for s in plan['steps'] if s['phase'] == 'write']
                        if operation == 'write':
                            self.assertEqual(len({s['data_path'] for s in writes}), 3)

    def test_small_block_sizes_and_sizes_are_independent(self):
        for size, block, total in [('4K','4K',409600000), ('64K','16K',6553600000),
                                   ('256K','64K',26214400000), ('1M','256K',104857600000)]:
            for tool in ('fio', 'elbencho'):
                plan = self.plan(tool, 'ai-storage-t03-read', '--file-size', size, '--bs', block)
                self.assertEqual(plan['dataset_bytes'], total)

    def test_random_read_has_separate_prefill_and_timed_measurement(self):
        plan = self.plan('fio', 'ai-storage-t02-read', '--iodepth', '32')
        self.assertNotIn('runtime=', plan['steps'][0]['fio_config'])
        cfg = plan['steps'][1]['fio_config']
        for setting in ('rw=randread','runtime=600','ramp_time=30','iodepth=32','direct=1'):
            self.assertIn(setting, cfg)

    def test_model_and_training_are_exact_finite_file_sets(self):
        for scenario, size, count in [('ai-storage-t01-read',1099511627776,1024),
                                       ('ai-storage-l01-read',68719476736,16)]:
            plan = self.plan('elbencho', scenario, '--threads', '8')
            self.assertEqual(plan['dataset_bytes'], size)
            self.assertEqual(plan['file_count'], count)
            self.assertNotIn('--infloop', plan['steps'][1]['argv'])
            self.assertNotIn('--timelimit', plan['steps'][1]['argv'])
        plan = self.plan('elbencho','ai-storage-l01-read','--dataset-size','16G','--threads','8')
        self.assertEqual(plan['file_count'],4)

    def test_checkpoint_sync_and_verification_are_separate(self):
        plan = self.plan('fio','ai-storage-c01','--jobs','4')
        writes = [s for s in plan['steps'] if s['phase'] == 'write']
        self.assertEqual(len({s['data_path'] for s in writes}), 3)
        self.assertEqual(plan['peak_dataset_bytes'],206158430208)
        for step in writes:
            self.assertIn('end_fsync=1',step['fio_config'])
            self.assertIn('direct=0',step['fio_config'])
        self.assertEqual(len([s for s in plan['steps'] if s['phase']=='verify']),3)

    def test_metadata_count_stays_fixed_with_ranks(self):
        for layout in ('unique','shared'):
            plan = self.plan('mdtest','ai-storage-t03','--jobs','32','--layout',layout)
            argv = plan['steps'][0]['argv']
            self.assertEqual(argv[argv.index('-n')+1],'3125')
            self.assertNotIn('-S',argv)
            self.assertEqual('-u' in argv,layout=='unique')
            self.assertEqual([s['phase'] for s in plan['steps'][:3]],['create','stat','remove'])
            self.assertIn('localhost:32',argv)

    def test_invalid_geometry_and_unimplemented_modes_fail(self):
        for extra in [('--file-size','4K','--bs','64K'),('--file-count','100001','--jobs','8'),
                      ('--data-id','../outside'),('--runtime','600'),('--repeats','0')]:
            result = subprocess.run([sys.executable,str(SCRIPT),'--tool','fio','--scenario',
                'ai-storage-t03-read','--dry-run',*extra],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('error:',result.stderr.lower())

    def test_dry_run_does_not_touch_mount_or_output(self):
        with tempfile.TemporaryDirectory() as temp:
            mount = str(Path(temp)/'absent-mount'); out = str(Path(temp)/'absent-output')
            self.plan('fio','ai-storage-b01-read','--mount',mount,'--output',out)
            self.assertEqual(list(Path(temp).iterdir()),[])


class AIStorageExecution(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('ai_storage', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'mount').mkdir()

    def plan(self, *extra):
        args = self.module.parser().parse_args(['--tool','fio','--scenario','ai-storage-t03-read',
            '--mount',str(self.root/'mount'),'--output',str(self.root/'output'),
            '--file-size','4K','--file-count','4','--jobs','2','--bs','4K',*extra])
        return self.module.build_plan(args)

    def fake_tool(self, argv, **kwargs):
        if '--version' in argv:
            return subprocess.CompletedProcess(argv,0,stdout='fio-3.38\n',stderr='')
        import configparser
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read(argv[1]); g = cfg['global']
        if g['rw']=='write':
            for j in range(int(g['numjobs'])):
                for f in range(int(g['nrfiles'])):
                    (Path(g['directory'])/f'file.{j}.{f}').write_bytes(b'x'*int(g['filesize']))
        direction = 'write' if g['rw']=='write' else 'read'
        report = {'jobs':[{'error':0,direction:{'io_bytes':16384,'runtime':10},'iodepth_level':{'1':100}}]}
        Path(next(x.split('=',1)[1] for x in argv if x.startswith('--output='))).write_text(json.dumps(report))
        return subprocess.CompletedProcess(argv,0)

    def test_records_prepare_separately_and_requires_manifest_for_reuse(self):
        self.assertTrue(hasattr(self.module,'execute'),'execution support missing')
        plan = self.plan('--data-id','reuse')
        with patch.object(self.module.shutil,'which',side_effect=lambda name:'/fake/'+name), \
             patch.object(self.module.subprocess,'run',side_effect=self.fake_tool):
            self.assertEqual(self.module.execute(plan),0)
            summary = json.loads((Path(plan['output'])/'summary.json').read_text())
            self.assertEqual(summary['status'],'PASS')
            self.assertEqual(summary['statistics']['read']['samples'],3)
            self.assertNotIn('prepare',summary['statistics'])
            reused = self.plan('--data-id','reuse','--phase','measure')
            self.assertEqual(self.module.execute(reused),0)
            next(Path(plan['data_root']).rglob('file.*')).unlink()
            missing = self.plan('--data-id','reuse','--phase','measure')
            self.assertEqual(self.module.execute(missing),1)

    def test_failed_prefill_stops_before_measurement(self):
        self.assertTrue(hasattr(self.module,'execute'),'execution support missing')
        plan = self.plan()
        def fail(argv, **kwargs):
            if '--version' in argv:
                return self.fake_tool(argv,**kwargs)
            return subprocess.CompletedProcess(argv,23)
        with patch.object(self.module.shutil,'which',side_effect=lambda name:'/fake/'+name), \
             patch.object(self.module.subprocess,'run',side_effect=fail):
            self.assertEqual(self.module.execute(plan),1)
        summary = json.loads((Path(plan['output'])/'summary.json').read_text())
        self.assertEqual(summary['status'],'FAIL')
        self.assertEqual(len(summary['results']),1)
        self.assertFalse(list(Path(plan['data_root']).glob('*.manifest.json')))

    def test_short_successful_tool_result_is_not_a_complete_dataset(self):
        self.assertTrue(hasattr(self.module,'execute'),'execution support missing')
        plan = self.plan()
        def short(argv, **kwargs):
            result=self.fake_tool(argv,**kwargs)
            if '--version' not in argv:
                path=Path(next(x.split('=',1)[1] for x in argv if x.startswith('--output=')))
                path.write_text('{"jobs":[{"error":0,"write":{"io_bytes":4096}}]}')
            return result
        with patch.object(self.module.shutil,'which',side_effect=lambda name:'/fake/'+name), \
             patch.object(self.module.subprocess,'run',side_effect=short):
            self.assertEqual(self.module.execute(plan),1)

    def test_elbencho_counts_last_done_bytes_not_fastest_thread(self):
        plan=self.plan(); plan['tool']='elbencho'
        result=self.root/'elbencho.json'
        result.write_text(json.dumps({'phase_type':'READ',
            'first_done':{'bytes':'4096'},'last_done':{'bytes':'16384'}})+'\n')
        step={'phase':'read','result_path':str(result)}
        self.assertEqual(self.module.tool_metrics(plan,step)['actual_bytes'],16384)
        result.write_text(json.dumps({'phase_type':'READ','last_done':{'bytes':'4096'}})+'\n')
        with self.assertRaises(ValueError):
            self.module.tool_metrics(plan,step)

    def test_missing_data_directory_is_not_created_by_measure(self):
        plan=self.plan('--phase','measure','--data-id','missing')
        with patch.object(self.module.shutil,'which',side_effect=lambda name:'/fake/'+name), \
             patch.object(self.module.subprocess,'run',side_effect=self.fake_tool):
            self.assertEqual(self.module.execute(plan),1)
        self.assertFalse(Path(plan['data_root']).exists())

    def test_mdtest_uses_banner_version_without_unsupported_version_flag(self):
        args=self.module.parser().parse_args(['--tool','mdtest','--scenario','ai-storage-t03',
            '--mount',str(self.root/'mount'),'--output',str(self.root/'output'),
            '--file-count','4','--jobs','2'])
        plan=self.module.build_plan(args)
        self.assertEqual(plan['steps'][0]['argv'][2], 'localhost:2')
        def metadata(argv,**kwargs):
            if argv[0].endswith('mdtest'):
                return subprocess.CompletedProcess(argv,1,stdout='',stderr='unknown option')
            if '--version' in argv:
                return subprocess.CompletedProcess(argv,0,stdout='Open MPI 4.1.6',stderr='')
            data=Path(argv[argv.index('-d')+1])
            if '-C' in argv:
                for n in range(4): (data/str(n)).touch()
                name='creation'
            elif '-T' in argv:
                name='stat'
            else:
                for file in data.iterdir(): file.unlink()
                name='removal'
            kwargs['stdout'].write('mdtest-4.0.0 was launched with 2 total task(s) on 1 node(s)\n'
                                    f'File {name}   100.0 100.0 100.0 0.0\n')
            return subprocess.CompletedProcess(argv,0)
        with patch.object(self.module.shutil,'which',side_effect=lambda name:'/fake/'+name), \
             patch.object(self.module.subprocess,'run',side_effect=metadata):
            self.assertEqual(self.module.execute(plan),0)
        env=json.loads((Path(plan['output'])/'environment.json').read_text())
        self.assertEqual(env['versions']['mdtest'],'4.0.0')


if __name__ == '__main__':
    unittest.main()
