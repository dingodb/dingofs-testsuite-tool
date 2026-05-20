---
phase: 18-result-statistics-summary
plan: 01
subsystem: smoke-test-orchestration
tags: [smoke, statistics, TAP-parsing, LTP-parsing, mdtest-validation, summary-report]
requires: []
provides: [parse_pjdtest_tap, parse_ltp_output, validate_mdtest_smoke, generate_smoke_summary]
affects: [smoke_run]
tech-stack:
  added: []
  patterns: 
    - "bash function composition (no function keyword, name+parens+brace)"
    - "global variable export pattern (SMOKE_PJD_*, SMOKE_LTP_*, SMOKE_MDT_*)"
    - "heredoc with cat for JSON/text file generation"
    - "line-anchored grep -cE for TAP and LTP output parsing"
key-files:
  created: []
  modified: [entrypoint.sh]
decisions:
  - "TAP skip counting: TODO directives counted as skip, fail = not_ok - skip"
  - "LTP space-anchored patterns: [[:space:]]TPASS: prevents matching inside test names"
  - "LTP TBROK counts as FAIL, TCONF counts as SKIP"
  - "mdtest validation uses three conditions: exit=0, SUMMARY rate present, non-zero ops"
  - "smoke_summary.json heredoc with bash interpolation for status strings and counts"
metrics:
  duration: "9m 55s"
  completed_date: "2026-05-20"
---

# Phase 18 Plan 01: Result Statistics & Summary

**One-liner:** Added four bash parsing/summary functions to entrypoint.sh that transform smoke_run() from exit-code-only reporting into a comprehensive statistics system with JSON and text summary reports.

## What was built

Three TAP/LTP/mdtest parsing functions and a summary generation function, all integrated into the existing `smoke_run()` orchestration:

1. **`parse_pjdtest_tap()`** (STAT-01): Parses pjdtest TAP output using line-anchored regex. Counts `^ok` lines as pass, `^not ok.*#.*TODO` as skip, and derives fail = total_not_ok - skip. Sets `SMOKE_PJD_PASS`, `SMOKE_PJD_FAIL`, `SMOKE_PJD_SKIP`, `SMOKE_PJD_TOTAL`.

2. **`parse_ltp_output()`** (STAT-02): Parses LTP `*_smoketest.raw` files using space-anchored patterns (`[[:space:]]TPASS:`, `[[:space:]]TFAIL:`, `[[:space:]]TBROK:`, `[[:space:]]TCONF:`). TBROK counts as FAIL. Detects timeout when exit code is 124. Sets `SMOKE_LTP_PASS`, `SMOKE_LTP_FAIL`, `SMOKE_LTP_SKIP`, `SMOKE_LTP_TOTAL`, `SMOKE_LTP_TIMEOUT`.

3. **`validate_mdtest_smoke()`** (STAT-03): Validates mdtest results using three conditions: exit code is 0, SUMMARY rate line is present, and operation counts (File creation, File stat, File removal) are non-zero. Sets `SMOKE_MDT_PASS` (1 or 0).

4. **`generate_smoke_summary()`** (STAT-04): Reads all global SMOKE_* variables and writes `smoke_summary.json` (machine-readable) and `smoke_summary.txt` (human-readable) to the smoke output directory. JSON includes per-tool pass/fail/skip/total with status strings. Text output uses `====` banner separators.

**Integration into `smoke_run()`:** All four functions are wired at the correct integration points:
- `parse_pjdtest_tap` called after `pjdtest_run` completes
- `validate_mdtest_smoke` called after `mdtest_run` completes  
- `parse_ltp_output` called after `ltp_run` completes
- `generate_smoke_summary` called after all tools complete and `SMOKE_MODE` is unset

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | d6c2ed5 | feat(18-result-statistics-summary): add parse_pjdtest_tap() function for TAP output parsing |
| 2 | ae16965 | feat(18-result-statistics-summary): add parse_ltp_output() and validate_mdtest_smoke() functions |
| 3 | 52a353a | feat(18-result-statistics-summary): add generate_smoke_summary() and wire all parse functions into smoke_run() |

## Files Modified

- `entrypoint.sh` — 4 new functions + 5 integration call sites in `smoke_run()`

## Verification Results

| Check | Result |
|-------|--------|
| `bash -n entrypoint.sh` syntax | PASS |
| All 4 functions exist | PASS (parse_pjdtest_tap, parse_ltp_output, validate_mdtest_smoke, generate_smoke_summary) |
| Functions ordered correctly | PASS (all 4 before smoke_run) |
| TAP regex: `^ok[[:space:]]+[0-9]+` (pass) | PASS |
| TAP regex: `^not[[:space:]]+ok[[:space:]]+[0-9]+.*#.*TODO` (skip) | PASS |
| LTP regex: `[[:space:]]TPASS:` (space-anchored) | PASS |
| LTP timeout detection (exit 124) | PASS |
| mdtest three-condition validation | PASS |
| JSON keys: smoke_timestamp, tools.*, aggregate | PASS |
| Text output with `====` banners | PASS |
| All 4 functions called from smoke_run() | PASS |
| Final summary with per-tool statistics | PASS |
| set +e/set -e blocks preserved (6 toggles) | PASS |
| SMOKE_MODE export/unset logic preserved | PASS |
| No forbidden calls (exit, log_result, send_wechat, send_email) in new functions | PASS |

## Requirements Delivered

- **STAT-01**: parse_pjdtest_tap() - TAP pass/fail/skip/total counting
- **STAT-02**: parse_ltp_output() - LTP TPASS/TFAIL/TCONF counting with timeout detection
- **STAT-03**: validate_mdtest_smoke() - Three-condition mdtest pass/fail validation
- **STAT-04**: generate_smoke_summary() - Combined JSON + text summary reports

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all functions are fully implemented with complete logic.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| TAP skip counting: TODO directives counted as skip, fail = not_ok - skip | PJDTEST uses `# TODO` comment convention for expected failures |
| LTP space-anchored patterns: `[[:space:]]TPASS:` | Prevents matching TPASS inside test case names/descriptions |
| LTP TBROK counts as FAIL, TCONF counts as SKIP | TBROK = test infrastructure broken (failure), TCONF = test not configured (skipped) |
| mdtest validation uses three conditions | Prevents false PASS for broken filesystems (exit=0 but zero operations) |
| smoke_summary.json heredoc with bash interpolation | Simpler than printf/jq; no additional dependencies |

---

*Plan completed: 2026-05-20*
