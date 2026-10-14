import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from performance_plan import build_plan, build_step, parser


class PerformancePlanTest(unittest.TestCase):
    def plan(self, *args):
        return build_plan(parser().parse_args(['--tool', 'fio', *args]))

    def test_total_is_global_and_uneven_file_distribution_is_exact(self):
        plan = self.plan('--concurrency', '3', '--file-size', '64K', '--file-count', '5')
        self.assertEqual(plan['total_size_bytes'], 327680)
        step = build_step(plan, 'write', 1)
        config = step['config']
        self.assertEqual(config.count('numjobs=1'), 3)
        self.assertEqual(config.count('nrfiles=2'), 2)
        self.assertEqual(config.count('nrfiles=1'), 1)
        self.assertIn('filename_format=worker-2.$filenum', config)
        self.assertIn('size=65536', config)

    def test_infers_missing_dimension_without_multiplying_by_workers(self):
        examples = [
            (['--file-size', '64K', '--total-size', '320K'], (65536, 5, 327680)),
            (['--file-count', '5', '--total-size', '320K'], (65536, 5, 327680)),
            (['--total-size', '1M'], (262144, 4, 1048576)),
        ]
        for args, expected in examples:
            with self.subTest(args=args):
                plan = self.plan(*args)
                self.assertEqual(tuple(plan[k] for k in ('file_size_bytes', 'file_count', 'total_size_bytes')), expected)

    def test_three_dimensions_must_agree(self):
        with self.assertRaisesRegex(ValueError, 'total-size'):
            self.plan('--file-size', '64K', '--file-count', '4', '--total-size', '1M')

    def test_does_not_round_data_sizes_or_drop_files(self):
        for args in [
            ['--file-size', '64K', '--total-size', '321K'],
            ['--file-count', '3', '--total-size', '1M'],
            ['--file-count', '2', '--concurrency', '3'],
            ['--file-size', '64K', '--block-size', '128K'],
            ['--file-size', '64K', '--block-size', '12K'],
            ['--direct', '1', '--block-size', '1K'],
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.plan(*args)

    def test_small_buffered_files_can_use_small_blocks(self):
        plan = self.plan('--direct', '0', '--file-size', '128', '--file-count', '4')
        self.assertEqual(plan['block_size_bytes'], 128)
        self.assertIn('direct=0', build_step(plan, 'write', 1)['config'])

    def test_read_and_mixed_prepare_are_not_measured(self):
        plan = self.plan('--rw', 'randrw', '--read-percent', '70', '--rounds', '3')
        prepare = build_step(plan, 'prepare', 0)
        measure = build_step(plan, 'randrw', 1)
        self.assertFalse(prepare['measured'])
        self.assertTrue(measure['measured'])
        self.assertIn('rw=write', prepare['config'])
        self.assertNotIn('rwmixread=', prepare['config'])
        self.assertIn('rw=randrw', measure['config'])
        self.assertIn('rwmixread=70', measure['config'])

    def test_rounds_reuse_dataset_but_keep_distinct_result_artifacts(self):
        plan = self.plan('--rounds', '3')
        first, second = build_step(plan, 'write', 1), build_step(plan, 'write', 2)
        self.assertNotEqual(first['result_path'], second['result_path'])
        self.assertIn('directory=' + plan['data_dir'], first['config'])
        self.assertIn('directory=' + plan['data_dir'], second['config'])
        self.assertEqual(plan['peak_dataset_bytes'], plan['total_size_bytes'])

    def test_planning_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan('--mount', directory, '--output', directory, '--dry-run')
            json.dumps(plan)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_elbencho_global_file_count_and_buffered_mode(self):
        plan = self.plan('--tool', 'elbencho', '--concurrency', '3', '--file-count', '5', '--file-size', '64K', '--direct', '0')
        argv = build_step(plan, 'write', 1)['argv']
        self.assertNotIn('--direct', argv)
        self.assertNotIn('-N', argv)
        self.assertEqual(argv[-1], plan['data_dir'] + '/file[0-4]')
        self.assertEqual(argv[argv.index('-t') + 1], '3')

    def test_elbencho_random_volume_is_not_silently_rounded(self):
        with self.assertRaisesRegex(ValueError, 'block.*concurrency'):
            self.plan('--tool', 'elbencho', '--rw', 'randread', '--concurrency', '3', '--file-count', '5', '--file-size', '64K', '--block-size', '4K')

    def test_elbencho_mixed_uses_explicit_total_and_read_percentage(self):
        plan = self.plan('--tool', 'elbencho', '--rw', 'randrw', '--read-percent', '70', '--file-size', '64K', '--block-size', '4K')
        argv = build_step(plan, 'randrw', 1)['argv']
        for token in ('-w', '--rand', '--direct'):
            self.assertIn(token, argv)
        self.assertEqual(argv[argv.index('--rwmixpct') + 1], '70')
        self.assertEqual(argv[argv.index('--randamount') + 1], '262144')

    def test_dangerous_path_characters_rejected_before_io(self):
        for path in ('/tmp/a\n[bad]', '/tmp/a:b', '/tmp/[0-100]'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.plan('--mount', path)

    def test_read_percentage_is_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, 'read-percent'):
            self.plan('--rw', 'read', '--read-percent', '70')


if __name__ == '__main__':
    unittest.main()
