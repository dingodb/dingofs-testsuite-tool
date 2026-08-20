# DTT Smoke Suite Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `dtt smoke` prepare a dedicated tool environment, run the requested three filesystem tool scenarios, and execute the exact reduced integration-test matrix with daily-compatible environments.

**Architecture:** The host wrapper prepares `env_126_tool` once before starting the smoke container and reloads the resulting `testdir`. Inside the container, `smoke_run` keeps fail-continue behavior, runs three tool phases plus a table-driven set of integration phases, aggregates the two quota invocations, and emits one combined JSON/text/notification summary.

**Tech Stack:** Bash, Python `unittest`, DingoFS integration-test YAML configuration.

**Spec:** User-approved conversation requirements from 2026-08-19; no separate design file exists.

## Global Constraints

- Do not run `mdtest` from `dtt smoke`; standalone mdtest behavior remains unchanged.
- Tool phases are exactly pjdtest `all`, LTP `smoke`, and xfstest `quick`.
- Before any enabled tool phase, prepare `env_126_tool`; abort smoke if preparation fails.
- `env_126_tool` mirrors `env_126_dirstat` except for its environment key and independent `tool-test` filesystem name.
- Integration environments must match `dtt daily`; every integration invocation uses `--reruns 2`.
- Quota runs only `verify_fs_capacity.yaml` and `verify_fs_quota.yaml`; all other selections are exactly those requested by the user.
- Preserve fail-continue behavior after individual test failures and preserve xfstest's narrow root-helper security boundary.
- Preserve unrelated working-tree changes and do not commit or push without a later explicit request.

---

### Task 1: Dedicated tool environment and host setup gate

**Files:**
- Create: `dingofs-integration-test/conf/env/env_126_tool.yaml`
- Create: `dingofs-integration-test/tests/test_env_126_tool.py`
- Modify: `tests/test_smoke_xfstest.py`
- Modify: `dingofs-testsuite-tool`

**Interfaces:**
- Consumes: `cmd_setup_env <env_name>` and the persisted `testdir` config.
- Produces: `cmd_smoke` prepares `env_126_tool`, reloads `testdir`, and starts the container only after successful setup.

- [x] **Step 1: Write the failing environment parser test**

```python
def test_tool_environment_uses_dedicated_identity_and_dirstat_layout(self):
    env = parse_environment("env_126_tool")
    self.assertEqual(env.name, "env_126_tool")
    self.assertEqual(env.clients[0].fs_name, "tool-test")
    self.assertEqual(env.mds_addr, "172.30.14.126:6900,172.30.14.126:6901,172.30.14.126:6902")
    self.assertEqual(env.storage.storage_type, "s3")
```

- [x] **Step 2: Run the parser test and verify RED**

Run: `python3 -m unittest dingofs-integration-test/tests/test_env_126_tool.py -v`

Expected: failure because `env_126_tool` cannot yet be parsed.

- [x] **Step 3: Add wrapper behavior tests for setup ordering and failure**

Extend the wrapper harness so a fake `cmd_setup_env` writes a new `testdir`, the fake runtime records its launch, and assertions prove:

```python
self.assertEqual(events, ["setup:env_126_tool", "runtime"])
self.assertIn(f"{new_mount}:/data", runtime_args)
self.assertEqual(failed_setup.returncode, 17)
self.assertFalse(runtime_args_file.exists())
```

- [x] **Step 4: Run the wrapper tests and verify RED**

Run: `python3 -m unittest tests.test_smoke_xfstest.SmokeXfstestTest.test_dtt_smoke_sets_up_tool_environment_before_container tests.test_smoke_xfstest.SmokeXfstestTest.test_dtt_smoke_aborts_when_tool_environment_setup_fails -v`

Expected: failures because `cmd_smoke` does not prepare `env_126_tool`.

- [x] **Step 5: Implement the environment and setup gate**

Create the YAML by copying the dirstat environment values, changing only the root key to `env_126_tool` and the client filesystem name to `tool-test`. In `cmd_smoke`, call `cmd_setup_env env_126_tool` when at least one of pjdtest/LTP/xfstest is enabled, return its exact non-zero status, then reload `config_testdir` before resolving the mount.

- [x] **Step 6: Run Task 1 tests and verify GREEN**

Run: `python3 -m unittest dingofs-integration-test/tests/test_env_126_tool.py tests.test_smoke_xfstest -v`

Expected: all selected tests pass.

### Task 2: Exact smoke execution matrix and combined results

**Files:**
- Create: `tests/test_smoke_suite.py`
- Modify: `tests/test_smoke_xfstest.py`
- Modify: `entrypoint.sh`

**Interfaces:**
- Consumes: the mount passed by `cmd_smoke`, `run_tests.py` per-module `--env`, `--case`, and `--run-level` flags.
- Produces: three tool results and eleven integration-module results in console output, JSON, text, and notifications.

- [x] **Step 1: Write a failing behavior test for the exact command matrix**

Run `smoke_run` through a shell harness whose `python3` function records real arguments and emits a one-case suite summary. Assert literal commands for:

```text
quota --env env_126_quota --case testcases/quota_test_cases/smoke/verify_fs_capacity.yaml --reruns 2
quota --env env_126_quota --case testcases/quota_test_cases/smoke/verify_fs_quota.yaml --reruns 2
basic_file_operation --env env_126_smoke --reruns 2
client --env env_40_dingofs --run-level smoke --reruns 2
cache_node --env env_40_dingofs --run-level smoke --reruns 2
dirstat --env env_126_dirstat --case testcases/dirstat_test_cases/smoke --reruns 2
hot_upgrade --env env_126_hotupgrade_multi --case testcases/hot_upgrade_test_cases/smoke --reruns 2
mds_manage --env env_126_mds_manage --case testcases/mds_manage_test_cases/smoke --reruns 2
mount_subdir --env env_126_mount_subdir --case testcases/mount_subdir_test_cases/smoke/verify_mount_subdir.yaml --reruns 2
trash --env env_126_trash --case testcases/trash_test_cases/smoke --reruns 2
warmup --env env_126_warmup --case testcases/warmup_test_cases/smoke --reruns 2
xattr --env env_126_xattr --case testcases/xattr_test_cases/smoke --reruns 2
```

Also assert pjdtest sees `all`, LTP sees `smoke`, xfstest sees `quick`, quota totals two cases, all eleven integration keys exist, and `mdtest` is absent from the JSON summary.

- [x] **Step 2: Run the matrix test and verify RED**

Run: `python3 -m unittest tests.test_smoke_suite -v`

Expected: failure showing missing integration commands and the obsolete mdtest summary entry.

- [x] **Step 3: Write a failing continuation and quota aggregation test**

Make the fake runner fail one quota case and one middle integration module. Assert both failures affect aggregate exit status, the second quota case and later xattr phase still execute, and quota reports `pass=1`, `fail=1`, `total=2`.

- [x] **Step 4: Run the failure-path test and verify RED**

Run: `python3 -m unittest tests.test_smoke_suite.SmokeSuiteTest.test_failures_are_aggregated_without_stopping_later_modules -v`

Expected: failure because the current runner has no requested matrix or two-case quota aggregation.

- [x] **Step 5: Implement table-driven integration execution**

Remove the internal `test_env_setup.py` call and mdtest phase. Add one helper that executes a module with its literal environment/selection arguments, captures the Python exit code through `tee`, parses the log, and stores dynamic pass/fail/total values. Invoke quota twice and sum both results; invoke each remaining module once in the requested order.

- [x] **Step 6: Update all smoke outputs**

Generate status and statistics for pjdtest, LTP, xfstest, and all eleven integration keys. Remove mdtest from JSON, text, console, and notification details. Keep xfstest scenario `quick` and preserve its privileged helper unchanged.

- [x] **Step 7: Run smoke behavior tests and verify GREEN**

Run: `python3 -m unittest tests.test_smoke_suite tests.test_smoke_xfstest -v`

Expected: all selected tests pass.

### Task 3: User-facing help and full verification

**Files:**
- Modify: `dingofs-testsuite-tool`
- Modify: `entrypoint.sh`
- Modify: `README.md`

**Interfaces:**
- Consumes: the final matrix and exclude names from Task 2.
- Produces: accurate `dtt smoke --help`, container help, and README documentation.

- [x] **Step 1: Update human-facing documentation**

Document the tool-environment setup, the three tool scenarios, all eleven integration selections/environments, fail-continue behavior, and the `int` exclusion group. Remove mdtest from smoke examples and counts without changing standalone mdtest documentation.

- [x] **Step 2: Run syntax and focused test verification**

Run:

```bash
bash -n dingofs-testsuite-tool
bash -n entrypoint.sh
python3 -m py_compile tests/test_smoke_suite.py tests/test_smoke_xfstest.py dingofs-integration-test/tests/test_env_126_tool.py
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s dingofs-integration-test/tests -p 'test_env_126_tool.py' -v
git diff --check
```

Expected: every command exits zero with no failures or whitespace errors.

- [x] **Step 3: Review the final diff against every exact selection**

Check the command matrix, environments, quota aggregation, setup failure boundary, mdtest removal, xfstest helper inputs, report keys, and unrelated-file preservation. Record any limitation rather than committing or pushing.
