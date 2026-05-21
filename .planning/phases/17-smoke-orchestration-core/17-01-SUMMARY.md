---
phase: 17-smoke-orchestration-core
plan: 01
status: complete
completed: "2026-05-20"
requirements: [SMOKE-01, SMOKE-02, OUT-01]
---

# Phase 17 Execution Summary

## Changes

### entrypoint.sh

**SMOKE_MODE guards** (Task 1):
- `pjdtest_run()`: Wrapped WeChat + Email notification blocks in `if [[ "$SMOKE_MODE" != "1" ]]`
- `mdtest_run()`: Same guard wrapping per-scenario notification blocks inside the `for` loop
- `ltp_run()`: Same guard wrapping notification blocks

**smoke_run() orchestrator** (Task 2):
- New function inserted between `mlperf_run()` and Mode Handling section
- Executes pjdtest_run → mdtest_run → ltp_run in sequence with `set +e`/`set -e` per tool
- Sets `export SMOKE_MODE=1` to suppress per-tool notifications
- Creates unified `smoke_<RUN_TIMESTAMP>/` output directory with `pjdtest/`, `mdtest/`, `ltp/` subdirectories
- Saves/restores original OUTPUT, SCENARIO, NP environment variables
- Returns aggregate exit code: 0 if all pass, 1 if any fail

**Dispatch wiring** (Task 3):
- `validate_params()`: Added `smoke` to valid tool regex; skips scenario validation for smoke
- `scenario_exists()`: Added `smoke)` case returning 0
- `dispatch_tool()`: Added `smoke)` case routing to `smoke_run`
- `parse_args()`: Added `smoke) show_smoke_help` for `-t smoke --help`
- `show_help()`: Updated Options line and added smoke bullet to Tools section
- `show_smoke_help()`: New help function with usage, examples, and notes

## Verification

- `bash -n entrypoint.sh`: PASS
- SMOKE_MODE guards: 3 (one per _run function)
- smoke_run() function: 1 (exact match)
- smoke in dispatch_tool: yes
- smoke in validate regex: yes
- show_smoke_help: 2 refs (definition + dispatch)
- set +e in smoke_run: 3 (one per tool call)
- tool calls in smoke_run: 3 (pjdtest_run, mdtest_run, ltp_run)

## Requirements Satisfied

| Req | Description | How |
|-----|-------------|-----|
| SMOKE-01 | Serial execution pjdtest→mdtest→ltp | smoke_run() calls in order |
| SMOKE-02 | Fail-continue | set +e/set -e per tool, aggregate exit |
| OUT-01 | Unified output dir | smoke_<ts>/{pjdtest,mdtest,ltp}/ |
