import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SmokeSuiteTest(unittest.TestCase):
    def run_smoke(
        self,
        *,
        fail_quota_capacity=False,
        fail_hot_upgrade=False,
        suite_error_module="",
        empty_module="",
        skipped_module="",
        exclude="",
    ):
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
                INT_ENV=unused
                MOUNT=/data
                SCENARIO=original
                NP=16
                WECHAT_ENABLED=no
                EMAIL_ENABLED=no
                SMOKE_EXCLUDE={shlex.quote(exclude)}
                DTT_SMOKE_ENV_READY=1
                DINGOFS_META_URL_TEMPLATE='mds://127.0.0.1:6900/{{fsname}}'
                FAIL_QUOTA_CAPACITY={'yes' if fail_quota_capacity else 'no'}
                FAIL_HOT_UPGRADE={'yes' if fail_hot_upgrade else 'no'}
                SUITE_ERROR_MODULE={shlex.quote(suite_error_module)}
                EMPTY_MODULE={shlex.quote(empty_module)}
                SKIPPED_MODULE={shlex.quote(skipped_module)}

                python3() {{
                    if [[ "$*" == *tests/test_env_setup.py* ]]; then
                        echo "unexpected_internal_setup"
                        echo "DINGOFS_TEMP_MOUNTDIR=/tmp/wrong-mount"
                        return 0
                    fi

                    printf 'python3_call:'
                    printf ' %q' "$@"
                    echo
                    local failed=no
                    if [[ "$FAIL_QUOTA_CAPACITY" == yes ]] && \
                       [[ "$*" == *verify_fs_capacity.yaml* ]]; then
                        failed=yes
                    fi
                    if [[ "$FAIL_HOT_UPGRADE" == yes ]] && \
                       [[ "$*" == *"run_tests.py hot_upgrade "* ]]; then
                        failed=yes
                    fi
                    echo "TEST SUITE SUMMARY"
                    if [[ -n "$EMPTY_MODULE" ]] && \
                       [[ "$*" == *"run_tests.py $EMPTY_MODULE "* ]]; then
                        echo "Total Cases: 0"
                        echo "Passed: 0"
                        echo "Failed: 0"
                        echo "Suite Errors: 0"
                        echo "Skipped: 0"
                        return 0
                    fi
                    if [[ -n "$SKIPPED_MODULE" ]] && \
                       [[ "$*" == *"run_tests.py $SKIPPED_MODULE "* ]]; then
                        echo "Total Cases: 1"
                        echo "Passed: 0"
                        echo "Failed: 0"
                        echo "Suite Errors: 0"
                        echo "Skipped: 1"
                        return 0
                    fi
                    echo "Total Cases: 1"
                    if [[ -n "$SUITE_ERROR_MODULE" ]] && \
                       [[ "$*" == *"run_tests.py $SUITE_ERROR_MODULE "* ]]; then
                        echo "Passed: 0"
                        echo "Failed: 0"
                        echo "Suite Errors: 1"
                        echo "Skipped: 0"
                        return 0
                    fi
                    if [[ "$failed" == yes ]]; then
                        echo "Passed: 0"
                        echo "Failed: 1"
                        echo "Suite Errors: 0"
                        echo "Skipped: 0"
                        return 9
                    fi
                    echo "Passed: 1"
                    echo "Failed: 0"
                    echo "Suite Errors: 0"
                    echo "Skipped: 0"
                    return 0
                }}
                pjdtest_run() {{
                    echo "pjdtest_call scenario=$SCENARIO mount=$MOUNT"
                    return 0
                }}
                parse_pjdtest_tap() {{
                    SMOKE_PJD_PASS=1; SMOKE_PJD_FAIL=0; SMOKE_PJD_SKIP=0; SMOKE_PJD_TOTAL=1
                }}
                ltp_run() {{
                    echo "ltp_call scenario=$SCENARIO mount=$MOUNT"
                    return 0
                }}
                parse_ltp_output() {{
                    SMOKE_LTP_PASS=1; SMOKE_LTP_FAIL=0; SMOKE_LTP_SKIP=0
                    SMOKE_LTP_TOTAL=1; SMOKE_LTP_TIMEOUT=0
                }}
                xfstest_run() {{
                    echo "xfstest_call scenario=$SCENARIO mount=$MOUNT"
                    return 0
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
            output = result.stdout + result.stderr
            calls = [
                shlex.split(line.removeprefix("python3_call:").strip())
                for line in output.splitlines()
                if line.startswith("python3_call:")
            ]
            return result, output, summary, calls

    def test_runs_the_exact_tool_and_integration_smoke_matrix(self):
        result, output, summary, calls = self.run_smoke()

        expected_core_calls = [
            [
                "run_tests.py", "quota", "--env", "env_126_quota", "--case",
                "testcases/quota_test_cases/smoke/verify_fs_capacity.yaml",
                "--reruns", "2",
            ],
            [
                "run_tests.py", "quota", "--env", "env_126_quota", "--case",
                "testcases/quota_test_cases/smoke/verify_fs_quota.yaml",
                "--reruns", "2",
            ],
            [
                "run_tests.py", "basic_file_operation", "--env", "env_126_smoke",
                "--reruns", "2",
            ],
            [
                "run_tests.py", "client", "--env", "env_40_dingofs",
                "--run-level", "smoke", "--reruns", "2",
            ],
            [
                "run_tests.py", "cache_node", "--env", "env_40_dingofs",
                "--run-level", "smoke", "--reruns", "2",
            ],
            [
                "run_tests.py", "dirstat", "--env", "env_126_dirstat", "--case",
                "testcases/dirstat_test_cases/smoke", "--reruns", "2",
            ],
            [
                "run_tests.py", "hot_upgrade", "--env", "env_126_hotupgrade_multi",
                "--case", "testcases/hot_upgrade_test_cases/smoke", "--reruns", "2",
            ],
            [
                "run_tests.py", "mds_manage", "--env", "env_126_mds_manage", "--case",
                "testcases/mds_manage_test_cases/smoke", "--reruns", "2",
            ],
            [
                "run_tests.py", "mount_subdir", "--env", "env_126_mount_subdir",
                "--case",
                "testcases/mount_subdir_test_cases/smoke/verify_mount_subdir.yaml",
                "--reruns", "2",
            ],
            [
                "run_tests.py", "trash", "--env", "env_126_trash", "--case",
                "testcases/trash_test_cases/smoke", "--reruns", "2",
            ],
            [
                "run_tests.py", "warmup", "--env", "env_126_warmup", "--case",
                "testcases/warmup_test_cases/smoke", "--reruns", "2",
            ],
            [
                "run_tests.py", "xattr", "--env", "env_126_xattr", "--case",
                "testcases/xattr_test_cases/smoke", "--reruns", "2",
            ],
        ]
        expected_report_names = [
            "verify_fs_capacity", "verify_fs_quota", "basic_file_operation",
            "client", "cache_node", "dirstat", "hot_upgrade", "mds_manage",
            "mount_subdir", "trash", "warmup", "xattr",
        ]
        expected_tools = {
            "pjdtest", "ltp", "xfstest", "int_quota",
            "int_basic_file_operation", "int_client", "int_cache_node",
            "int_dirstat", "int_hot_upgrade", "int_mds_manage",
            "int_mount_subdir", "int_trash", "int_warmup", "int_xattr",
        }

        self.assertEqual(result.returncode, 0, output)
        self.assertIn("pjdtest_call scenario=all mount=/data", output)
        self.assertIn("ltp_call scenario=smoke mount=/data", output)
        self.assertIn("xfstest_call scenario=quick mount=/data", output)
        self.assertNotIn("unexpected_internal_setup", output)
        self.assertNotIn("mdtest_call", output)
        self.assertEqual(len(calls), len(expected_core_calls))
        for call, core, report_name in zip(
            calls, expected_core_calls, expected_report_names
        ):
            self.assertEqual(call[:len(core)], core)
            report_args = call[len(core):]
            self.assertEqual(report_args[0], "--report-path")
            report_path = report_args[1]
            self.assertTrue(
                report_path.endswith(
                    f"/smoke_test-run/int_{call[1]}/{report_name}"
                ),
                report_path,
            )
            self.assertEqual(
                report_args[2:4],
                ["--report-dir", f"{report_path}/allure-results"],
            )
            self.assertEqual(report_args[4:], ["--report-url", ""])
        self.assertEqual(set(summary["tools"]), expected_tools)
        self.assertEqual(summary["tools"]["int_quota"]["total"], 2)
        self.assertEqual(summary["aggregate"]["status"], "PASS")
        self.assertIn("smoke_rc=0", output)

    def test_failures_are_aggregated_without_stopping_later_modules(self):
        _, output, summary, calls = self.run_smoke(
            fail_quota_capacity=True,
            fail_hot_upgrade=True,
        )

        self.assertEqual(len(calls), 12)
        self.assertEqual(calls[-1][1], "xattr")
        self.assertEqual(summary["tools"]["int_quota"]["pass"], 1)
        self.assertEqual(summary["tools"]["int_quota"]["fail"], 1)
        self.assertEqual(summary["tools"]["int_quota"]["total"], 2)
        self.assertEqual(summary["tools"]["int_hot_upgrade"]["status"], "FAIL")
        self.assertEqual(summary["aggregate"]["status"], "FAIL")
        self.assertIn("smoke_rc=1", output)

    def test_suite_errors_fail_module_and_aggregate_while_continuing(self):
        _, output, summary, calls = self.run_smoke(suite_error_module="dirstat")

        self.assertEqual(len(calls), 12)
        self.assertEqual(calls[-1][1], "xattr")
        self.assertEqual(summary["tools"]["int_dirstat"]["pass"], 0)
        self.assertEqual(summary["tools"]["int_dirstat"]["fail"], 0)
        self.assertEqual(summary["tools"]["int_dirstat"]["error"], 1)
        self.assertEqual(summary["tools"]["int_dirstat"]["status"], "FAIL")
        self.assertEqual(summary["aggregate"]["status"], "FAIL")
        self.assertIn("smoke_rc=1", output)

    def test_quota_aggregates_suite_errors_from_both_cases(self):
        _, output, summary, calls = self.run_smoke(suite_error_module="quota")

        self.assertEqual(len(calls), 12)
        self.assertEqual(calls[-1][1], "xattr")
        self.assertEqual(summary["tools"]["int_quota"]["pass"], 0)
        self.assertEqual(summary["tools"]["int_quota"]["fail"], 0)
        self.assertEqual(summary["tools"]["int_quota"]["error"], 2)
        self.assertEqual(summary["tools"]["int_quota"]["total"], 2)
        self.assertEqual(summary["tools"]["int_quota"]["status"], "FAIL")
        self.assertEqual(summary["aggregate"]["status"], "FAIL")
        self.assertIn("smoke_rc=1", output)

    def test_exclude_int_marks_all_integration_modules_skipped(self):
        _, output, summary, calls = self.run_smoke(exclude="int")

        self.assertEqual(calls, [])
        for name, result in summary["tools"].items():
            if name.startswith("int_"):
                self.assertEqual(result["status"], "SKIP", name)
                self.assertEqual(result["skip"], 0, name)
                self.assertEqual(result["excluded"], 1, name)
        self.assertEqual(summary["aggregate"]["status"], "PASS")
        self.assertIn("smoke_rc=0", output)

    def test_exclude_single_integration_module_continues_with_later_modules(self):
        _, output, summary, calls = self.run_smoke(exclude="int_hot_upgrade")

        self.assertEqual(len(calls), 11)
        self.assertNotIn("hot_upgrade", [call[1] for call in calls])
        self.assertEqual(calls[-1][1], "xattr")
        self.assertEqual(summary["tools"]["int_hot_upgrade"]["status"], "SKIP")
        self.assertEqual(summary["tools"]["int_hot_upgrade"]["skip"], 0)
        self.assertEqual(summary["tools"]["int_hot_upgrade"]["excluded"], 1)
        self.assertEqual(summary["aggregate"]["status"], "PASS")
        self.assertIn("smoke_rc=0", output)

    def test_zero_selected_cases_fail_module_and_continue(self):
        _, output, summary, calls = self.run_smoke(empty_module="mds_manage")

        self.assertEqual(len(calls), 12)
        self.assertEqual(calls[-1][1], "xattr")
        self.assertEqual(summary["tools"]["int_mds_manage"]["total"], 0)
        self.assertEqual(summary["tools"]["int_mds_manage"]["status"], "FAIL")
        self.assertEqual(summary["aggregate"]["status"], "FAIL")
        self.assertIn("smoke_rc=1", output)

    def test_executed_module_reports_real_skipped_case_count(self):
        _, output, summary, calls = self.run_smoke(skipped_module="dirstat")

        self.assertEqual(len(calls), 12)
        self.assertEqual(calls[-1][1], "xattr")
        self.assertEqual(summary["tools"]["int_dirstat"]["skip"], 1)
        self.assertEqual(summary["tools"]["int_dirstat"]["excluded"], 0)
        self.assertEqual(summary["tools"]["int_dirstat"]["status"], "PASS")
        self.assertEqual(summary["aggregate"]["status"], "PASS")
        self.assertIn("smoke_rc=0", output)

    def test_quota_aggregates_skipped_case_counts(self):
        _, output, summary, calls = self.run_smoke(skipped_module="quota")

        self.assertEqual(len(calls), 12)
        self.assertEqual(calls[-1][1], "xattr")
        self.assertEqual(summary["tools"]["int_quota"]["pass"], 0)
        self.assertEqual(summary["tools"]["int_quota"]["skip"], 2)
        self.assertEqual(summary["tools"]["int_quota"]["excluded"], 0)
        self.assertEqual(summary["tools"]["int_quota"]["total"], 2)
        self.assertEqual(summary["tools"]["int_quota"]["status"], "PASS")
        self.assertEqual(summary["aggregate"]["status"], "PASS")
        self.assertIn("smoke_rc=0", output)

    def test_host_prepared_entrypoint_does_not_repeat_environment_setup(self):
        _, output, _, calls = self.run_smoke()

        self.assertNotIn("unexpected_internal_setup", output)
        self.assertEqual(len(calls), 12)

    def test_unprepared_direct_entrypoint_is_rejected(self):
        source = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        library = source.rsplit('\nmain "$@"', 1)[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = textwrap.dedent(
                f"""
                unset DTT_SMOKE_ENV_READY
                OUTPUT={Path(temp_dir) / 'output'}
                RUN_TIMESTAMP=test-run
                MOUNT=/data
                SCENARIO=all
                NP=16
                SMOKE_EXCLUDE=pjdtest,ltp,xfstest,int
                WECHAT_ENABLED=no
                EMAIL_ENABLED=no
                send_smoke_notification() {{ :; }}
                set +e
                smoke_run
                rc=$?
                set -e
                echo "smoke_rc=$rc"
                exit 0
                """
            )
            result = subprocess.run(
                ["bash", "-c", library + "\n" + harness],
                text=True,
                capture_output=True,
                check=False,
            )
        output = result.stdout + result.stderr

        self.assertIn("smoke_rc=2", output)
        self.assertIn("dtt smoke", output)

    def test_container_smoke_help_matches_the_execution_matrix(self):
        result = subprocess.run(
            ["bash", str(ROOT / "entrypoint.sh"), "-t", "smoke", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        output = result.stdout + result.stderr

        self.assertEqual(result.returncode, 0, output)
        self.assertIn("pjdtest -s all", output)
        self.assertIn("ltp -s smoke", output)
        self.assertIn("xfstest -s quick", output)
        self.assertIn("int_xattr", output)
        self.assertNotIn("mdtest", output.lower())


if __name__ == "__main__":
    unittest.main()
