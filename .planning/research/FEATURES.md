# Feature Research: dtt smoke Command

**Domain:** Storage test orchestration / smoke testing
**Researched:** 2026-05-19
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Single command triggers multiple tests | Core value proposion: "one command to verify storage health" | LOW | Add `smoke` as new tool type in dispatch; `smoke_run()` orchestrates other `*_run()` calls |
| Serial execution (pjdtest -> mdtest -> ltp) | Users want ordered, predictable execution; earliest failure stops later tests to avoid wasted time | LOW | Sequential function calls within `smoke_run()`; inherit `set -e` behavior from outer script |
| Output organized under smoke_ prefix directory | Users need to find smoke results separately from individual test runs | LOW | `$OUTPUT/smoke_${RUN_TIMESTAMP}/` with per-tool subdirs: `pjdtest/`, `mdtest/`, `ltp/` |
| Reuse existing per-tool execution functions | Users expect same test quality as individual runs; DRY principle | LOW | Call `pjdtest_run()`, `mdtest_run()`, `ltp_run()` internally (scoped to smoke output dirs) |
| Reuse existing config (testdir, output, image) | Configuration should not change just because tests are batched | LOW | `smoke_run()` reads same `$MOUNT`, `$OUTPUT` env vars; no new config keys needed |
| WeChat/Email notification after all tests complete | Users expect to be notified of results, consistent with existing single-test behavior | LOW | Single unified notification after all three tools run, using existing `send_wechat_notification()` and `send_email_notification()` |
| Non-zero exit code on any tool failure | Shell convention: `dtt smoke && echo "healthy"` should work | LOW | Track per-tool exit codes; return aggregate (0 only if all pass) |
| Progress display during execution | Users want to know what is happening during what could be a long run | LOW | Echo section headers between tools; timestamp each phase |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Per-tool pass/fail/skip/total statistics | Transforms smoke test from binary pass/fail into quantitative health score; enables trend tracking over time | MEDIUM | Requires parsing each tool's output format: TAP for pjdtest, LTP log format for LTP, exit code + dimensions for mdtest |
| Combined summary report (smoke_report.md) | Single glance shows overall storage health across filesystem correctness, metadata performance, and kernel syscall behavior | MEDIUM | Build markdown table with per-tool stats; can reuse `generate_report.py` patterns for markdown generation |
| Unified notification with all three tool summaries | Unlike per-test notifications (3 separate messages), one message shows the full picture; reduces notification fatigue | LOW | Construct single WeChat markdown message and single HTML email with all three tools' results in a summary table |
| Tool-level result.json for machine consumption | Enables CI/CD integration: parse smoke results for dashboards, alerting, trend analysis | MEDIUM | Write `smoke_${RUN_TIMESTAMP}/result.json` with structured per-tool pass/fail/skip/total + duration |
| Failure stops execution (fast-fail) | Don't waste time running mdtest and LTP if basic POSIX tests already fail; fastest feedback loop | LOW | `set -e` with trap to still produce partial summary report before exit |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Parallel execution of three tools | "Faster results" | All three tools write to same mount point simultaneously; pjdtest creates/removes files that mdtest or LTP could collide with; disk I/O contention invalidates mdtest performance metrics; nondeterministic results | Serial execution is the only valid approach for a storage smoke test. If speed matters, use individual `dtt` commands in separate mount points. |
| Custom tool/scenario selection for smoke | "Flexibility" | Smoke tests are by definition a fixed, known-good health check. Allowing customization makes results non-comparable across runs and defeats the purpose of "one command to know if storage is healthy." | Users needing custom combinations should use individual `dtt -t <tool>` commands sequentially. Smoke is intentionally opinionated. |
| Smoke-specific config keys | "Dedicated smoke configuration" | Fragments config, creates cognitive load ("which config applies to smoke vs individual?"), introduces config precedence bugs | Reuse existing config. If users need different mount points for smoke, they can set them before running: `dtt config set testdir /smoke-mount && dtt smoke` |
| Re-running failed tools automatically | "Resilience" | Retry logic hides flakiness. A smoke test that sometimes passes and sometimes fails is worse than one that consistently fails -- it masks real storage issues. Automatic retries create confusion about result provenance. | Report failures immediately. Users can re-run `dtt smoke` manually. For CI, the pipeline controls retry policy, not the tool. |
| Real-time streaming per-test output to notification | "Live updates" | Three WeChat messages mid-run creates notification spam. Partial results without context are misleading. Network latency of per-message sending adds overhead. | Single summary notification at end. Terminal stdout provides real-time feedback for users watching the run. |

## Feature Dependencies

```
dtt smoke command
    |---requires---> run_testsuite() in dtt wrapper         [EXISTS: dingofs-testsuite-tool]
    |---requires---> smoke_run() in entrypoint.sh            [NEW: orchestration function]
    |       |---calls---> pjdtest_run()                      [EXISTS: entrypoint.sh L1208]
    |       |---calls---> mdtest_run()                       [EXISTS: entrypoint.sh ~L1100]
    |       |---calls---> ltp_run()                          [EXISTS: entrypoint.sh L1281]
    |       |---uses----> log_result()                       [EXISTS: entrypoint.sh L656]
    |       |---uses----> send_wechat_notification()         [EXISTS: scripts/notify.sh L201]
    |       |---uses----> send_email_notification()          [EXISTS: scripts/notify.sh L25]
    |
    |---requires---> Statistics parsing                     [NEW: core differentiator]
    |       |---parses--> pjdtest TAP output                 [NEW: prove -rv produces TAP format]
    |       |---parses--> LTP result log                     [NEW: /opt/ltp/results/ files]
    |       |---counts---> mdtest exit code                  [EXISTS: mdtest_run() already does this]
    |
    |---requires---> Unified output directory                [NEW: smoke_${RUN_TIMESTAMP}/]
    |       |---contains--> pjdtest/ subdirectory
    |       |---contains--> mdtest/ subdirectory
    |       |---contains--> ltp/ subdirectory
    |       |---contains--> result.log                       [REUSES: log_result() writes here]
    |       |---contains--> result.json                      [NEW: structured summary]
    |       |---contains--> smoke_report.md                  [NEW: human-readable summary]
    |
    |---requires---> Unified notification                    [NEW: single message for all 3 tools]
            |---uses----> send_wechat_notification()         [EXISTS: but needs new aggregate format]
            |---uses----> send_email_notification()          [EXISTS: but needs new aggregate format]
```

### Dependency Notes

- **smoke_run() requires pjdtest_run(), mdtest_run(), ltp_run():** All three tool functions already exist and are fully operational. No new tool implementation needed. The orchestration function's job is to call them sequentially with smoke-specific output paths and collect their results.
- **Statistics parsing enhances smoke_run():** Without parsing, smoke only reports binary pass/fail per tool. With parsing, it reports quantitative health (e.g., "pjdtest: 94/100 passed, 2 failed, 4 skipped"). This is the core value-add of smoke over running three individual commands.
- **Unified notification depends on statistics:** A notification that just says "3/3 tools passed" is table stakes. A notification that shows pass/fail counts per tool is a differentiator.
- **result.json depends on statistics parsing:** The structured output requires parsing to populate counts.

## MVP Definition

### Launch With (v1)

Minimum viable product -- what is needed to validate the concept.

- [ ] `dtt smoke` command recognized by `dingofs-testsuite-tool` wrapper -- why essential: entry point for the feature
- [ ] `smoke_run()` function in `entrypoint.sh` that calls pjdtest, mdtest, ltp sequentially -- why essential: the orchestration itself
- [ ] Output under `$OUTPUT/smoke_${RUN_TIMESTAMP}/` with per-tool subdirectories -- why essential: organized, findable results
- [ ] Per-tool pass/fail/skip/total statistics parsed from tool outputs -- why essential: the differentiator that makes smoke valuable
- [ ] `result.log` with per-tool entries (reuses existing `log_result()`) -- why essential: audit trail
- [ ] Single unified WeChat/Email notification with summary of all three tools -- why essential: consistent with existing notification behavior
- [ ] Aggregate exit code (0 = all pass, non-zero = at least one failure) -- why essential: CI/CD integration
- [ ] Fast-fail on pjdtest failure (don't run mdtest/ltp if basic POSIX tests fail) -- why essential: fastest feedback, avoids wasted time

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] `result.json` structured output for machine consumption -- trigger: first CI/CD integration request
- [ ] `smoke_report.md` human-readable summary file -- trigger: user request for offline report sharing
- [ ] Smoke-specific summary in unified notification (pass rate, failed test names) -- trigger: after statistics parsing is solid
- [ ] Optional `--no-fast-fail` flag to run all tools regardless of failures -- trigger: user request for "run everything and give me full picture" mode

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] Historical smoke result comparison (diff against last run) -- why defer: requires persistent state storage, adds complexity
- [ ] Performance regression detection in smoke (mdtest ops/s threshold) -- why defer: mdtest is inherently variable; thresholds need calibration per environment
- [ ] Configurable smoke tool set (e.g., add fio to smoke) -- why defer: dilutes the "opinionated smoke" value proposition
- [ ] Smoke result trending dashboard -- why defer: belongs in a separate monitoring system, not the test tool itself

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| `dtt smoke` command entry point | HIGH | LOW | P1 |
| smoke_run() orchestration | HIGH | LOW | P1 |
| smoke_ output directory structure | HIGH | LOW | P1 |
| pjdtest TAP statistics parsing | HIGH | MEDIUM | P1 |
| LTP result statistics parsing | HIGH | MEDIUM | P1 |
| mdtest exit code + summary | MEDIUM | LOW | P1 |
| Unified notification (WeChat + Email) | HIGH | LOW | P1 |
| Aggregate exit code | MEDIUM | LOW | P1 |
| Fast-fail on pjdtest failure | MEDIUM | LOW | P1 |
| result.json structured output | MEDIUM | MEDIUM | P2 |
| smoke_report.md human-readable | MEDIUM | MEDIUM | P2 |
| Detailed failed test names in notification | MEDIUM | MEDIUM | P2 |
| --no-fast-fail flag | LOW | LOW | P2 |
| Historical comparison | LOW | HIGH | P3 |
| Performance regression detection | LOW | HIGH | P3 |

## Competitor Feature Analysis

No direct competitors exist in the DingoFS ecosystem -- this is the first smoke test orchestration tool. The closest analogs in the broader testing ecosystem:

| Feature | pytest | LTP runltp | Our Approach |
|---------|--------|------------|--------------|
| Multi-suite orchestration | pytest plugins / conftest | Single suite only | Built-in: 3 tools in 1 command |
| Pass/fail statistics | Built-in (verbose, summary) | LTP log parser | Parse from each tool's native output format |
| Unified output | --junit-xml, --html | Single log file | Per-tool subdirs + combined summary |
| Notification | CI plugins (external) | None built-in | Built-in WeChat + Email |
| Fast-fail | -x / --exitfirst | Not applicable (single suite) | Fail on first tool failure |

## Sources

- Codebase analysis of `entrypoint.sh` (pjdtest_run L1208, ltp_run L1281, log_result L656, notification L966-974)
- Codebase analysis of `dingofs-testsuite-tool` (run_testsuite L433, dispatch pattern L780-815)
- Codebase analysis of `scripts/notify.sh` (send_wechat_notification L201, send_email_notification L25)
- Codebase analysis of `scripts/generate_report.py` (result parsing patterns, combined report generation)
- PROJECT.md milestone definition: "一条 dtt smoke 命令自动串行执行三个测试场景，快速验证存储系统基本健康状态"

---
*Feature research for: dtt smoke command*
*Researched: 2026-05-19*
