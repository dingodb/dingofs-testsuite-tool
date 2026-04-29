---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: MLPerf 工具集成
status: defining_requirements
last_updated: "2026-04-29T00:00:00.000Z"
last_activity: 2026-04-29 -- Milestone v1.4 started
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# STATE: DingoFS Storage Testsuite Tools

**Last Updated:** 2026-04-29
**Session:** v1.4 - MLPerf 工具集成

---

## Project Reference

**Core Value:** 让用户用最简单的方式执行存储性能测试 —— 一条命令即可完成测试

**Current Focus:** Defining requirements for MLPerf 工具集成

**Project Root:** `/mnt/disk0/daigy/github/dingofs-testsuite-tool`

---

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-04-29 -- Milestone v1.4 started

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases Completed | 7/7 |
| Requirements Delivered | 9/9 (v1.1) |
| Days in Progress | 7 |
| Blockers | 0 |

---

## Accumulated Context

### Decisions Made

| Decision | Rationale | Date |
|----------|-----------|------|
| 3-phase structure | Natural clustering: foundation → functionality → output | 2026-04-03 |
| Phase 2 groups parameters, scenarios, run modes | All needed together to run tests | 2026-04-03 |
| Phase 3 focuses on output formats | Enhances value after core functionality works | 2026-04-03 |
| Phase 5: LTP Build Setup | Dockerfile multi-stage build for LTP | 2026-04-08 |
| Phase 6: LTP Integration | entrypoint.sh changes, ltp_run function | 2026-04-08 |
| Phase 7: LTP Runtime Safety | timeout, output logging, capability docs | 2026-04-08 |

### Active TODOs

- [ ] Plan Phase 5: LTP Build Setup

### Blockers

(None)

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260413-m3k | Support multiple mdsaddr addresses (comma-separated) | 2026-04-13 | - | [260413-m3k-support-multiple-mdsaddr-addresses-comma](./quick/260413-m3k-support-multiple-mdsaddr-addresses-comma/) |
| 260421-d32 | Add --help support for each tool and change -s mdtest/ltp defaults to -s all | 2026-04-21 | 9e85c7e | [260421-d32-add-help-support-for-each-tool-in-wrappe](./quick/260421-d32-add-help-support-for-each-tool-in-wrappe/) |
| 260421-dvj | Organize output into tool-specific subdirectories | 2026-04-21 | 769ad97 | [260421-dvj-organize-output-into-tool-specific-subdi](./quick/260421-dvj-organize-output-into-tool-specific-subdi/) |
| 260424-b84 | Fix BS_SIZE=small path and filesize (400M) | 2026-04-24 | - | [260424-b84-fix-bs-size-small-path-and-size](./quick/260424-b84-fix-bs-size-small-path-and-size/) |
| 260424-kv8 | Reorganize fio scenarios into /scenarios/fio/bs_normal and bs_small | 2026-04-24 | 505ca27 | [260424-kv8-reorganize-fio-scenarios-into-scenarios-](./quick/260424-kv8-reorganize-fio-scenarios-into-scenarios-/) |
| 260428-fay | Add container runtime config option (docker/podman) to dtt | 2026-04-28 | cea0db6 | [260428-fay-add-container-runtime-config-option-dock](./quick/260428-fay-add-container-runtime-config-option-dock/) |

### Key Files

- `.planning/PROJECT.md` - Project context
- `.planning/REQUIREMENTS.md` - Requirements definition
- `.planning/ROADMAP.md` - Phase roadmap
- `.planning/config.json` - Configuration

---

## Session Continuity

**Last Session:** 2026-04-29T00:00:00.000Z

**Next Actions:**

1. Define requirements for v1.4 MLPerf milestone
2. Create roadmap for v1.4

**Context for Next Session:**
v1.4 milestone started. Integrating existing mlperf-storage:latest Docker image into dtt tool. 4 workloads + checkpointing, scale/file_count/gpu_count parameters.

---

## Phase History

| Phase | Milestone | Status | Completed | Notes |
|-------|-----------|--------|-----------|-------|
| 1-4 | v1.0 | Complete | 2026-04-07 | Base image + core + output + scenarios |
| 5-7 | v1.1 | Complete | 2026-04-15 | LTP build, integration, safety |
| 8-10 | v1.2 | Complete | 2026-04-21 | Integration test command |
| 11-14 | v1.3 | Partial | - | WeChat done, Email pending |

---

## v1.1 Milestone: 新增 LTP 工具

**Started:** 2026-04-08
**Completed:** 2026-04-15

**Target features:**

- Install LTP toolset in Docker image (Phase 5) ✓
- Add ltp run command with filesystem tests by default (Phase 6) ✓
- Support LTP test results output to specified directory (Phase 7) ✓
- Timeout protection and capability documentation (Phase 7) ✓

**Roadmap created:** 2026-04-08
**Coverage:** 9/9 requirements mapped to 3 phases

---

## v1.2 Milestone: 集成测试命令

**Started:** 2026-04-21
**Completed:** 2026-04-21

**Target features:**

- Add -t int command support (Phase 8) ✓
- Pass MDSADDR from dtt config to framework (Phase 9) ✓
- Parse and save integration test results (Phase 10) ✓

**Roadmap created:** 2026-04-21
**Coverage:** 8/8 requirements mapped to 3 phases

---

## v1.3 Milestone: 测试结果通知

**Started:** 2026-04-21
**Status:** Partially complete — WeChat done, Email pending

**Target features:**

- Add --wechat and --email CLI flags (Phase 11) ✓
- WeChat webhook notification with markdown_v2 (Phase 12) ✓
- Email notification via SMTP Outlook (Phase 13) — Pending
- Extend to all tools (Phase 14) ✓

**Roadmap created:** 2026-04-21
**Coverage:** 17/17 requirements mapped to 4 phases

---

## v1.4 Milestone: MLPerf 工具集成

**Started:** 2026-04-29
**Status:** Defining requirements

**Target features:**

- 添加 dtt -t mlperf 命令支持
- -s 支持 resnet50/unet3d/cosmoflow/checkpointing/all
- --scale small/medium/large，默认 small
- --file_count 自定义生成测试文件数量（优先级高于 --scale）
- --gpu_count 并发 GPU 数量，默认 1
- 测试挂载点使用 dtt config testdir
- 测试结果输出到 dtt config output

---

*State initialized: 2026-04-08*
*Last updated: 2026-04-29 — v1.4 started*
