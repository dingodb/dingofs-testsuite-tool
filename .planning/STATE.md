---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: 冒烟测试命令
status: roadmap_created
last_updated: "2026-05-20T00:00:00Z"
last_activity: 2026-05-20
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# STATE: DingoFS Storage Testsuite Tools

**Last Updated:** 2026-05-20
**Session:** v1.5 -- 冒烟测试命令

---

## Project Reference

**Core Value:** 让用户用最简单的方式执行存储性能测试 -- 一条命令即可完成测试

**Current Focus:** Phase 17 -- Smoke Orchestration Core (ready to plan)

**Project Root:** `/mnt/disk5/daigy/dingofs-testsuite-tool`

---

## Current Position

Phase: 17 of 19 (Smoke Orchestration Core)
Plan: --
Status: Roadmap created -- ready to plan Phase 17
Last activity: 2026-05-20 -- Roadmap created for v1.5 (Phases 17-19)

```
Progress: ░░░░░░░░░░░░░░░░░░░░ 0/3 phases complete (v1.5)
```

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases Completed (v1.5) | 0/3 |
| Requirements Delivered (v1.5) | 0/9 |
| Days in Progress | 0 |
| Blockers | 0 |

---

## Accumulated Context

### Decisions Made

| Decision | Rationale | Date |
|----------|-----------|------|
| 3-phase structure for v1.5 | 3 natural clusters (orchestration -> statistics -> CLI/notification); Phase 4 (Polish) from research has zero v1.5 requirements | 2026-05-20 |
| Phase 17: Container-first | SMOKE_MODE guards must exist before smoke_run() can call existing _run() functions without notification side effects | 2026-05-20 |
| Phase 18: Statistics after orchestration | Cannot parse results until smoke_run() produces output; parsing functions need real output files | 2026-05-20 |
| Phase 19: CLI last | Wrapper cmd_smoke() + combined notification depends on container fully supporting -t smoke | 2026-05-20 |
| Single-container hybrid architecture | Avoids 3-container overhead, enables in-memory stats aggregation, prevents per-tool notification spam | 2026-05-20 |
| SMOKE_MODE guard pattern | Wrap notification blocks in `if [[ "$SMOKE_MODE" != "1" ]]` in 3 existing _run() functions (2 lines each, 6 total) | 2026-05-20 |

### Active TODOs

- [ ] Plan Phase 17: Smoke Orchestration Core
- [ ] Plan Phase 18: Result Statistics & Summary
- [ ] Plan Phase 19: CLI & Notification

### Blockers

(None)

### Key Files

- `.planning/PROJECT.md` - Project context (v1.5 milestone definition)
- `.planning/REQUIREMENTS.md` - Requirements (9 v1.5 requirements)
- `.planning/ROADMAP.md` - Phase roadmap (Phases 17-19)
- `.planning/research/SUMMARY.md` - Research synthesis (Option C: single-container hybrid)
- `dingofs-testsuite-tool` - Host-side CLI wrapper (Phase 19 target)
- `entrypoint.sh` - Container entrypoint (Phase 17-18 target)
- `scripts/notify.sh` - WeChat/Email notification primitives (unchanged, reused by Phase 19)

---

## Session Continuity

**Last Session:** 2026-05-20 -- Roadmap creation

**Next Actions:**

1. `/gsd:plan-phase 17` -- Plan Smoke Orchestration Core (SMOKE_MODE guards + smoke_run + dispatch)

**Context for Next Session:**
v1.5 roadmap created with 3 phases covering 9 requirements. Phase 17 (Smoke Orchestration Core) is the first phase: SMOKE_MODE guards in 3 existing _run() functions, new smoke_run() function, dispatch wiring in entrypoint.sh, fail-continue with set +e/set -e, unified smoke_<timestamp>/ output directory with per-tool subdirectories. Research confidence is HIGH for this phase -- pure bash function composition inside existing framework.

---

## Phase History

| Phase | Milestone | Status | Completed | Notes |
|-------|-----------|--------|-----------|-------|
| 1-4 | v1.0 | Complete | 2026-04-07 | Base image + core + output + scenarios |
| 5-7 | v1.1 | Complete | 2026-04-15 | LTP build, integration, safety |
| 8-10 | v1.2 | Complete | 2026-04-21 | Integration test command |
| 11-14 | v1.3 | Partial | - | WeChat done, Email pending |
| 15-16 | v1.4 | Complete | 2026-04-29 | MLPerf CLI + execution |
| 17-19 | v1.5 | Not started | - | Smoke orchestration + stats + CLI/notification |

---

## v1.5 Milestone: 冒烟测试命令

**Started:** 2026-05-20
**Status:** Roadmap created

**Phases:** 3 (Phase 17-19)

| Phase | Goal | Requirements |
|-------|------|-------------|
| 17. Smoke Orchestration Core | Container executes 3 smoke tools in sequence with unified output and fail-continue | SMOKE-01, SMOKE-02, OUT-01 (3) |
| 18. Result Statistics & Summary | Per-tool pass/fail/skip/total parsed from outputs with combined summary | STAT-01~04 (4) |
| 19. CLI & Notification | dtt smoke from host CLI with help + single combined WeChat/Email notification | SMOKE-03, OUT-02 (2) |

**Target features:**

- dtt smoke command -- single command runs pjdtest, mdtest, ltp in sequence
- Fail-continue: one tool failing does not abort subsequent tools
- Per-tool statistics: pass/fail/skip/total counts from TAP, LTP log, mdtest output
- Unified output: smoke_<timestamp>/ with per-tool subdirectories
- Combined notification: single WeChat/Email message with all three tools' results

**Roadmap created:** 2026-05-20
**Coverage:** 9/9 requirements mapped to 3 phases

---

*State initialized: 2026-04-08*
*Last updated: 2026-05-20 -- v1.5 roadmap created*
