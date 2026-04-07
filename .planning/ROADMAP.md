# Roadmap: DingoFS Storage Benchmark Tools

**Project:** DingoFS Storage Benchmark Tools
**Core Value:** 让用户用最简单的方式执行存储性能测试 —— 一条命令即可完成测试
**Created:** 2026-04-03
**Granularity:** Standard

## Overview

This roadmap delivers a Docker-based storage performance testing toolkit with fio, vdbench, and mdtest tools. The project evolves from a basic Docker image to a fully functional testing platform with multiple output formats.

## Phases

- [ ] **Phase 1: Docker Image Construction** - Build base image with all testing tools installed
- [x] **Phase 2: Core Functionality** - Enable test execution with parameters, scenarios, and run modes (completed 2026-04-03)
- [ ] **Phase 3: Output Formats** - Provide multiple report formats for test results
- [ ] **Phase 4: Fio Scenario Enhancements** - Add more fio scenarios for comprehensive testing

## Phase Details

### Phase 1: Docker Image Construction

**Goal:** Users have a working Docker image with all required storage testing tools installed and ready to use.

**Depends on:** Nothing (first phase)

**Requirements:** DOCK-01, DOCK-02, DOCK-03, DOCK-04, DOCK-05

**Success Criteria** (what must be TRUE):
  1. User can build Docker image from Dockerfile without errors
  2. User can verify fio is installed by running `fio --version` inside container
  3. User can verify vdbench is installed and executable inside container
  4. User can verify mdtest is installed by running `mdtest --version` inside container
  5. Image size is optimized (no unnecessary packages or cache files remain)

**Plans:** 1/1 plan complete

Plans:
- [x] 01-01-PLAN.md — Create Dockerfile and verify all storage testing tools

---

### Phase 2: Core Functionality

**Goal:** Users can execute storage performance tests using various tools, scenarios, and parameters through command line or configuration files.

**Depends on:** Phase 1

**Requirements:** PARM-01, PARM-02, PARM-03, PARM-04, PARM-05, PARM-06, SCEN-01, SCEN-02, SCEN-03, SCEN-04, SCEN-05, SCEN-06, SCEN-07, MODE-01, MODE-02, MODE-03, ENTRY-01, ENTRY-02, ENTRY-04

**Success Criteria** (what must be TRUE):
  1. User can run a test by specifying tool name via command line (e.g., `docker run myimage --tool fio`)
  2. User can run a test by mounting a configuration file with all parameters
  3. User can execute fio sequential read/write test and see results
  4. User can execute vdbench random read/write test and see results
  5. User can run one-shot test mode where container exits after test completion
  6. User can run long-running container and trigger tests via `docker exec`

**Plans:** 3/3 plans complete

Plans:
- [x] 02-01-PLAN.md — Create fio and vdbench preset scenario files
- [x] 02-02-PLAN.md — Create entrypoint.sh with CLI parsing and mode handling
- [x] 02-03-PLAN.md — Update Dockerfile with scenarios and entrypoint

---

### Phase 3: Output Formats

**Goal:** Users receive test results in multiple useful formats suitable for different consumption needs.

**Depends on:** Phase 2

**Requirements:** OUTP-01, OUTP-02, OUTP-03, OUTP-04, ENTRY-03

**Success Criteria** (what must be TRUE):
  1. User can view raw tool output after test completion
  2. User can get structured JSON report with parsed test results
  3. User can get HTML report with visualized test metrics
  4. User can see text summary highlighting key performance indicators

**Plans:** 2/2 plans complete

Plans:
- [x] 03-01-PLAN.md — Create report generation script and update Dockerfile
- [x] 03-02-PLAN.md — Integrate report generation into entrypoint.sh

---

### Phase 4: Fio Scenario Enhancements

**Goal:** Add more fio test scenarios to cover mixed workloads, different block sizes, and queue depths for comprehensive storage testing.

**Depends on:** Phase 2

**Requirements:** FIO-01, FIO-02, FIO-03, FIO-04, FIO-05

**Success Criteria** (what must be TRUE):
  1. User can run mixed read/write workloads (e.g., 70/30, 50/50 read/write ratios)
  2. User can test different block sizes (4k, 8k, 64k, 128k, 1m)
  3. User can specify iodepth for queue depth testing
  4. User can run steady-state performance tests with longer runtime
  5. New scenarios follow existing naming convention and directory structure

**Plans:** 1/1 plan complete

Plans:
- [x] 04-01-PLAN.md — Add new fio scenarios (mixed rw, block size, iodepth)

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Docker Image Construction | 1/1 | Complete | 2026-04-03 |
| 2. Core Functionality | 3/3 | Complete   | 2026-04-03 |
| 3. Output Formats | 2/2 | Complete | 2026-04-07 |
| 4. Fio Scenario Enhancements | 0/1 | Pending |  |

## Coverage

- v1 Requirements: 34 total
- Mapped to phases: 34
- Unmapped: 0

| Requirement | Phase | Status |
|-------------|-------|--------|
| DOCK-01 | Phase 1 | Complete |
| DOCK-02 | Phase 1 | Complete |
| DOCK-03 | Phase 1 | Complete |
| DOCK-04 | Phase 1 | Complete |
| DOCK-05 | Phase 1 | Complete |
| PARM-01 | Phase 2 | Pending |
| PARM-02 | Phase 2 | Pending |
| PARM-03 | Phase 2 | Pending |
| PARM-04 | Phase 2 | Pending |
| PARM-05 | Phase 2 | Pending |
| PARM-06 | Phase 2 | Pending |
| SCEN-01 | Phase 2 | Complete |
| SCEN-02 | Phase 2 | Complete |
| SCEN-03 | Phase 2 | Complete |
| SCEN-04 | Phase 2 | Complete |
| SCEN-05 | Phase 2 | Complete |
| SCEN-06 | Phase 2 | Complete |
| SCEN-07 | Phase 2 | Complete |
| MODE-01 | Phase 2 | Pending |
| MODE-02 | Phase 2 | Pending |
| MODE-03 | Phase 2 | Pending |
| ENTRY-01 | Phase 2 | Complete |
| ENTRY-02 | Phase 2 | Complete |
| ENTRY-04 | Phase 2 | Complete |
| OUTP-01 | Phase 3 | Complete |
| OUTP-02 | Phase 3 | Complete |
| OUTP-03 | Phase 3 | Complete |
| OUTP-04 | Phase 3 | Complete |
| ENTRY-03 | Phase 3 | Complete |
| FIO-01 | Phase 4 | Pending |
| FIO-02 | Phase 4 | Pending |
| FIO-03 | Phase 4 | Pending |
| FIO-04 | Phase 4 | Pending |
| FIO-05 | Phase 4 | Pending |

---

*Roadmap created: 2026-04-03*
*Last updated: 2026-04-07*
