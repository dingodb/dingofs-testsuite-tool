# Quick Task 260521-leq: SUMMARY

**Date:** 2026-05-21
**Status:** Complete

## Changes

### 1. dtt config add int_env param
- Added `int_env` config key with default value `env_126_smoke`
- Added `load_config`/`save_config` support
- Added `dtt config set int_env` and `dtt config show` support
- Added help text entry
- `cmd_smoke()` passes `INT_ENV` env var to container

### 2. smoke_run() add 3 integration test scenarios
- Added `INT_ENV` reading in entrypoint.sh
- Added `parse_int_smoke_output()` function for pytest output parsing
- Added 3 new smoke steps (tools 4-6):
  - int_client: `python3 run_tests.py client --run-level smoke --env $INT_ENV --reruns 5`
  - int_cache_node: `python3 run_tests.py cache_node --run-level smoke --env $INT_ENV --reruns 5`
  - int_quota: `python3 run_tests.py quota --run-level smoke --env env_126_quota --reruns 5`
- Updated `generate_smoke_summary()` with int results in JSON and text
- Updated `send_smoke_notification()` with int results in notification details
- Updated smoke_run header from 3 to 6 tools
- All tests run under `/dingofs-integration-test` directory
