# Roadmap: DingoFS Storage Testsuite Tools

**Project:** DingoFS Storage Testsuite Tools
**Core Value:** 让用户用最简单的方式执行存储性能测试 —— 一条命令即可完成测试
**Created:** 2026-04-03
**Granularity:** Standard

## Overview

This roadmap delivers a Docker-based storage performance testing toolkit with fio, vdbench, mdtest, and LTP tools. The project evolves from a basic Docker image to a fully functional testing platform with multiple output formats.

## Phases

- [ ] **Phase 1: Docker Image Construction** - Build base image with all testing tools installed
- [x] **Phase 2: Core Functionality** - Enable test execution with parameters, scenarios, and run modes (completed 2026-04-03)
- [ ] **Phase 3: Output Formats** - Provide multiple report formats for test results
- [ ] **Phase 4: Fio Scenario Enhancements** - Add more fio scenarios for comprehensive testing
- [ ] **Phase 5: LTP Build Setup** - Multi-stage Docker build for LTP toolset
- [ ] **Phase 6: LTP Integration** - Integrate LTP into entrypoint.sh with ltp_run function
- [ ] **Phase 7: LTP Runtime Safety** - Timeout wrappers, output logging, and capability documentation

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

**Goal:** Add comprehensive fio test scenarios covering all combinations of workload type, direct I/O mode, block size, and job count for thorough storage performance testing.

**Depends on:** Phase 2

**Requirements:** FIO-01, FIO-02, FIO-03, FIO-04

**Success Criteria** (what must be TRUE):
  1. User can run all four workload types: rand_read, rand_write, seq_read, seq_write
  2. User can test with both direct=0 (buffered I/O) and direct=1 (direct I/O)
  3. User can test different block sizes: 128K, 1M, 4M
  4. User can test with different job counts: 1, 8, 16, 32
  5. Each scenario uses iodepth=1 for consistent single-queue-depth testing
  6. Total: 4 types × 2 direct × 3 bs × 4 numjobs = 96 scenarios
  7. Naming convention: {rw}_{direct}d_{bs}_{numjobs}j.fio

**Plans:** 1/1 plan complete

Plans:
- [x] 04-01-PLAN.md — Generate 96 fio scenario files (4 types × 2 direct × 3 bs × 4 numjobs)

---

### Phase 5: LTP Build Setup

**Goal:** Users have a Docker image with LTP toolset installed via multi-stage build, supporting both x86_64 and ARM64 platforms.

**Depends on:** Phase 1

**Requirements:** LTP-01, LTP-02, LTP-03

**Success Criteria** (what must be TRUE):
  1. User can build Docker image with LTP toolset without errors
  2. User can verify LTP is installed by running `ltp-01 --version` or seeing the tool available
  3. Final image uses multi-stage build with build stage for compilation
  4. User can build and run on x86_64 platform
  5. User can build and run on ARM64 platform

**Plans:** TBD

---

### Phase 6: LTP Integration

**Goal:** Users can execute LTP filesystem tests via `-t ltp` command line parameter, with `ltp_run()` function defaulting to filesystem test suite.

**Depends on:** Phase 5

**Requirements:** LTP-04, LTP-05, LTP-06

**Success Criteria** (what must be TRUE):
  1. User can specify `-t ltp` and container recognizes LTP as a valid tool option
  2. User can run `ltp_run()` function which executes the LTP test suite
  3. User can run LTP with default filesystem tests via `-f fs` flag
  4. User can see LTP test output displayed in container logs

**Plans:** TBD

---

### Phase 7: LTP Runtime Safety

**Goal:** LTP tests execute safely with timeout protection, output is logged to user-specified directory, and container capability requirements are documented.

**Depends on:** Phase 6

**Requirements:** LTP-07, LTP-08, LTP-09

**Success Criteria** (what must be TRUE):
  1. User can run LTP tests without risk of indefinite hanging (timeout wrapper active)
  2. User can specify output directory and see LTP results written there
  3. User can find documentation explaining required container capabilities (CAP_SYS_ADMIN)
  4. User understands that privileged container or specific capabilities are needed for LTP tests

**Plans:** TBD

---

## v1.2: 集成测试命令

### Phase 8: 集成测试基础
**Goal:** Users can run integration tests via `-t integration` command.

**Depends on:** Phase 1

**Requirements:** INTG-01, AUTO-01

**Success Criteria** (what must be TRUE):
1. User can specify `-t int` and container recognizes it as a valid tool
2. `integration_run()` function exists and can be called
3. dingofs-integration-test exists in the image at /dingofs-integration-test
4. `dtt -t int --help` displays help information

---

### Phase 9: 参数传递与执行
**Goal:** MDS address is passed from `dtt config` to the automation framework, and tests execute successfully.

**Depends on:** Phase 8

**Requirements:** INTG-02, INTG-03, AUTO-02

**Success Criteria** (what must be TRUE):
1. MDSADDR is read from `dtt config mdsaddr` and passed to container
2. Automation framework executes tests successfully
3. Environment variables are correctly passed to the automation framework

---

### Phase 10: 结果解析与保存
**Goal:** Automation framework test results are parsed and saved to the output directory.

**Depends on:** Phase 9

**Requirements:** INTG-04, INTG-05, AUTO-03

**Success Criteria** (what must be TRUE):
1. Automation framework output is parsed to identify success/failure
2. Results are saved to `$OUTPUT/integration/` directory
3. result.log correctly records integration test results

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Docker Image Construction | 1/1 | Complete | 2026-04-03 |
| 2. Core Functionality | 3/3 | Complete   | 2026-04-03 |
| 3. Output Formats | 2/2 | Complete | 2026-04-07 |
| 4. Fio Scenario Enhancements | 1/1 | Complete | 2026-04-07 |
| 5. LTP Build Setup | 1/1 | Complete | 2026-04-15 |
| 6. LTP Integration | 1/1 | Complete | 2026-04-15 |
| 7. LTP Runtime Safety | 1/1 | Complete | 2026-04-15 |
| 8. 集成测试基础 | 0/1 | Pending | — |
| 9. 参数传递与执行 | 0/1 | Pending | — |
| 10. 结果解析与保存 | 0/1 | Pending | — |

## Coverage

- v1.2 Requirements: 8 total (INTG-01~05, AUTO-01~03)
- v1.1 Requirements: 9 total (LTP-01~09)
- v1.0 Requirements: 34 total
- Mapped to phases: All ✓

| Requirement | Phase | Status |
|-------------|-------|--------|
| INTG-01 | Phase 8 | Pending |
| AUTO-01 | Phase 8 | Pending |
| INTG-02 | Phase 9 | Pending |
| INTG-03 | Phase 9 | Pending |
| AUTO-02 | Phase 9 | Pending |
| INTG-04 | Phase 10 | Pending |
| INTG-05 | Phase 10 | Pending |
| AUTO-03 | Phase 10 | Pending |
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
| FIO-01 | Phase 4 | Complete |
| FIO-02 | Phase 4 | Complete |
| FIO-03 | Phase 4 | Complete |
| FIO-04 | Phase 4 | Complete |
| LTP-01 | Phase 5 | Pending |
| LTP-02 | Phase 5 | Pending |
| LTP-03 | Phase 5 | Pending |
| LTP-04 | Phase 6 | Pending |
| LTP-05 | Phase 6 | Pending |
| LTP-06 | Phase 6 | Pending |
| LTP-07 | Phase 7 | Pending |
| LTP-08 | Phase 7 | Pending |
| LTP-09 | Phase 7 | Pending |

---

*Roadmap created: 2026-04-03*
*Last updated: 2026-04-21 for v1.2*
