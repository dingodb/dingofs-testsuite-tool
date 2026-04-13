---
phase: 04-fio-scenario-enhancements
plan: "01"
subsystem: testing
tags: [fio, scenarios, storage-testsuite]

# Dependency graph
requires:
  - phase: 02-core-functionality
    provides: entrypoint.sh, scenario files, Dockerfile base
provides:
  - 96 fio scenario files covering all parameter combinations
  - Generator script for regenerating scenarios
affects:
  - Phase 4 completion

# Tech tracking
tech-stack:
  added: [fio scenarios, bash generator script]
  patterns: [parameterized fio configuration, scenario generation]

key-files:
  created:
    - scenarios/fio/gen_fio_scenarios.sh
    - 96 new fio scenario files
  modified: []

key-decisions:
  - "Used generator script approach for 96 files (more maintainable than manual creation)"
  - "Fixed iodepth=1 for all scenarios per requirement"
  - "Used naming convention: {rw}_{direct}d_{bs}_{numjobs}j.fio"

patterns-established:
  - "Generator script creates all scenario files from parameter loops"
  - "Random scenarios include norandommap=1; sequential do not"

requirements-completed: [FIO-01, FIO-02, FIO-03, FIO-04]

# Metrics
duration: 2min
completed: 2026-04-07
---

# Phase 04-01: Fio Scenario Generation Summary

**Generated 96 fio scenario files covering all combinations of workload type, direct I/O mode, block size, and job count**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-04-07
- **Completed:** 2026-04-07
- **Tasks:** 1

## Accomplishments
- Created generator script `scenarios/fio/gen_fio_scenarios.sh`
- Generated 96 fio scenario files:
  - 24 rand_read files (2 direct × 3 bs × 4 numjobs)
  - 24 rand_write files
  - 24 seq_read files
  - 24 seq_write files
- All scenarios use iodepth=1 (fixed)
- Random scenarios include norandommap=1
- Sequential scenarios do not include norandommap

## Scenario Parameters

| Parameter | Values |
|-----------|--------|
| Workload types | rand_read, rand_write, seq_read, seq_write |
| direct | 0, 1 |
| block size | 128k, 1m, 4m |
| numjobs | 1, 8, 16, 32 |
| iodepth | 1 (fixed) |

## Files Created

- `scenarios/fio/gen_fio_scenarios.sh` - Generator script
- 96 fio scenario files in `scenarios/fio/`:
  - `rand_read_0d_128k_1j.fio` through `rand_read_1d_4m_32j.fio`
  - `rand_write_0d_128k_1j.fio` through `rand_write_1d_4m_32j.fio`
  - `seq_read_0d_128k_1j.fio` through `seq_read_1d_4m_32j.fio`
  - `seq_write_0d_128k_1j.fio` through `seq_write_1d_4m_32j.fio`

## Naming Convention

`{rw}_{direct}d_{bs}_{numjobs}j.fio`

Example: `rand_read_0d_128k_1j.fio` = rand_read, direct=0, bs=128k, numjobs=1

## Verification

All 96 files verified:
- Correct naming convention
- Correct rw, direct, bs, numjobs parameters
- iodepth=1 for all
- norandommap=1 for random scenarios only

## Next Phase Readiness

- 96 scenarios ready for use with entrypoint.sh
- User can run: `docker run myimage -t fio -s rand_read_0d_128k_1j -m /data -o /data`

---
*Phase: 04-01*
*Completed: 2026-04-07*
