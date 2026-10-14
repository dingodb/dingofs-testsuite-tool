import shlex
import tempfile
import unittest
from pathlib import Path
import test_fio_cli


class MdtestCustomCLI(unittest.TestCase):
    def test_custom_directory_is_mounted_without_global_config_change(self):
        helper=test_fio_cli.FioCliTest();self.addCleanup(helper.doCleanups)
        with tempfile.TemporaryDirectory(prefix='mdtest custom ') as directory:
            result,args=helper._run_wrapper('-t mdtest -s custom -n 2 --custom-dir '+shlex.quote(directory))
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn(directory+':/custom',args)
            self.assertIn('custom',args)
            self.assertNotIn('--custom-dir',args)  # wrapper consumes the host-only option

    def test_invalid_directory_rejected_before_container_launch(self):
        helper=test_fio_cli.FioCliTest();self.addCleanup(helper.doCleanups)
        result,args=helper._run_wrapper('-t mdtest -s custom --custom-dir /path/that/does/not/exist')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(args,[])
