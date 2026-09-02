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
        smoke_base_env="env_126",
        report_generator_failure=False,
        report_copy_failure=False,
        initial_latest=False,
        report_url_ready=True,
    ):
        source = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        library = source.rsplit('\nmain "$@"', 1)[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            harness = textwrap.dedent(
                f"""
                INTEGRATION_DIR={shlex.quote(str(ROOT / 'dingofs-integration-test'))}
                OUTPUT={temp / 'output'}
                RUN_TIMESTAMP=test-run
                INT_ENV=unused
                MOUNT=/data
                SCENARIO=original
                NP=16
                WECHAT_ENABLED=no
                EMAIL_ENABLED=no
                SMOKE_EXCLUDE={shlex.quote(exclude)}
                SMOKE_BASE_ENV={shlex.quote(smoke_base_env)}
                DTT_SMOKE_ENV_READY=1
                DINGOFS_META_URL_TEMPLATE='mds://127.0.0.1:6900/{{fsname}}'
                FAIL_QUOTA_CAPACITY={'yes' if fail_quota_capacity else 'no'}
                FAIL_HOT_UPGRADE={'yes' if fail_hot_upgrade else 'no'}
                SUITE_ERROR_MODULE={shlex.quote(suite_error_module)}
                EMPTY_MODULE={shlex.quote(empty_module)}
                SKIPPED_MODULE={shlex.quote(skipped_module)}
                REPORT_GENERATOR_FAILURE={'yes' if report_generator_failure else 'no'}
                REPORT_COPY_FAILURE={'yes' if report_copy_failure else 'no'}
                INITIAL_LATEST={'yes' if initial_latest else 'no'}
                REPORT_URL_READY={'yes' if report_url_ready else 'no'}
                REAL_PYTHON3=$(type -P python3)
                REAL_CP=$(type -P cp)

                mkdir -p "$OUTPUT"
                DTT_SMOKE_REPORT_URL_FILE="$OUTPUT/.dtt-smoke-report-url-test"
                printf '%s\n' \
                    'http://192.0.2.10:8888/allure-smoke-report-latest/index.html' \
                    > "$DTT_SMOKE_REPORT_URL_FILE"
                SMOKE_REPORT_URL='http://stale.invalid/previous-report'
                export DTT_SMOKE_REPORT_URL_FILE SMOKE_REPORT_URL
                if [[ "$INITIAL_LATEST" == yes ]]; then
                    mkdir -p "$OUTPUT/allure-smoke-report-latest"
                    printf 'previous report' > \
                        "$OUTPUT/allure-smoke-report-latest/index.html"
                fi

                python3() {{
                    if [[ "$1" == "-c" ]]; then
                        if [[ "$REPORT_GENERATOR_FAILURE" == yes ]]; then
                            return 23
                        fi
                        "$REAL_PYTHON3" "$@"
                        return $?
                    fi
                    if [[ "$*" == *tests/test_env_setup.py* ]]; then
                        echo "unexpected_internal_setup"
                        echo "DINGOFS_TEMP_MOUNTDIR=/tmp/wrong-mount"
                        return 0
                    fi

                    printf 'python3_call:'
                    printf ' %q' "$@"
                    echo
                    local command_line="$*"
                    local report_dir=""
                    local previous=""
                    local argument
                    for argument in "$@"; do
                        if [[ "$previous" == "--report-dir" ]]; then
                            report_dir="$argument"
                            break
                        fi
                        previous="$argument"
                    done
                    if [[ -n "$report_dir" ]]; then
                        local result_name
                        result_name=$(basename "$(dirname "$report_dir")")
                        mkdir -p "$report_dir"
                        printf '{{"name":"%s","status":"passed"}}\n' \
                            "$result_name" > "$report_dir/${{result_name}}-result.json"
                    fi
                    local failed=no
                    if [[ "$FAIL_QUOTA_CAPACITY" == yes ]] && \
                       [[ "$command_line" == *verify_fs_capacity.yaml* ]]; then
                        failed=yes
                    fi
                    if [[ "$FAIL_HOT_UPGRADE" == yes ]] && \
                       [[ "$command_line" == *"run_tests.py hot_upgrade "* ]]; then
                        failed=yes
                    fi
                    echo "TEST SUITE SUMMARY"
                    if [[ -n "$EMPTY_MODULE" ]] && \
                       [[ "$command_line" == *"run_tests.py $EMPTY_MODULE "* ]]; then
                        echo "Total Cases: 0"
                        echo "Passed: 0"
                        echo "Failed: 0"
                        echo "Suite Errors: 0"
                        echo "Skipped: 0"
                        return 0
                    fi
                    if [[ -n "$SKIPPED_MODULE" ]] && \
                       [[ "$command_line" == *"run_tests.py $SKIPPED_MODULE "* ]]; then
                        echo "Total Cases: 1"
                        echo "Passed: 0"
                        echo "Failed: 0"
                        echo "Suite Errors: 0"
                        echo "Skipped: 1"
                        return 0
                    fi
                    echo "Total Cases: 1"
                    if [[ -n "$SUITE_ERROR_MODULE" ]] && \
                       [[ "$command_line" == *"run_tests.py $SUITE_ERROR_MODULE "* ]]; then
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
                cp() {{
                    if [[ "$REPORT_COPY_FAILURE" == yes ]] && \
                       [[ "$*" == *allure-smoke-report-history* ]]; then
                        return 24
                    fi
                    "$REAL_CP" "$@"
                }}
                smoke_report_url_is_ready() {{
                    [[ "$REPORT_URL_READY" == yes ]]
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
                send_smoke_notification() {{
                    echo "notify_report_url=${{SMOKE_REPORT_URL:-}}"
                    return 0
                }}

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
            smoke_base = temp / "output" / "smoke_test-run"
            aggregate_results = smoke_base / "allure-results"
            persistent_latest = temp / "output" / "allure-smoke-report-latest"
            persistent_history = (
                temp
                / "output"
                / "allure-smoke-report-history"
                / "allure-report-test-run"
            )
            latest_index = persistent_latest / "index.html"
            self.last_smoke_artifacts = {
                "result_files": sorted(
                    path.name for path in aggregate_results.glob("*-result.json")
                ),
                "run_latest": (smoke_base / "allure-report-latest" / "index.html").is_file(),
                "persistent_latest": (persistent_latest / "index.html").is_file(),
                "persistent_history": (persistent_history / "index.html").is_file(),
                "public_latest": (
                    temp
                    / "output"
                    / ".dtt-smoke-report-public"
                    / "live"
                    / "allure-smoke-report-latest"
                    / "index.html"
                ).is_file(),
                "latest_content": (
                    latest_index.read_text(encoding="utf-8")
                    if latest_index.is_file()
                    else None
                ),
                "report_url_ready": Path(
                    f"{temp / 'output' / '.dtt-smoke-report-url-test'}.ready"
                ).is_file(),
            }
            output = result.stdout + result.stderr
            calls = [
                shlex.split(line.removeprefix("python3_call:").strip())
                for line in output.splitlines()
                if line.startswith("python3_call:")
            ]
            return result, output, summary, calls

    def test_generates_one_aggregate_allure_report_for_executed_int_modules(self):
        result, output, _, calls = self.run_smoke(
            exclude="int_client,int_cache_node,xfstest"
        )

        self.assertEqual(result.returncode, 0, output)
        self.assertEqual(len(calls), 10)
        self.assertEqual(
            self.last_smoke_artifacts["result_files"],
            [
                "basic_file_operation-result.json",
                "dirstat-result.json",
                "hot_upgrade-result.json",
                "mds_manage-result.json",
                "mount_subdir-result.json",
                "trash-result.json",
                "verify_fs_capacity-result.json",
                "verify_fs_quota-result.json",
                "warmup-result.json",
                "xattr-result.json",
            ],
        )
        self.assertTrue(self.last_smoke_artifacts["run_latest"])
        self.assertTrue(self.last_smoke_artifacts["persistent_latest"])
        self.assertTrue(self.last_smoke_artifacts["persistent_history"])
        self.assertTrue(self.last_smoke_artifacts["public_latest"])
        self.assertTrue(self.last_smoke_artifacts["report_url_ready"])
        self.assertIn(
            "notify_report_url=http://192.0.2.10:8888/"
            "allure-smoke-report-latest/index.html",
            output,
        )
        self.assertIn("Allure report:", output)

    def test_report_generation_failure_preserves_test_exit_and_previous_latest(self):
        _, output, summary, _ = self.run_smoke(
            fail_hot_upgrade=True,
            report_generator_failure=True,
            initial_latest=True,
        )

        self.assertEqual(summary["aggregate"]["exit_code"], 1)
        self.assertIn("smoke_rc=1", output)
        self.assertIn("notify_report_url=", output)
        self.assertNotIn("notify_report_url=http", output)
        self.assertEqual(self.last_smoke_artifacts["latest_content"], "previous report")
        self.assertFalse(self.last_smoke_artifacts["report_url_ready"])

    def test_report_copy_failure_preserves_test_exit_and_previous_latest(self):
        _, output, summary, _ = self.run_smoke(
            fail_hot_upgrade=True,
            report_copy_failure=True,
            initial_latest=True,
        )

        self.assertEqual(summary["aggregate"]["exit_code"], 1)
        self.assertIn("smoke_rc=1", output)
        self.assertIn("notify_report_url=", output)
        self.assertNotIn("notify_report_url=http", output)
        self.assertEqual(self.last_smoke_artifacts["latest_content"], "previous report")
        self.assertFalse(self.last_smoke_artifacts["report_url_ready"])

    def test_final_http_readiness_failure_omits_link_and_preserves_test_exit(self):
        _, output, summary, _ = self.run_smoke(
            fail_hot_upgrade=True,
            report_url_ready=False,
        )

        self.assertEqual(summary["aggregate"]["exit_code"], 1)
        self.assertIn("smoke_rc=1", output)
        self.assertTrue(self.last_smoke_artifacts["public_latest"])
        self.assertFalse(self.last_smoke_artifacts["report_url_ready"])
        self.assertNotIn("notify_report_url=http", output)
        self.assertIn("final readiness check", output)

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

    def test_env_127_switches_only_the_126_based_integration_environments(self):
        result, output, _, calls = self.run_smoke(smoke_base_env="env_127")

        environments = [(call[1], call[3]) for call in calls]
        self.assertEqual(result.returncode, 0, output)
        self.assertEqual(
            environments,
            [
                ("quota", "env_127_quota"),
                ("quota", "env_127_quota"),
                ("basic_file_operation", "env_127_smoke"),
                ("client", "env_40_dingofs"),
                ("cache_node", "env_40_dingofs"),
                ("dirstat", "env_127_dirstat"),
                ("hot_upgrade", "env_127_hotupgrade_multi"),
                ("mds_manage", "env_127_mds_manage"),
                ("mount_subdir", "env_127_mount_subdir"),
                ("trash", "env_127_trash"),
                ("warmup", "env_127_warmup"),
                ("xattr", "env_127_xattr"),
            ],
        )

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
        self.assertTrue(self.last_smoke_artifacts["run_latest"])
        self.assertTrue(self.last_smoke_artifacts["persistent_latest"])

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
            script = Path(temp_dir) / "run-smoke-test.sh"
            script.write_text(library + "\n" + harness, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(script)],
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
