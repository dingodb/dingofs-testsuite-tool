import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SmokeXfstestTest(unittest.TestCase):
    def _run_smoke_wrapper_with_setup(
        self,
        *,
        setup_rc=0,
        configure_output=True,
        mount_ready=True,
        smoke_args="",
    ):
        wrapper = ROOT / "dingofs-testsuite-tool"
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        temp = Path(temp_dir.name)
        config = temp / "config"
        old_mount = temp / "old-mount"
        new_mount = temp / "tool-mount"
        output = temp / "output"
        config.mkdir()
        old_mount.mkdir()
        new_mount.mkdir()
        output.mkdir()

        events_file = temp / "events"
        args_file = temp / "runtime-args"
        runtime = temp / "fake-runtime"
        runtime.write_text(
            "#!/bin/bash\n"
            f"echo runtime >> {events_file}\n"
            f"printf '%s\\n' \"$@\" > {args_file}\n",
            encoding="utf-8",
        )
        runtime.chmod(0o755)
        (config / "image").write_text("test-image\n", encoding="utf-8")
        (config / "testdir").write_text(f"{old_mount}\n", encoding="utf-8")
        if configure_output:
            (config / "output").write_text(f"{output}\n", encoding="utf-8")
        (config / "runtime").write_text(f"{runtime}\n", encoding="utf-8")

        command = textwrap.dedent(
            f"""
            export DINGOFS_TESTSUITE_CONFIG_DIR={config}
            source {wrapper}
            _run_setup_env() {{
                echo "setup:$1" >> {events_file}
                if [[ {setup_rc} -ne 0 ]]; then
                    return {setup_rc}
                fi
                echo "export DINGOFS_TEMP_MOUNTDIR={new_mount}"
            }}
            mountpoint() {{ return {0 if mount_ready else 1}; }}
            _is_rootless() {{ return 0; }}
            cmd_smoke {smoke_args}
            """
        )
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )
        events = (
            events_file.read_text(encoding="utf-8").splitlines()
            if events_file.exists()
            else []
        )
        args = (
            args_file.read_text(encoding="utf-8").splitlines()
            if args_file.exists()
            else []
        )
        return result, events, args, args_file, new_mount

    def run_smoke(self, *, template="mds://127.0.0.1:6900/{fsname}", xfstest_rc=0,
                  exclude=""):
        source = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        library = source.rsplit('\nmain "$@"', 1)[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            integration = temp / "integration"
            integration.mkdir()
            harness = textwrap.dedent(
                f"""
                INTEGRATION_DIR={integration}
                OUTPUT={temp / 'output'}
                RUN_TIMESTAMP=test-run
                INT_ENV=env_test
                MOUNT={temp / 'mount'}
                SCENARIO=original
                NP=16
                WECHAT_ENABLED=no
                EMAIL_ENABLED=no
                SMOKE_EXCLUDE={exclude!r}
                DTT_SMOKE_ENV_READY=1
                DINGOFS_META_URL_TEMPLATE={template!r}
                XFSTEST_FAKE_RC={xfstest_rc}

                python3() {{
                    echo "TEST SUITE SUMMARY"
                    echo "Total Cases: 1"
                    echo "Passed: 1"
                    echo "Failed: 0"
                    return 0
                }}
                pjdtest_run() {{ return 0; }}
                parse_pjdtest_tap() {{
                    SMOKE_PJD_PASS=1; SMOKE_PJD_FAIL=0; SMOKE_PJD_SKIP=0; SMOKE_PJD_TOTAL=1
                }}
                ltp_run() {{ return 0; }}
                parse_ltp_output() {{
                    SMOKE_LTP_PASS=1; SMOKE_LTP_FAIL=0; SMOKE_LTP_SKIP=0
                    SMOKE_LTP_TOTAL=1; SMOKE_LTP_TIMEOUT=0
                }}
                xfstest_run() {{
                    echo "xfstest_call scenario=$SCENARIO output=$OUTPUT"
                    return "$XFSTEST_FAKE_RC"
                }}
                send_smoke_notification() {{ :; }}

                set +e
                smoke_run
                smoke_rc=$?
                set -e
                echo "smoke_rc=$smoke_rc"
                exit 0
                """
            )
            script = temp / "run-smoke.sh"
            script.write_text(library + "\n" + harness, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(script)], text=True, capture_output=True, check=False
            )
            summary_path = temp / "output" / "smoke_test-run" / "smoke_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            return (
                summary["aggregate"]["exit_code"],
                result.stdout + result.stderr,
                summary,
            )

    def test_quick_failure_is_reported_and_later_tests_continue(self):
        returncode, output, summary = self.run_smoke(xfstest_rc=23)

        self.assertIn("xfstest_call scenario=quick", output)
        self.assertIn("[14/14] Running integration test: xattr", output)
        self.assertEqual(returncode, 1)
        self.assertEqual(summary["tools"]["xfstest"]["status"], "FAIL")
        self.assertEqual(summary["tools"]["xfstest"]["exit_code"], 23)

    def test_missing_mds_template_fails_only_xfstest_item(self):
        returncode, output, summary = self.run_smoke(template="")

        self.assertNotIn("xfstest_call", output)
        self.assertIn("xfstest_mds_template", output)
        self.assertIn("[14/14] Running integration test: xattr", output)
        self.assertEqual(returncode, 1)
        self.assertEqual(summary["tools"]["xfstest"]["status"], "FAIL")

    def test_excluded_xfstest_does_not_require_template(self):
        returncode, output, summary = self.run_smoke(template="", exclude="xfstest")

        self.assertNotIn("xfstest_call", output)
        self.assertEqual(returncode, 0)
        self.assertEqual(summary["tools"]["xfstest"]["status"], "SKIP")

    def test_dtt_smoke_passes_configured_mds_template_to_container(self):
        wrapper = ROOT / "dingofs-testsuite-tool"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            config.mkdir()
            mount = temp / "mount"
            output = temp / "output"
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
            (config / "int_env").write_text("env_test\n", encoding="utf-8")
            template = "mds://10.0.0.1:6900/{fsname}"
            (config / "xfstest_mds_template").write_text(
                template + "\n", encoding="utf-8"
            )

            command = textwrap.dedent(
                f"""
                export DINGOFS_TESTSUITE_CONFIG_DIR={config}
                source {wrapper}
                cmd_setup_env() {{ :; }}
                mountpoint() {{ return 0; }}
                _is_rootless() {{ return 1; }}
                cmd_smoke
                """
            )
            subprocess.run(["bash", "-c", command], check=True, capture_output=True)
            args = args_file.read_text(encoding="utf-8").splitlines()
            owner = f"{os.stat(output).st_uid}:{os.stat(output).st_gid}"
            excluded_command = textwrap.dedent(
                f"""
                export DINGOFS_TESTSUITE_CONFIG_DIR={config}
                source {wrapper}
                cmd_setup_env() {{ :; }}
                mountpoint() {{ return 0; }}
                _is_rootless() {{ return 1; }}
                cmd_smoke --exclude xfstest
                """
            )
            subprocess.run(
                ["bash", "-c", excluded_command], check=True, capture_output=True
            )
            excluded_args = args_file.read_text(encoding="utf-8").splitlines()

            rootless_command = textwrap.dedent(
                f"""
                export DINGOFS_TESTSUITE_CONFIG_DIR={config}
                source {wrapper}
                cmd_setup_env() {{ :; }}
                mountpoint() {{ return 0; }}
                _is_rootless() {{ return 0; }}
                cmd_smoke
                """
            )
            subprocess.run(
                ["bash", "-c", rootless_command], check=True, capture_output=True
            )
            rootless_args = args_file.read_text(encoding="utf-8").splitlines()

        self.assertIn("DINGOFS_META_URL_TEMPLATE=" + template, args)
        self.assertIn("DTT_SMOKE_RUN_AS=" + owner, args)
        self.assertIn("DTT_SMOKE_OUTPUT_OWNER=" + owner, args)
        self.assertNotIn("--user", args)
        self.assertIn("--user", excluded_args)
        self.assertNotIn("DINGOFS_META_URL_TEMPLATE=" + template, excluded_args)
        self.assertNotIn("--user", rootless_args)
        self.assertNotIn("DTT_SMOKE_RUN_AS=" + owner, rootless_args)
        self.assertNotIn("DTT_SMOKE_OUTPUT_OWNER=" + owner, rootless_args)
        self.assertIn("DINGOFS_META_URL_TEMPLATE=" + template, rootless_args)

    def test_dtt_smoke_sets_up_tool_environment_before_container(self):
        result, events, args, _, new_mount = self._run_smoke_wrapper_with_setup()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(events, ["setup:env_126_tool", "runtime"])
        self.assertIn(f"{new_mount}:/data", args)
        self.assertIn("DTT_SMOKE_ENV_READY=1", args)

    def test_dtt_smoke_aborts_when_tool_environment_setup_fails(self):
        result, events, args, args_file, _ = self._run_smoke_wrapper_with_setup(
            setup_rc=17
        )

        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertEqual(events, ["setup:env_126_tool"])
        self.assertEqual(args, [])
        self.assertFalse(args_file.exists())

    def test_dtt_smoke_validates_output_before_environment_setup(self):
        result, events, args, args_file, _ = self._run_smoke_wrapper_with_setup(
            configure_output=False
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Output directory not set", result.stdout + result.stderr)
        self.assertEqual(events, [])
        self.assertEqual(args, [])
        self.assertFalse(args_file.exists())

    def test_dtt_smoke_aborts_when_setup_path_is_not_mounted(self):
        result, events, args, args_file, _ = self._run_smoke_wrapper_with_setup(
            mount_ready=False
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("not an active mount", result.stdout + result.stderr)
        self.assertEqual(events, ["setup:env_126_tool"])
        self.assertEqual(args, [])
        self.assertFalse(args_file.exists())

    def test_dtt_smoke_skips_tool_setup_when_all_tool_phases_are_excluded(self):
        result, events, args, _, new_mount = self._run_smoke_wrapper_with_setup(
            smoke_args="--exclude pjdtest,ltp,xfstest"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(events, ["runtime"])
        self.assertNotIn(f"{new_mount}:/data", args)
        self.assertIn("DTT_SMOKE_ENV_READY=1", args)

    def test_xfstest_runner_returns_check_exit_code_not_tee_exit_code(self):
        source = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        library = source.rsplit('\nmain "$@"', 1)[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            xfstests = temp / "xfstests"
            xfstests.mkdir()
            (xfstests / "local.config").write_text(
                "export TEST_DIR=/test\nexport SCRATCH_MNT=/scratch\nexport FSTYP=dingofs\n",
                encoding="utf-8",
            )
            check = xfstests / "check"
            check.write_text("#!/bin/bash\nexit 23\n", encoding="utf-8")
            check.chmod(0o755)
            harness = textwrap.dedent(
                f"""
                XFSTESTS_DIR={xfstests}
                XFSTESTS_ROOT={temp / 'root'}
                OUTPUT={temp / 'output'}
                RUN_TIMESTAMP=test-run
                SCENARIO=quick
                DINGOFS_META_URL_TEMPLATE=
                log_result() {{ :; }}
                set +e
                xfstest_run
                rc=$?
                set -e
                echo "xfstest_rc=$rc"
                """
            )
            script = temp / "run-xfstest.sh"
            script.write_text(library + "\n" + harness, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(script)], text=True, capture_output=True, check=True
            )

        self.assertIn("xfstest_rc=23", result.stdout + result.stderr)

    def test_xfstest_runner_stops_when_mds_setup_fails(self):
        source = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        library = source.rsplit('\nmain "$@"', 1)[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            xfstests = temp / "xfstests"
            xfstests.mkdir()
            setup = xfstests / "setup.sh"
            setup.write_text("#!/bin/bash\nexit 17\n", encoding="utf-8")
            setup.chmod(0o755)
            check_marker = temp / "check-ran"
            check = xfstests / "check"
            check.write_text(
                f"#!/bin/bash\ntouch {check_marker}\nexit 0\n", encoding="utf-8"
            )
            check.chmod(0o755)
            harness = textwrap.dedent(
                f"""
                XFSTESTS_DIR={xfstests}
                XFSTESTS_ROOT={temp / 'root'}
                OUTPUT={temp / 'output'}
                RUN_TIMESTAMP=test-run
                SCENARIO=quick
                DINGOFS_META_URL_TEMPLATE='mds://127.0.0.1:6900/{{fsname}}'
                log_result() {{ :; }}
                set +e
                xfstest_run
                rc=$?
                set -e
                echo "xfstest_rc=$rc"
                """
            )
            script = temp / "run-xfstest-setup-failure.sh"
            script.write_text(library + "\n" + harness, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(script)], text=True, capture_output=True, check=True
            )

        self.assertIn("xfstest_rc=17", result.stdout + result.stderr)
        self.assertFalse(check_marker.exists())

    def test_privilege_helper_has_fixed_inputs_and_rejects_arguments(self):
        source = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        library = source.rsplit('\nmain "$@"', 1)[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            helper = temp / "dtt-smoke-xfstest"
            sudoers = temp / "dtt-smoke-sudoers"
            fake_entrypoint = temp / "entrypoint"
            invocation = temp / "invocation"
            fake_entrypoint.write_text(
                "#!/bin/bash\n"
                f"printf 'template=%s\\nowner=%s\\nargs=%s\\n' "
                '"$DINGOFS_META_URL_TEMPLATE" "$DTT_SMOKE_OUTPUT_OWNER" "$*" '
                f"> {invocation}\n",
                encoding="utf-8",
            )
            fake_entrypoint.chmod(0o755)
            harness = textwrap.dedent(
                f"""
                install_smoke_xfstest_helper \\
                    {helper} {sudoers} {fake_entrypoint} \\
                    'mds://127.0.0.1:6900/{{fsname}}' 1002:1002 \\
                    /output/smoke_fixed/xfstest fixed /data
                """
            )
            subprocess.run(
                ["bash", "-c", library + "\n" + harness],
                check=True,
                capture_output=True,
            )

            success = subprocess.run([str(helper)], check=False)
            rejected = subprocess.run([str(helper), "unexpected"], check=False)
            sudoers_text = sudoers.read_text(encoding="utf-8")
            invocation_text = invocation.read_text(encoding="utf-8")

        self.assertEqual(success.returncode, 0)
        self.assertEqual(rejected.returncode, 64)
        self.assertIn(f'{helper} ""', sudoers_text)
        self.assertNotIn("SETENV", sudoers_text)
        self.assertIn("template=mds://127.0.0.1:6900/{fsname}", invocation_text)
        self.assertIn("owner=1002:1002", invocation_text)
        self.assertIn(
            "args=-t xfstest -s quick -m /data -o /output/smoke_fixed/xfstest",
            invocation_text,
        )

    def test_xfstest_runner_refuses_stale_non_mds_configuration(self):
        source = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        library = source.rsplit('\nmain "$@"', 1)[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            xfstests = temp / "xfstests"
            xfstests.mkdir()
            config = temp / "dingofs-xfstests.conf"
            setup = xfstests / "setup.sh"
            setup.write_text(
                "#!/bin/bash\n"
                f"echo 'export FSTYP=ext4' > {xfstests / 'local.config'}\n"
                f"echo 'export FUSE_SUBTYP=.not-dingofs' >> {xfstests / 'local.config'}\n"
                f"echo 'META_URL_TEMPLATE=mds://127.0.0.1:6900/\\{{fsname\\}}' > {config}\n",
                encoding="utf-8",
            )
            setup.chmod(0o755)
            check_marker = temp / "check-ran"
            check = xfstests / "check"
            check.write_text(
                f"#!/bin/bash\ntouch {check_marker}\nexit 0\n", encoding="utf-8"
            )
            check.chmod(0o755)
            harness = textwrap.dedent(
                f"""
                XFSTESTS_DIR={xfstests}
                XFSTESTS_ROOT={temp / 'root'}
                DINGOFS_XFSTESTS_CONF={config}
                OUTPUT={temp / 'output'}
                RUN_TIMESTAMP=test-run
                SCENARIO=quick
                DINGOFS_META_URL_TEMPLATE='mds://127.0.0.1:6900/{{fsname}}'
                log_result() {{ :; }}
                set +e
                xfstest_run
                rc=$?
                set -e
                echo "xfstest_rc=$rc"
                """
            )
            script = temp / "run-xfstest-stale-config.sh"
            script.write_text(library + "\n" + harness, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(script)], text=True, capture_output=True, check=True
            )

        self.assertIn("refusing to run", result.stdout + result.stderr)
        self.assertIn("xfstest_rc=1", result.stdout + result.stderr)
        self.assertFalse(check_marker.exists())


if __name__ == "__main__":
    unittest.main()
