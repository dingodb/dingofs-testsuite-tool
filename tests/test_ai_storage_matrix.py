import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/ai_storage_scenarios.py'


class SmallFileMatrix(unittest.TestCase):
    def preview(self,*args):
        p=subprocess.run([sys.executable,str(SCRIPT),'--tool','fio','--scenario','ai-storage-t03-read',
                          '--dry-run',*args],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        return json.loads(p.stdout)

    def test_default_runs_all_nineteen_pairs_for_each_tool_and_operation(self):
        expected={4096:1,65536:3,262144:4,1048576:5,10485760:6}
        for tool in ('fio','elbencho'):
            for op in ('read','write'):
                result=self.preview('--tool',tool,'--scenario','ai-storage-t03-'+op)
                self.assertEqual(result.get('combination_count'),19)
                plans=result['plans']
                self.assertEqual({s:sum(p['file_size']==s for p in plans) for s in expected},expected)
                self.assertTrue(all(p['file_count']==100000 for p in plans))
                if tool=='fio' or op=='read':
                    self.assertEqual(sum(p['steps'][0]['phase']=='prepare' for p in plans),5)
                    self.assertEqual(len({p['data_root'] for p in plans}),5)
                else:
                    self.assertEqual(len({p['data_root'] for p in plans}),19)

    def test_one_parameter_filters_and_two_parameters_select_one(self):
        result=self.preview('--file-size','1M')
        self.assertEqual(result.get('combination_count'),5)
        self.assertEqual([p['block_size'] for p in result['plans']],
                         [4096,16384,65536,262144,1048576])
        result=self.preview('--bs','64K')
        self.assertEqual(result.get('combination_count'),4)
        single=self.preview('--file-size','1M','--bs','64K')
        self.assertEqual(single['file_size'],1048576)
        self.assertEqual(single['block_size'],65536)

    def test_prepare_deduplicates_sizes_and_measure_never_prefills(self):
        prepared=self.preview('--phase','prepare','--data-id','dataset')
        self.assertEqual(len(prepared.get('plans',[])),5)
        measured=self.preview('--phase','measure','--data-id','dataset')
        self.assertEqual(len(measured.get('plans',[])),19)
        self.assertEqual({p['data_root'] for p in prepared['plans']},
                         {p['data_root'] for p in measured['plans']})
        self.assertTrue(all(s['phase']=='read' for p in measured['plans'] for s in p['steps']))

    def test_batch_stops_on_failure_preserves_failed_data_and_reports_progress(self):
        spec=importlib.util.spec_from_file_location('ai_storage',SCRIPT)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        self.assertTrue(hasattr(m,'execute_matrix'),'matrix execution missing')
        with tempfile.TemporaryDirectory() as temp:
            args=m.parser().parse_args(['--tool','elbencho','--scenario','ai-storage-t03-write',
                '--file-size','64K','--mount',temp,'--output',temp])
            matrix=m.build_matrix(args)
            calls=[]
            def run(plan):
                calls.append(plan)
                Path(plan['data_root']).mkdir(parents=True)
                (Path(plan['data_root'])/'data').write_text('generated')
                out=Path(plan['output']);out.mkdir(parents=True)
                ok=len(calls)==1
                (out/'summary.json').write_text(json.dumps({'status':'PASS' if ok else 'FAIL','statistics':{}}))
                return 0 if ok else 1
            with patch.object(m,'execute',side_effect=run):
                self.assertEqual(m.execute_matrix(matrix),1)
            self.assertEqual(len(calls),2)
            self.assertFalse(Path(calls[0]['data_root']).exists())
            self.assertTrue(Path(calls[1]['data_root']).exists())
            summary=json.loads((Path(matrix['output'])/'matrix-summary.json').read_text())
            self.assertEqual(summary['passed'],1)
            self.assertEqual(summary['failed'],1)
            self.assertEqual(summary['not_run'],1)

    def test_read_batch_reuses_data_until_last_pair_and_keeps_prepare_datasets(self):
        spec=importlib.util.spec_from_file_location('ai_storage',SCRIPT)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        for phase in ('all','prepare','measure'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temp:
                args=m.parser().parse_args(['--tool','fio','--scenario','ai-storage-t03-read',
                    '--file-size','64K','--phase',phase,'--data-id','owned',
                    '--mount',temp,'--output',temp])
                matrix=m.build_matrix(args)
                root=Path(matrix['plans'][0]['data_root'])
                if phase=='measure': root.mkdir(parents=True)
                def run(plan):
                    if plan['phase'] in ('all','prepare'):
                        Path(plan['data_root']).mkdir(parents=True)
                    else:
                        self.assertTrue(Path(plan['data_root']).exists())
                    return 0
                with patch.object(m,'execute',side_effect=run):
                    self.assertEqual(m.execute_matrix(matrix),0)
                self.assertEqual(root.exists(),phase!='all')


if __name__=='__main__': unittest.main()
