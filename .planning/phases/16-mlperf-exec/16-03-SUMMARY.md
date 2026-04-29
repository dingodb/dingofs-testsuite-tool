---
phase: 16-mlperf-exec
plan: 03
subsystem: infra
tags: [bash, docker, mlperf]

# Dependency graph
requires:
  - phase: 15-cli
    provides: "mlperf parameter parsing, validation, help infrastructure in dtt wrapper"
provides:
  - "docker run command construction for mlperf with env var mapping (MODELS, SCALE, NUM_ACCELERATORS)"
  - "--shm-size=8g shared memory allocation for PyTorch DataLoader"
  - "volume mounts: testdir→/data, output→/output with validation"
  - "updated help text reflecting mlperf integration into dtt image"
  - "exec-based container launch for signal passthrough"
affects: [dockerfile, entrypoint]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "docker run construction via bash array with conditional -e flags"
    - "exec for container process replacement (signal passthrough)"

key-files:
  modified:
    - dingofs-testsuite-tool

key-decisions:
  - "SCALE=$file_count takes precedence over SCALE=$scale when --file_count set (CLI-06)"
  - "exec used for container launch so Ctrl+C signals pass through to container"
  - "mlperf mount/output validation inside mlperf block (does not affect non-mlperf tools)"
  - "--shm-size=8g hardcoded per D-04/EXEC-03 requirement"

patterns-established:
  - "docker_cmd array pattern extended to mlperf with -it --shm-size=8g flags"

requirements-completed: [EXEC-01, EXEC-02, EXEC-03, DATA-01, DATA-02]

# Metrics
duration: 289s
completed: 2026-04-29
---

# Phase 16 Plan 03: MLPerf Docker Run Integration Summary

**Replaced mlperf placeholder with docker run command construction passing MODELS/SCALE/NUM_ACCELERATORS env vars, --shm-size=8g, and volume mounts via exec**

## Performance

- **Duration:** 4 min 49 sec (289 seconds)
- **Started:** 2026-04-29T06:06:11Z
- **Completed:** 2026-04-29T06:11:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Replaced Phase 15 mlperf placeholder (lines 564-574) with production docker run command construction
- Mapped CLI params to mlperf env vars: `-s`→MODELS, `--scale`→SCALE, `--file_count`→SCALE, `--gpu_count`→NUM_ACCELERATORS
- Added `--shm-size=8g` shared memory for PyTorch DataLoader multi-process data loading
- Volume mounts: testdir→/data, output→/output with pre-flight validation (config checks, directory existence)
- `--file_count` overrides `--scale` for SCALE env var (CLI-06 from Phase 15)
- Container launched with `exec` for proper signal passthrough (Ctrl+C reaches container)
- Updated show_mlperf_help() to reflect mlperf-storage integration into dtt image (D-01)
- Updated scale descriptions to remove misleading specific file counts, added MLPerf compliance notes
- Added `--shm-size=8g` and `-it` notes to show_help() mlperf examples

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace mlperf placeholder with docker run command construction** - `d6d9490` (feat)
2. **Task 2: Update show_mlperf_help() note and fix help examples** - `200ef20` (docs)

## Files Modified

- `dingofs-testsuite-tool` - Replaced mlperf placeholder block with docker run construction (65 insertions, 14 deletions), updated help text in show_mlperf_help() and show_help()

## Decisions Made

None - followed plan as specified. All implementation decisions (exec usage, CLI-06 precedence, hardcoded --shm-size=8g, in-block validation) were pre-specified in the plan.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. The dtt wrapper is self-contained.

## Next Phase Readiness

- dtt wrapper now constructs the full docker run command for mlperf
- Container receives all required env vars (MODELS, SCALE, NUM_ACCELERATORS, ACCELERATOR_TYPE, LOOPS, SUBMISSION_MODE)
- Volume mounts and --shm-size=8g are in place
- Phase 16 execution is complete; mlperf end-to-end flow is ready for testing
- Remaining Phase 16 plans (16-01 Dockerfile, 16-02 entrypoint.sh) handle the container-side implementation

---
*Phase: 16-mlperf-exec*
*Completed: 2026-04-29*
