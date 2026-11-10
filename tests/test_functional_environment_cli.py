import shlex
import tempfile
import unittest
from pathlib import Path
import test_fio_cli

class FunctionalEnvironmentCLI(unittest.TestCase):
    def test_exact_file_is_mounted_read_only(self):
        helper=test_fio_cli.FioCliTest();self.addCleanup(helper.doCleanups)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'env_platform_abc.yaml'
            path.write_text('env_platform_abc: {}\n')
            result,args=helper._run_wrapper('-t int -s basic_file_operation --env env_platform_abc --int-env-file '+shlex.quote(str(path)))
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn(str(path)+':/dingofs-integration-test/conf/env/env_platform_abc.yaml:ro',args)
            self.assertNotIn('--int-env-file',args)
    def test_missing_file_rejected(self):
        helper=test_fio_cli.FioCliTest();self.addCleanup(helper.doCleanups)
        result,args=helper._run_wrapper('-t int -s quota --env env_platform_abc --int-env-file /missing/env.yaml')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(args,[])

    def test_path_traversal_key_and_other_tool_are_rejected(self):
        helper=test_fio_cli.FioCliTest();self.addCleanup(helper.doCleanups)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'env_platform_abc.yaml';path.write_text('env_platform_abc: {}\n')
            result,args=helper._run_wrapper('-t int -s quota --env env_platform_../../bad --int-env-file '+shlex.quote(str(path)))
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(args,[])
            result,args=helper._run_wrapper('-t fio -s seq_write --env env_platform_abc --int-env-file '+shlex.quote(str(path)))
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(args,[])

    def test_exact_plan_rejects_missing_managed_runtime(self):
        helper=test_fio_cli.FioCliTest();self.addCleanup(helper.doCleanups)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'plan.json';path.write_text('{}')
            result,args=helper._run_wrapper('-t int -s quota --case-plan '+shlex.quote(str(path)))
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(args,[])
