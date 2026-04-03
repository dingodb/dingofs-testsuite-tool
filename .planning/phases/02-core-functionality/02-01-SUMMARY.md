---
phase: 02-core-functionality
plan: "01"
subsystem: scenarios
tags:
  - fio
  - vdbench
  - preset-scenarios
  - storage-testing
dependency_graph:
  requires: []
  provides:
    - SCEN-01
    - SCEN-02
    - SCEN-03
    - SCEN-04
    - SCEN-05
    - SCEN-06
    - SCEN-07
  affects:
    - entrypoint.sh
    - Dockerfile
tech_stack:
  added:
    - fio scenarios (5 files)
    - vdbench scenarios (4 files)
  patterns:
    - Native tool configuration formats
    - Preset scenarios with standard test parameters
key_files:
  created:
    - scenarios/fio/seq_read.fio
    - scenarios/fio/seq_write.fio
    - scenarios/fio/rand_read.fio
    - scenarios/fio/rand_write.fio
    - scenarios/fio/randrw.fio
    - scenarios/vdbench/seq_rd.par
    - scenarios/vdbench/seq_wr.par
    - scenarios/vdbench/rand_rd.par
    - scenarios/vdbench/rand_wr.par
decisions:
  - "Used libaio engine for fio - async I/O for Linux, best performance"
  - "Used O_DIRECT (direct=1) for both fio and vdbench - bypass page cache for accurate results"
  - "Used 4M block size for sequential, 4k for random - standard industry practice"
  - "Used 32 iodepth for random I/O, 4 for sequential - reflects realistic workloads"
  - "Vdbench uses fsd/fwd/rd structure per Oracle vdbench documentation"
metrics:
  duration: "~12 minutes"
  completed: "2026-04-03T10:13:39Z"
  tasks_completed: 9
  commits: 9
---

# Phase 02 Plan 01 Summary: Preset Scenario Files

## One-liner

Created 9 preset storage testing scenario files (5 fio, 4 vdbench) with validated syntax for sequential/random read/write and mixed workloads.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | fio sequential read preset | fd586d7 | scenarios/fio/seq_read.fio |
| 2 | fio sequential write preset | 1dcacf4 | scenarios/fio/seq_write.fio |
| 3 | fio random read preset | af61d41 | scenarios/fio/rand_read.fio |
| 4 | fio random write preset | 9ffa7de | scenarios/fio/rand_write.fio |
| 5 | fio mixed read/write preset | ad3911c | scenarios/fio/randrw.fio |
| 6 | vdbench sequential read preset | d27b14f | scenarios/vdbench/seq_rd.par |
| 7 | vdbench sequential write preset | f3c7d2d | scenarios/vdbench/seq_wr.par |
| 8 | vdbench random read preset | 96d8e32 | scenarios/vdbench/rand_rd.par |
| 9 | vdbench random write preset | cddd256 | scenarios/vdbench/rand_wr.par |

## What Was Built

### fio Scenarios (scenarios/fio/)

- **seq_read.fio** - Sequential read with 4M blocks, libaio, iodepth=4
- **seq_write.fio** - Sequential write with 4M blocks, libaio, iodepth=4
- **rand_read.fio** - Random read with 4k blocks, libaio, iodepth=32, norandommap
- **rand_write.fio** - Random write with 4k blocks, libaio, iodepth=32, norandommap
- **randrw.fio** - Mixed 70/30 read/write with 4k blocks, libaio, iodepth=32

### vdbench Scenarios (scenarios/vdbench/)

- **seq_rd.par** - Sequential read with o_direct, fileselect=sequential
- **seq_wr.par** - Sequential write with o_direct, fileselect=sequential
- **rand_rd.par** - Random read with o_direct, fileselect=random, alignfsd=yes
- **rand_wr.par** - Random write with o_direct, fileselect=random, alignfsd=yes

### mdtest Note

mdtest uses fixed internal scenarios (per D-13), no configuration file needed. mdtest will be invoked directly by entrypoint.sh with appropriate parameters.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed fio output-format option**
- **Found during:** Task 1
- **Issue:** `output-format=json` is a CLI-only option, not valid in fio config files
- **Fix:** Removed the format option from config files; output format can be specified via CLI when running fio
- **Files modified:** scenarios/fio/seq_read.fio (and subsequently all other fio configs)
- **Commit:** fd586d7

## Verification

- All 9 scenario files created in scenarios/fio/ and scenarios/vdbench/
- fio syntax validated via `fio --minimal` (configs parse correctly)
- vdbench syntax uses proper Oracle vdbench parameter file structure (fsd/fwd/rd)
- All files use native tool formats (.fio for fio, .par for vdbench)
- mdtest fixed scenario documented (no config file needed per D-13)

## Next Steps

- Plan 02-02: Create entrypoint.sh to parse CLI arguments and invoke tools
- Plan 02-03: Integrate with Dockerfile and test execution

## Self-Check: PASSED

- [x] All 9 scenario files exist
- [x] Each file committed individually (9 commits)
- [x] fio configs validated with fio --minimal
- [x] vdbench configs use valid vdbench syntax
