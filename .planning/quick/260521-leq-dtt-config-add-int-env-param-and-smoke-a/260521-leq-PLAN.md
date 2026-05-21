# Quick Task 260521-leq: dtt config add int_env param and smoke add client/cache_node/quota scenarios

## Task 1: Add int_env config param to dtt wrapper

**files:** `dingofs-testsuite-tool`

- Add `INTENV_FILE` and default `env_126_smoke`
- Add `int_env` to `load_config()`, `save_config()`, `cmd_config()` set/show/help
- Pass `INT_ENV` env var to container in `cmd_smoke()`

## Task 2: Add client/cache_node/quota scenarios to smoke_run()

**files:** `entrypoint.sh`

- Read `INT_ENV` env var (default `env_126_smoke`)
- Add 3 new int-test steps in `smoke_run()` after ltp, executed under `/dingofs-integration-test`
- Commands:
  - `python3 run_tests.py client --run-level smoke --env $INT_ENV --reruns 5`
  - `python3 run_tests.py cache_node --run-level smoke --env $INT_ENV --reruns 5`
  - `python3 run_tests.py quota --run-level smoke --env env_126_quota --reruns 5`
- Parse pytest output for pass/fail counts
- Include results in smoke summary and notification
