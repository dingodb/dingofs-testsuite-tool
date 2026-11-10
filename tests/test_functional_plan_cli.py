import os
import shlex
import tempfile
import unittest
from pathlib import Path
import test_fio_cli

class FunctionalPlanCLI(unittest.TestCase):
    def test_int_plan_and_cancel_are_mounted_in_job_output(self):
        helper=test_fio_cli.FioCliTest();self.addCleanup(helper.doCleanups)
        # Runner will place the plan inside the task's output directory.
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory)/'runtime';runtime.mkdir()
            for name in ('entrypoint.sh','run_tests.py','test_suite.py','functional_plan.py','env_parser.py','env_setup.py','command_utils.py','mount_subdir_executor.py','trash_executor.py','cache_node_executor.py','hot_upgrade_executor.py','dirstat_executor.py','mds_manage_executor.py','client_mount_ops.py','client_cache_group_ops.py','large_scale_cache_setup.py','large_scale_cache_observer.py'):
                (runtime/name).write_text('fixture')
            old=os.environ.get('DTT_PERFORMANCE_RUNTIME_DIR')
            os.environ['DTT_PERFORMANCE_RUNTIME_DIR']=str(runtime)
            self.addCleanup(lambda: os.environ.pop('DTT_PERFORMANCE_RUNTIME_DIR',None) if old is None else os.environ.__setitem__('DTT_PERFORMANCE_RUNTIME_DIR',old))
            for key,value in {'DTT_CLIENT_BINARY':'/build/client candidate','DTT_CACHE_BINARY':'/build/dingo-cache','DTT_MDS_CLIENT_BINARY':'/build/dingo-mds-client'}.items():
                previous=os.environ.get(key);os.environ[key]=value
                self.addCleanup(lambda k=key,v=previous: os.environ.pop(k,None) if v is None else os.environ.__setitem__(k,v))
            path=Path(directory)/'plan.json';path.write_text('{"version":1,"modules":{"quota":["smoke/a.yaml"]}}')
            result,args=helper._run_wrapper('-t int -s quota --case-plan '+shlex.quote(str(path)))
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn(str(runtime/'env_setup.py')+':/dingofs-integration-test/src/config/env_setup.py:ro',args)
            self.assertIn(str(runtime/'cache_node_executor.py')+':/dingofs-integration-test/src/cache_node_test/executor.py:ro',args)
            self.assertIn('DTT_CLIENT_BINARY=/build/client candidate',args)
            self.assertIn('DTT_CACHE_BINARY=/build/dingo-cache',args)
            self.assertIn('DTT_MDS_CLIENT_BINARY=/build/dingo-mds-client',args)
            self.assertIn('INT_CASE_PLAN=/functional-plan/plan.json',args)
            self.assertIn(str(path)+':/functional-plan/plan.json:ro',args)
