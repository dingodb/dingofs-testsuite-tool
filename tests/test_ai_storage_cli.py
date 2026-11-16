import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

import test_fio_cli

ROOT = Path(__file__).resolve().parents[1]


class AIStorageCli(unittest.TestCase):
    def test_wrapper_forwards_total_count_and_preview_for_every_tool(self):
        helper = test_fio_cli.FioCliTest()
        self.addCleanup(helper.doCleanups)
        for tool, scene in [('fio','ai-storage-t03-read'),('elbencho','ai-storage-t03-write'),('mdtest','ai-storage-t03')]:
            result, argv = helper._run_wrapper(f'-t {tool} -s {scene} --ai-storage-file-count 100000 --ai-storage-jobs 8 --ai-storage-dry-run')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('--ai-storage-dry-run',argv)
            self.assertEqual(argv[argv.index('--ai-storage-file-count')+1],'100000')

    def test_entrypoint_dispatches_preview_to_real_planner(self):
        for tool, scene in [('fio','ai-storage-t03-read'),('elbencho','ai-storage-t03-write'),('mdtest','ai-storage-t03')]:
            with tempfile.TemporaryDirectory() as temp:
                env = dict(os.environ, DTT_AI_STORAGE_RUNNER=str(ROOT/'scripts/ai_storage_scenarios.py'))
                result = subprocess.run(['bash',str(ROOT/'entrypoint.sh'),'-t',tool,'-s',scene,
                    '-m',temp,'-o',temp,'--ai-storage-dry-run','--ai-storage-file-count','100000'],
                    capture_output=True,text=True,env=env)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('"file_count": 100000',result.stdout)
                self.assertEqual(list(Path(temp).iterdir()),[])

    def test_ai_storage_options_rejected_for_ordinary_scenarios(self):
        helper=test_fio_cli.FioCliTest(); self.addCleanup(helper.doCleanups)
        result, argv=helper._run_wrapper('--ai-storage-dry-run')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(argv,[])


if __name__ == '__main__':
    unittest.main()
