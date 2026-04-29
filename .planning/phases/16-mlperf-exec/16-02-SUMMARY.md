---
phase: 16-mlperf-exec
plan: "02"
subsystem: entrypoint
tags: [mlperf, entrypoint, dispatch, orchestration]
type: execute
autonomous: true
wave: 1
depends_on: []
key_files:
  created: []
  modified:
    - entrypoint.sh
decisions:
  - "mlperf_run() follows existing run function patterns (ltp_run, integration_run) with OUTPUT_BASE export, auto-detection, and notification support"
  - "MODELS='all' expands to unet3d,resnet50,cosmoflow,checkpointing (four standard MLPerf models)"
  - "CLIENT_HOST_MEMORY_GB and NUM_PROCESSES auto-detect when not explicitly set via environment variables"
  - "mlperf skips SCENARIO validation like mdtest (scenario defaults to 'all')"
tech_stack:
  added: []
  patterns:
    - "run function pattern: parameter defaults -> auto-detect resources -> configuration banner -> loop execution -> summary -> log_result -> notifications"
metrics:
  duration_seconds: 550
  completed_date: "2026-04-29T06:14:53Z"
  task_count: 2
  file_count: 1
requirements:
  - EXEC-01
  - EXEC-02
  - DATA-03
---

# Phase 16 Plan 02: MLPerf Entrypoint Integration Summary

**One-liner:** Added mlperf tool support to entrypoint.sh with validation, dispatch routing, container-side help, and an mlperf_run() function that orchestrates multi-model MLPerf benchmarks by calling run_model.sh with auto-detected system resources.

## What Changed

### Task 1: Validation, Dispatch, and Help Integration
10 surgical changes to entrypoint.sh adding mlperf recognition as a valid tool:
- **TOOL validation regex**: Added `|mlperf` to the accepted tool list
- **Scenario validation skip**: mlperf (like mdtest) skips scenario existence check
- **`--help` routing**: `-t mlperf --help` routes to `show_mlperf_help()`
- **dispatch_tool()**: `mlperf)` case routes to `mlperf_run`
- **scenario_exists()**: Validates resnet50/unet3d/cosmoflow/checkpointing/all
- **show_help()**: Added tools list entry, examples, and output format documentation
- **log_result()**: mlperf case uses exit code 0 = SUCCESS
- **show_mlperf_help()**: New 30-line help function documenting scenarios, env vars, and usage

### Task 2: mlperf_run() Orchestration Function
155-line function orchestrating multi-model MLPerf benchmarks:
- Creates output directories under `/output/mlperf_<timestamp>/`
- Exports `OUTPUT_BASE` env var for downstream consumption by run_model.sh
- Sets defaults for all MLPerf environment variables (MODELS, SCALE, NUM_ACCELERATORS, etc.)
- Auto-detects `CLIENT_HOST_MEMORY_GB` from `/proc/meminfo` and `NUM_PROCESSES` via `nproc`
- Expands `MODELS="all"` to all four standard models
- Validates each model name before execution
- Prints ANSI-colored configuration banner
- Loops through models, calling `/usr/local/bin/run_model.sh` for each
- Tracks PASSED/FAILED status per model
- Prints summary table with each model's result
- Calls `log_result` for result persistence
- Sends WeChat/Email notifications if enabled
- Returns overall exit code (0 = all passed, 1 = any failed)

## Verification Results

### Phase-Level Checks
1. `bash -n entrypoint.sh` -- PASSED (no syntax errors)
2. `grep -c "show_mlperf_help" entrypoint.sh` -- 2 (function def + routing reference)
3. `grep -c "mlperf_run" entrypoint.sh` -- 2 (dispatch + function def)
4. dispatch routing: `mlperf)` case correctly points to `mlperf_run`
5. `OUTPUT_BASE` exported inside mlperf_run() for run_model.sh consumption
6. `run_model.sh` invoked inside mlperf_run() loop with proper parameters
7. All existing dispatch cases present: fio_run, vdbench_run, mdtest_run, pjdtest_run, ltp_run, integration_run

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | 2e8e138 | feat(16-mlperf-exec): add mlperf validation, dispatch routing, and help to entrypoint.sh |
| 2 | 968636f | feat(16-mlperf-exec): create mlperf_run() function in entrypoint.sh |

## Deviations from Plan

None -- plan executed exactly as written.

## Auth Gates

None.

## Known Stubs

None.
