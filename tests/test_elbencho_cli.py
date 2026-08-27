from pathlib import Path
import shlex
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ElbenchoCliTest(unittest.TestCase):
    def _run_wrapper(self, elbencho_args, scenario="seq_write"):
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
            run_testsuite -t elbencho -s {shlex.quote(scenario)} {elbencho_args}
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

    def _run_entrypoint(self, elbencho_args, scenario="all"):
        source = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        library = source.rsplit('\nmain "$@"', 1)[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            output = temp / "output"
            mount = temp / "mount"
            bin_dir = temp / "bin"
            output.mkdir()
            mount.mkdir()
            bin_dir.mkdir()

            args_file = temp / "elbencho-args"
            report_args_file = temp / "report-args"
            fake_report_generator = temp / "generate-report.py"
            fake_report_generator.write_text(
                "import pathlib, sys\n"
                f"pathlib.Path({str(report_args_file)!r}).write_text('\\n'.join(sys.argv[1:]), encoding='utf-8')\n",
                encoding="utf-8",
            )
            fake_elbencho = bin_dir / "elbencho"
            fake_elbencho.write_text(
                f"#!/bin/bash\nprintf '%s ' \"$@\" >> {args_file}\nprintf '\\n' >> {args_file}\n",
                encoding="utf-8",
            )
            fake_elbencho.chmod(0o755)
            harness = textwrap.dedent(
                f"""
                log_result() {{ :; }}
                send_wechat_notification() {{ :; }}
                send_email_notification() {{ :; }}
                PATH={shlex.quote(str(bin_dir))}:$PATH
                OUTPUT={shlex.quote(str(output))}
                MOUNT={shlex.quote(str(mount))}
                RUN_TIMESTAMP=test-run
                WECHAT_ENABLED=no
                EMAIL_ENABLED=no
                REPORT_GENERATOR={shlex.quote(str(fake_report_generator))}
                parse_args -t elbencho -s {shlex.quote(scenario)} {elbencho_args}
                validate_params
                elbencho_run
                """
            )
            script = temp / "run-elbencho.sh"
            script.write_text(library + "\n" + harness, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(script)], text=True, capture_output=True, check=False
            )
            calls = (
                args_file.read_text(encoding="utf-8").splitlines()
                if args_file.exists()
                else []
            )
            self.last_report_args = (
                report_args_file.read_text(encoding="utf-8").splitlines()
                if report_args_file.exists()
                else []
            )
            elbencho_output = output / "elbencho_test-run"
            self.last_elbencho_artifacts = {
                path.name: path.read_text(encoding="utf-8")
                for path in elbencho_output.glob("*")
                if path.is_file()
            }
        return result, [shlex.split(call) for call in calls]

    def _run_small_entrypoint(self, elbencho_args):
        source = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        library = source.rsplit('\nmain "$@"', 1)[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            output = temp / "output"
            mount = temp / "mount"
            args_file = temp / "small-script-args"
            output.mkdir()
            mount.mkdir()

            harness = textwrap.dedent(
                f"""
                bash() {{ printf '%s\n' "$@" > {shlex.quote(str(args_file))}; }}
                log_result() {{ :; }}
                elbencho_notify() {{ :; }}
                OUTPUT={shlex.quote(str(output))}
                MOUNT={shlex.quote(str(mount))}
                RUN_TIMESTAMP=test-run
                parse_args -t elbencho -s small {elbencho_args}
                validate_params
                elbencho_run
                """
            )
            script = temp / "run-small-entrypoint.sh"
            script.write_text(library + "\n" + harness, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(script)], text=True, capture_output=True, check=False
            )
            args = (
                args_file.read_text(encoding="utf-8").splitlines()
                if args_file.exists()
                else []
            )
        return result, args

    def test_wrapper_passes_elbencho_overrides_to_container_entrypoint(self):
        result, args = self._run_wrapper(
            "--file-size 10G --file-count 100 --block-size 4M "
            "--dir-count 2 --threads 16 --operation write"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        file_size_index = args.index("--file-size")
        self.assertEqual(
            args[file_size_index:],
            [
                "--file-size", "10G",
                "--file-count", "100",
                "--block-size", "4M",
                "--dir-count", "2",
                "--threads", "16",
                "--operation", "write",
            ],
        )

    def test_wrapper_rejects_invalid_counts_before_starting_container(self):
        for option in ("--file-count", "--dir-count", "--threads"):
            with self.subTest(option=option):
                result, args = self._run_wrapper(f"{option} 0")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(args, [])
                self.assertIn("positive integer", result.stdout + result.stderr)

    def test_wrapper_rejects_invalid_operation(self):
        result, args = self._run_wrapper("--operation delete")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(args, [])
        self.assertIn("read or write", result.stdout + result.stderr)

    def test_wrapper_rejects_conflicting_scenario_and_operation_before_container(self):
        result, args = self._run_wrapper(
            "--operation write", scenario="seq_read"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(args, [])
        self.assertIn("conflicts", result.stdout + result.stderr)

    def test_wrapper_reports_missing_elbencho_option_values(self):
        for option in (
            "--file-size",
            "--file-count",
            "--block-size",
            "--dir-count",
            "--threads",
            "--operation",
        ):
            with self.subTest(option=option):
                result, args = self._run_wrapper(option)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(args, [])
                self.assertIn("requires a value", result.stdout + result.stderr)

    def test_wrapper_rejects_invalid_sizes_before_starting_container(self):
        for option, value in (("--file-size", "bad"), ("--block-size", "0")):
            with self.subTest(option=option):
                result, args = self._run_wrapper(f"{option} {value}")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(args, [])
                self.assertIn("size", result.stdout + result.stderr)

    def test_wrapper_passes_small_overrides_to_container_entrypoint(self):
        result, args = self._run_wrapper(
            "--file-size 10m --file-count 100 --block-size 1m "
            "--threads 1,4,8,16",
            scenario="small",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        file_size_index = args.index("--file-size")
        self.assertEqual(
            args[file_size_index:],
            [
                "--file-size", "10m",
                "--file-count", "100",
                "--block-size", "1m",
                "--threads", "1,4,8,16",
            ],
        )

    def test_entrypoint_passes_small_overrides_to_script(self):
        result, args = self._run_small_entrypoint(
            "--file-size 10m --file-count 100 --block-size 1m "
            "--threads 1,4,8,16"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            args[3:],
            [
                "--file-size", "10m",
                "--file-count", "100",
                "--block-size", "1m",
                "--threads", "1,4,8,16",
            ],
        )

    def test_wrapper_rejects_small_only_overrides_for_other_script_scenarios(self):
        for scenario in ("full", "custom"):
            with self.subTest(scenario=scenario):
                result, args = self._run_wrapper("--threads 16", scenario=scenario)

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(args, [])
                self.assertIn("all/seq/rand/small", result.stdout + result.stderr)

    def test_wrapper_rejects_invalid_small_thread_lists(self):
        for threads in ("1,,4", "1,0,4", "1,a,4", ",1,4", "1,4,"):
            with self.subTest(threads=threads):
                result, args = self._run_wrapper(
                    f"--threads {shlex.quote(threads)}", scenario="small"
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(args, [])
                self.assertIn("comma-separated positive integers", result.stdout + result.stderr)

    def test_custom_parameters_map_to_elbencho_directory_mode(self):
        result, calls = self._run_entrypoint(
            "--file-size 10G --file-count 100 --block-size 4M "
            "--dir-count 2 --threads 16 --operation write",
            scenario="seq_write",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertIn("-w", call)
        self.assertIn("-d", call)
        for option, value in (
            ("-s", "10G"),
            ("-N", "100"),
            ("-b", "4M"),
            ("-n", "2"),
            ("-t", "16"),
        ):
            index = call.index(option)
            self.assertEqual(call[index + 1], value)
        self.assertTrue(call[-1].endswith("/mount"), call[-1])

    def test_no_overrides_preserve_legacy_large_file_defaults(self):
        result, calls = self._run_entrypoint("", scenario="seq_write")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertNotIn("-n", call)
        self.assertNotIn("-N", call)
        for option, value in (("-s", "1G"), ("-b", "4M"), ("-t", "8")):
            index = call.index(option)
            self.assertEqual(call[index + 1], value)
        self.assertTrue(call[-1].endswith("/mount/elbencho_test_file[1-4]"))

    def test_single_count_override_keeps_other_directory_defaults(self):
        for options, expected_dirs, expected_files in (
            ("--file-count 100", "1", "100"),
            ("--dir-count 2", "2", "4"),
        ):
            with self.subTest(options=options):
                result, calls = self._run_entrypoint(options, scenario="seq_write")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(len(calls), 1)
                call = calls[0]
                self.assertEqual(call[call.index("-n") + 1], expected_dirs)
                self.assertEqual(call[call.index("-N") + 1], expected_files)
                self.assertEqual(call[call.index("-t") + 1], "8")
                self.assertTrue(call[-1].endswith("/mount"))

    def test_operation_write_filters_all_scenario_to_write_workloads(self):
        result, calls = self._run_entrypoint("--operation write")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("-w" in call for call in calls))
        self.assertEqual(["--rand" in call for call in calls], [False, True])

    def test_entrypoint_records_commands_and_generates_one_run_report(self):
        result, calls = self._run_entrypoint("--operation write")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertIn("seq_write.command", self.last_elbencho_artifacts)
        self.assertIn("rand_write.command", self.last_elbencho_artifacts)
        self.assertEqual(self.last_elbencho_artifacts["seq_write.exitcode"], "0\n")
        self.assertEqual(self.last_elbencho_artifacts["rand_write.exitcode"], "0\n")
        self.assertIn("elbencho -w", self.last_elbencho_artifacts["seq_write.command"])
        self.assertIn("--rand", self.last_elbencho_artifacts["rand_write.command"])
        self.assertEqual(
            self.last_report_args,
            [
                "--tool", "elbencho",
                "--output-dir", next(
                    value
                    for index, value in enumerate(self.last_report_args)
                    if self.last_report_args[index - 1:index] == ["--output-dir"]
                ),
                "--scenario", "all",
                "--mount", next(
                    value
                    for index, value in enumerate(self.last_report_args)
                    if self.last_report_args[index - 1:index] == ["--mount"]
                ),
            ],
        )

    def test_custom_script_scenario_does_not_invoke_standard_report_generator(self):
        result, _ = self._run_entrypoint("", scenario="custom")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.last_report_args, [])

    def test_conflicting_scenario_and_operation_are_rejected(self):
        result, calls = self._run_entrypoint(
            "--operation write", scenario="seq_read"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        self.assertIn("conflicts", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
