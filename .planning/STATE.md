---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: MLPerf 工具集成
status: roadmap_created
last_updated: "2026-04-29T00:00:00.000Z"
last_activity: 2026-04-29 -- Roadmap created for v1.4
progress:
  total_phases: 2
  completed_phases: 0
  total_plans: 2
  completed_plans: 0
---

# STATE: DingoFS Storage Testsuite Tools

**Last Updated:** 2026-04-29
**Session:** v1.4 - MLPerf 工具集成

---

## Project Reference

**Core Value:** 让用户用最简单的方式执行存储性能测试 —— 一条命令即可完成测试

**Current Focus:** Roadmap defined for MLPerf 工具集成, ready for phase planning

**Project Root:** `/mnt/disk0/daigy/github/dingofs-testsuite-tool`

---

## Current Position

Phase: Not started (roadmap created)
Plan: —
Status: Roadmap created
Last activity: 2026-04-29 -- v1.4 roadmap created

```
Progress: ░░░░░░░░░░░░░░░░░░░░ 0/2 phases complete
```

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases Completed (v1.4) | 0/2 |
| Requirements Delivered (v1.4) | 0/13 |
| Days in Progress | 0 |
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
| 2-phase structure for v1.4 MLPerf | CLI (parameter parsing/help) → EXEC (container run/mounts/output); DATA reqs tightly coupled with EXEC | 2026-04-29 |
| Phase 15: CLI first | Need CLI parameters parsed before they can be passed to mlperf container | 2026-04-29 |
| DATA-01~03 merged into Phase 16 | Volume mounts and output handling are part of docker run command construction, not a separate concern | 2026-04-29 |

### Active TODOs

- [ ] Plan Phase 15: CLI 参数与帮助集成
- [ ] Plan Phase 16: MLPerf 容器执行与数据集成

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

1. Plan Phase 15: CLI 参数与帮助集成
2. Plan Phase 16: MLPerf 容器执行与数据集成

**Context for Next Session:**
v1.4 roadmap created with 2 phases covering 13 requirements. CLI phase (Phase 15) covers help text and parameter parsing in dtt wrapper. EXEC phase (Phase 16) covers mlperf-storage container launch with parameter passing, --shm-size=8g, volume mounts (testdir→/data, output→output dir), and report saving.

---

## Phase History

| Phase | Milestone | Status | Completed | Notes |
|-------|-----------|--------|-----------|-------|
| 1-4 | v1.0 | Complete | 2026-04-07 | Base image + core + output + scenarios |
| 5-7 | v1.1 | Complete | 2026-04-15 | LTP build, integration, safety |
| 8-10 | v1.2 | Complete | 2026-04-21 | Integration test command |
| 11-14 | v1.3 | Partial | - | WeChat done, Email pending |
| 15-16 | v1.4 | Not started | - | MLPerf CLI + execution |

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
**Status:** Roadmap created

**Phases:** 2 (Phase 15-16)

| Phase | Goal | Requirements |
|-------|------|-------------|
| 15. CLI 参数与帮助集成 | Users can discover and configure mlperf through CLI | CLI-01~07 (7) |
| 16. MLPerf 容器执行与数据集成 | Users can run mlperf benchmarks with proper mounts/output | EXEC-01~03, DATA-01~03 (6) |

**Target features:**

- dtt --help 中添加 mlperf 工具说明
- dtt -t mlperf --help 显示详细用法
- -s 支持 resnet50/unet3d/cosmoflow/checkpointing/all
- --scale small/medium/large，默认 small
- --file_count 自定义生成测试文件数量（优先级高于 --scale）
- --gpu_count 并发 GPU 数量，默认 1
- dtt -t mlperf 启动 mlperf-storage 容器
- --shm-size=8g 支持 PyTorch DataLoader
- 测试挂载点使用 dtt config testdir 映射到 /data
- 测试结果输出到 dtt config output

**Roadmap created:** 2026-04-29
**Coverage:** 13/13 requirements mapped to 2 phases

---

*State initialized: 2026-04-08*
*Last updated: 2026-04-29 — v1.4 roadmap created*
