from pathlib import Path
import shlex
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FioCliTest(unittest.TestCase):
    def _run_wrapper(self, fio_args):
        wrapper = ROOT / "dingofs-testsuite-tool"
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        temp = Path(temp_dir.name)
        config = temp / "config"
        mount = temp / "mount"
        output = temp / "output"
        config.mkdir()
        mount.mkdir()
        output.mkdir()

        args_file = temp / "runtime-args"
        runtime = temp / "fake-runtime"
        runtime.write_text(
            f"#!/bin/bash\nprintf '%s\\n' \"$@\" > {args_file}\n",
            encoding="utf-8",
        )
        runtime.chmod(0o755)
        (config / "image").write_text("test-image\n", encoding="utf-8")
        (config / "testdir").write_text(f"{mount}\n", encoding="utf-8")
        (config / "output").write_text(f"{output}\n", encoding="utf-8")
        (config / "runtime").write_text(f"{runtime}\n", encoding="utf-8")

        command = textwrap.dedent(
            f"""
            export DINGOFS_TESTSUITE_CONFIG_DIR={shlex.quote(str(config))}
            source {shlex.quote(str(wrapper))}
            _is_rootless() {{ return 0; }}
            run_testsuite -t fio -s seq_write {fio_args}
            """
        )
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )
        args = (
            args_file.read_text(encoding="utf-8").splitlines()
            if args_file.exists()
            else []
        )
        return result, args

    def _run_fio_entrypoint(self, fio_options):
        source = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        library = source.rsplit('\nmain "$@"', 1)[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            scenarios = temp / "scenarios"
            output = temp / "output"
            mount = temp / "mount"
            scenarios.mkdir()
            output.mkdir()
            mount.mkdir()

            configs = []
            for direct in (0, 1):
                for block_size in ("128k", "1m", "4m"):
                    for numjobs in (1, 8, 16, 32):
                        path = scenarios / (
                            f"seq_write_{direct}d_{block_size}_{numjobs}j.fio"
                        )
                        path.write_text(
                            "[global]\n"
                            f"bs={block_size}\n"
                            f"direct={direct}\n"
                            f"numjobs={numjobs}\n"
                            "size=8G\n"
                            "[job1]\n",
                            encoding="utf-8",
                        )
                        configs.append(path)

            fio_args = temp / "fio-args"
            fake_fio = temp / "fio"
            fake_fio.write_text(
                f"#!/bin/bash\nprintf '%s ' \"$@\" >> {fio_args}\nprintf '\\n' >> {fio_args}\nprintf '{{}}\\n'\n",
                encoding="utf-8",
            )
            fake_fio.chmod(0o755)
            scenario_lines = "\n".join(str(path) for path in configs)
            harness = textwrap.dedent(
                f"""
                get_scenario_paths() {{ printf '%s\\n' {shlex.quote(scenario_lines)}; }}
                python3() {{ :; }}
                log_result() {{ :; }}
                send_wechat_notification() {{ :; }}
                send_email_notification() {{ :; }}
                FIO_BIN={shlex.quote(str(fake_fio))}
                OUTPUT={shlex.quote(str(output))}
                MOUNT={shlex.quote(str(mount))}
                RUN_TIMESTAMP=test-run
                WECHAT_ENABLED=no
                EMAIL_ENABLED=no
                parse_args -t fio -s seq_write {fio_options}
                fio_run
                """
            )
            script = temp / "run-fio.sh"
            script.write_text(library + "\n" + harness, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(script)], text=True, capture_output=True, check=False
            )
            calls = (
                fio_args.read_text(encoding="utf-8").splitlines()
                if fio_args.exists()
                else []
            )
            effective_configs = [
                Path(shlex.split(call)[0]).read_text(encoding="utf-8")
                for call in calls
            ]
        return result, calls, effective_configs

    def test_wrapper_passes_fio_overrides_to_container_entrypoint(self):
        result, args = self._run_wrapper(
            "--numjobs 64 --direct 1 --file-size 10G --block-size 4K"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        numjobs_index = args.index("--numjobs")
        self.assertEqual(
            args[numjobs_index:],
            [
                "--numjobs", "64",
                "--direct", "1",
                "--file-size", "10G",
                "--block-size", "4K",
            ],
        )

    def test_wrapper_rejects_non_positive_numjobs_before_starting_container(self):
        result, args = self._run_wrapper("--numjobs 0")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(args, [])
        self.assertIn("positive integer", result.stdout + result.stderr)

    def test_wrapper_rejects_direct_other_than_zero_or_one(self):
        result, args = self._run_wrapper("--direct 2")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(args, [])
        self.assertIn("0 or 1", result.stdout + result.stderr)

    def test_numjobs_override_keeps_direct_and_block_size_matrix_without_duplicates(self):
        result, calls, _ = self._run_fio_entrypoint("--numjobs 64")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 6)
        for call in calls:
            self.assertIn("--numjobs=64", shlex.split(call))
            self.assertTrue(Path(shlex.split(call)[0]).stem.endswith("_64j"))
        selected = {
            "_".join(Path(shlex.split(call)[0]).stem.split("_")[2:4])
            for call in calls
        }
        self.assertEqual(
            selected,
            {"0d_128k", "0d_1m", "0d_4m", "1d_128k", "1d_1m", "1d_4m"},
        )

    def test_file_size_only_keeps_all_prebuilt_matrix_combinations(self):
        result, calls, _ = self._run_fio_entrypoint("--file-size 10G")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 24)
        for call in calls:
            self.assertIn("--size=10G", shlex.split(call))

    def test_all_overrides_collapse_prebuilt_matrix_to_one_combination(self):
        result, calls, effective_configs = self._run_fio_entrypoint(
            "--numjobs 64 --direct 1 --file-size 10G --block-size 4K"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 1)
        tokens = shlex.split(calls[0])
        self.assertEqual(Path(tokens[0]).stem, "seq_write_1d_4k_64j")
        self.assertIn("Running scenario 1/1: seq_write_1d_4k_64j", result.stdout)
        self.assertIn("--numjobs=64", tokens)
        self.assertIn("--direct=1", tokens)
        self.assertIn("--size=10G", tokens)
        self.assertIn("--bs=4K", tokens)
        self.assertNotRegex(
            effective_configs[0],
            r"(?m)^\s*(?:numjobs|direct|size|bs)\s*=",
        )


if __name__ == "__main__":
    unittest.main()
