---
phase: 16-mlperf-exec
plan: 01
subsystem: image-build
type: execute
wave: 1
autonomous: true
status: complete
date: "2026-04-29"
completed_date: "2026-04-29"
duration: "4m 10s"
plan_file: .planning/phases/16-mlperf-exec/16-01-PLAN.md

tags:
  - dockerfile
  - multi-stage-build
  - mlperf-storage
  - python-venv
  - run_model.sh

depends_on: []
provides:
  - mlperf-builder
  - run_model.sh
affects:
  - final-image
  - mlperf_run

tech-stack:
  added:
    - Python 3.12 venv
    - dlio-benchmark (mlperf_storage_v2.0)
    - mlpstorage v2.0
    - CPU PyTorch + torchvision
    - CPU TensorFlow + tfrecord
  patterns:
    - Multi-stage Docker build
    - venv-based Python isolation
    - COPY --from inter-stage artifact transfer

decisions:
  - Used --no-deps pip install to avoid GPU dependency bloat
  - CPU-only PyTorch/TensorFlow saves ~2.3GB vs GPU wheels
  - OUTPUT_BASE env var for redirectable results/logs path
  - Re-added plain-text logging helpers after removing ANSI block (Rule 1 deviation)

key-files:
  created:
    - run_model.sh (379 lines, executable, dtt-adapted mlperf lifecycle script)
  modified:
    - Dockerfile (+83/-1, added mlperf-builder multi-stage build and final-stage copies)

commits:
  - 1a68b63: feat(16-mlperf-exec): add adapted run_model.sh with OUTPUT_BASE support
  - a2dd83a: feat(16-mlperf-exec): add mlperf-builder multi-stage build and artifact copy

requirements:
  completed:
    - EXEC-01 (mlperf-storage installed in dtt image via multi-stage build)
    - DATA-03 (OUTPUT_BASE env var enables results redirection to output volume)

verification:
  all: PASSED
  checks:
    - "bash -n run_model.sh syntax check: PASSED"
    - "OUTPUT_BASE referenced in run_model.sh: PASSED"
    - "All 7 upstream functions preserved: PASSED"
    - "AS mlperf-builder stage exists: PASSED"
    - "COPY --from=mlperf-builder (3 copies): PASSED"
    - "PATH includes /opt/mlpstorage-env/bin: PASSED"
    - "OPENBLAS_NUM_THREADS and OMP_NUM_THREADS set: PASSED"
    - "tensorflow-cpu installed: PASSED"
    - "dlio_benchmark patches applied: PASSED"
    - "python3.12-venv, procps, bc in apt-get: PASSED"
---

# Phase 16 Plan 01: MLPerf Builder Stage and run_model.sh Summary

**One-liner:** Added mlperf-builder multi-stage build (Python 3.12 venv, dlio-benchmark, mlpstorage v2.0, CPU PyTorch/TensorFlow) and adapted run_model.sh with OUTPUT_BASE support for dtt output volume conventions.

## Tasks Completed

### Task 1: Create adapted run_model.sh for dtt output conventions

Created `run_model.sh` (379 lines) adapted from the upstream mlperf-storage run_model.sh with these key changes:

1. **OUTPUT_BASE env var** (defaults to `/data`, overridable to `/output/mlperf_<timestamp>`)
2. **RESULTS_DIR** uses `$OUTPUT_BASE` instead of hardcoded `/data`
3. **LOGS_DIR** added at `$OUTPUT_BASE/logs`
4. **ANSI color block removed** — replaced with plain-text `info()`, `success()`, `warn()`, `error()` helpers
5. **All 7 upstream functions preserved**: `determine_num_files`, `should_run_datagen`, `run_datagen`, `run_benchmark`, `run_reportgen`, `run_checkpointing`, `build_extra_params_values`

**Commit:** `1a68b63`

### Task 2: Add mlperf-builder stage to Dockerfile and copy artifacts to final stage

Modified `Dockerfile` with interleaved edits to insert a new build stage and update the final stage:

**PART A — New `mlperf-builder` stage (between ltp-builder and final):**
- Python 3.12 venv at `/opt/mlpstorage-env`
- Cloned `mlcommons/storage` (v2.0) and `argonne-lcf/dlio_benchmark` (mlperf_storage_v2.0)
- Installed runtime deps: numpy, pandas, h5py, mpi4py, omegaconf, hydra-core, Pillow, PyYAML, psutil, pyarrow
- CPU-only PyTorch + torchvision (~200MB vs ~2.5GB CUDA)
- CPU TensorFlow + tfrecord + tfrecord2idx wrapper (~400MB vs 1+GB GPU)
- 3 sed patches on dlio_benchmark for optional TF/TF-IO import guards
- `pip install --no-deps` for dlio-src and mlpstorage-src

**PART B — Final stage changes:**
- Added `python3.12-venv`, `procps`, `bc` to apt-get install list
- Added 3 `COPY --from=mlperf-builder` lines for `/opt/mlpstorage-env`, `/opt/mlpstorage-src`, `/opt/dlio-src`
- Added `COPY run_model.sh /usr/local/bin/run_model.sh` with `chmod +x`
- Extended `PATH` with `:/opt/mlpstorage-env/bin`
- Set `ENV OPENBLAS_NUM_THREADS=1` and `ENV OMP_NUM_THREADS=1`

**Commit:** `a2dd83a`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed ANSI color block also removed logging function definitions**
- **Found during:** Task 1 (run_model.sh creation)
- **Issue:** The plan specified removing the ANSI color helper block (lines 44-54 of upstream), but those lines also defined the `info()`, `success()`, `warn()`, `error()` functions that the script calls throughout. Removing them would cause "command not found" errors at runtime.
- **Fix:** Added plain-text (non-ANSI) versions of all four logging functions: `info() { echo "[INFO]  $*"; }` etc.
- **Files modified:** `run_model.sh` (added 5 lines after path setup)
- **Commit:** `1a68b63`

### No Other Deviations

The Dockerfile edits (PART A and PART B) were applied exactly as specified in the plan. All verification checks passed on first attempt.

## Known Stubs

None. All variables are properly initialized and all data flows are wired through environment variables or function arguments.

## Self-Check

- [x] `run_model.sh` exists and is executable
- [x] `Dockerfile` contains `AS mlperf-builder` stage
- [x] `Dockerfile` contains 3 `COPY --from=mlperf-builder` statements
- [x] `Dockerfile` contains `COPY run_model.sh /usr/local/bin/run_model.sh`
- [x] `bash -n run_model.sh` passes syntax check
- [x] Commit `1a68b63` exists
- [x] Commit `a2dd83a` exists
