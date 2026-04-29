---
phase: 15-cli
plan: 01
subsystem: cli
tags: [bash, mlperf, cli, parameter-parsing, help-text]

# Dependency graph
requires: []
provides:
  - mlperf tool listing in dtt --help (CLI-01)
  - show_mlperf_help() function with detailed parameter docs (CLI-02)
  - mlperf scenario validation: resnet50/unet3d/cosmoflow/checkpointing/all (CLI-03)
  - --scale small/medium/large with small default (CLI-04)
  - --file_count positive integer validation with override precedence (CLI-05, CLI-06)
  - --gpu_count positive integer validation with default 1 (CLI-07)
  - mlperf --help routed locally (not via docker run)
affects: [16-exec]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tool-specific help routed locally when tool container differs from main image"
    - "Parameter precedence: explicit --file_count overrides scale-derived default"
    - "Early-exit pattern for mlperf in run_testsuite() before mount/output validation"

key-files:
  modified:
    - dingofs-testsuite-tool

key-decisions:
  - "mlperf --help displayed locally via show_mlperf_help(), not via docker run (different container)"
  - "--file_count takes precedence over --scale when both specified (CLI-06)"
  - "mlperf block placed before mount/output validation to allow early exit"
  - "Phase 15 prints parameter summary and exits; Phase 16 will replace with actual docker run"

requirements-completed:
  - CLI-01
  - CLI-02
  - CLI-03
  - CLI-04
  - CLI-05
  - CLI-06
  - CLI-07

# Metrics
duration: 16min
completed: 2026-04-29
---

# Phase 15 Plan 01: CLI 参数与帮助集成 Summary

**MLPerf CLI help text, tool-specific --help, and parameter parsing (--scale/--file_count/--gpu_count) with validation in the dtt wrapper**

## Performance

- **Duration:** 16 min
- **Started:** 2026-04-29T03:33:45Z
- **Completed:** 2026-04-29T03:50:03Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- `dtt --help` lists `mlperf` as an available tool alongside fio, vdbench, mdtest, pjdtest, ltp, int
- `dtt -t mlperf --help` displays detailed usage with parameter descriptions, valid values, defaults, and examples (rendered locally, not via docker run)
- `-s` accepts all 5 mlperf scenarios: resnet50, unet3d, cosmoflow, checkpointing, all; defaults to "all" when omitted
- `--scale` accepts small/medium/large with small as default
- `--file_count` accepts positive integers; takes precedence over --scale when both specified
- `--gpu_count` accepts positive integers with 1 as default
- All parameter validation with clear error messages on invalid input

## Task Commits

Each task was committed atomically:

1. **Task 1: Update show_help() and create show_mlperf_help() function** - `50866c8` (feat)
2. **Task 2: Add mlperf parameter parsing, validation, and routing** - `cd3051d` (feat)

## Files Created/Modified

- `dingofs-testsuite-tool` - Added mlperf to show_help() tools list, options, examples; created show_mlperf_help() function; added --scale/--file_count/--gpu_count parameter parsing, validation, and routing in run_testsuite(); updated main entry point dispatch

## Decisions Made

- mlperf --help displayed locally via show_mlperf_help() rather than run_docker_help() because mlperf uses a different container (mlperf-storage) than the main dtt image
- --file_count takes precedence over --scale when both specified, evidenced by "(overrides --scale default)" in output
- mlperf validation block placed before mount/output checks to allow early exit without requiring testdir/output configuration
- Phase 15 prints a parameter summary and exits with placeholder message; Phase 16 will replace this with actual docker run command construction

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Moved mlperf block before mount/output validation checks**

- **Found during:** Task 2 (mlperf parameter parsing and validation)
- **Issue:** The plan instructed to place mlperf validation after tool validation. However, in the actual code, mount/output validation occurs BEFORE tool validation. This caused mlperf commands to fail with "Test directory not set." before reaching the mlperf-specific code block.
- **Fix:** Restructured the code order so the mlperf block (with its early exit) runs immediately after argument parsing and config fallback, before the mount/output validation section. This allows mlperf commands to exit without requiring testdir/output configuration.
- **Files modified:** dingofs-testsuite-tool
- **Verification:** All 20+ behavioral tests pass, including `dtt -t mlperf -s resnet50`, `dtt -t mlperf -s all`, scale/file_count/gpu_count variations, and error cases.
- **Committed in:** cd3051d (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix for correctness. Without this reordering, every mlperf command would fail at the mount validation check. No scope creep.

## Known Stubs

- **Phase 15 placeholder exit:** The mlperf block in `run_testsuite()` prints "MLPerf execution will be available in Phase 16." and exits. Phase 16 (MLPerf 容器执行与数据集成) will replace this with actual `docker run mlperf-storage` command construction with proper --shm-size, volume mounts, and result collection.

## Issues Encountered

None beyond the auto-fixed deviation above.

## Next Phase Readiness

- All 7 CLI requirements (CLI-01 through CLI-07) delivered
- Parameter parsing is fully validated and ready for Phase 16 to consume
- Phase 16 can directly use the validated `$scenario`, `$scale`, `$file_count`, `$gpu_count` variables to construct the mlperf-storage docker run command
- No blockers or unresolved concerns

---
*Phase: 15-cli*
*Completed: 2026-04-29*
