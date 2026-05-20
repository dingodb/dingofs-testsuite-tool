# Stack Research: dtt smoke Subcommand

**Domain:** Bash-based storage test orchestration (addition to existing DingoFS Testsuite Tools)
**Researched:** 2026-05-19
**Confidence:** HIGH

## Recommended Stack

### Core Technologies (unchanged from existing stack)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Bash | 5.x (Ubuntu 24.04) | Wrapper script language, result parsing, orchestration | Already in use. No new runtime needed. Adequate for sequential test orchestration and text parsing. |
| Docker / Podman | latest | Container runtime | Already abstracted via `runtime` config key. `dtt smoke` reuses existing `run_testsuite()` to launch individual tool containers. |
| `dingofs-testsuite-tool` (bash) | existing | CLI wrapper | `cmd_smoke()` added as new function with `smoke` case in main dispatch. |
| `entrypoint.sh` (bash) | existing | In-container test runner | No changes needed with host-side orchestration approach. Existing `pjdtest_run()`, `mdtest_run()`, `ltp_run()` used as-is. |
| `scripts/notify.sh` (bash) | existing | WeChat + Email notification | No changes needed. Existing `send_wechat_notification()` and `send_email_notification()` accept tool/duration/details args -- smoke passes combined summary. |

### Supporting Tools (no new installs)

| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| `grep`, `awk`, `sed` | system (POSIX) | Text parsing for TAP output (pjdtest) and LTP log summary | Core parsing toolkit for result extraction. No additional packages. |
| `prove` (Perl Test::Harness) | system (Ubuntu 24.04) | Runs pjdtest, generates TAP-format summary footer | Already invoked by `pjdtest_run()`. Smoke reads its output file. |
| `runltp` (LTP) | existing in image | Runs LTP, generates structured log with summary table | Already invoked by `ltp_run()`. Smoke reads the `-l` log file. |
| `mdtest` (MPI binary) | existing in image | Metadata performance benchmark | Already invoked by `mdtest_run()`. Smoke runs it with `-n 8`. |
| `printf` / `echo` | system | Writing `smoke_summary.txt` | Standard bash output. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| shellcheck | Static analysis for bash scripts | Run on `dingofs-testsuite-tool` after adding `cmd_smoke()`. Catches quoting issues and unused variables. |
| bats-core (optional) | Bash unit testing | Could test `parse_pjdtest_results` and `parse_ltp_results` in isolation with sample output fixtures. Not required for v1. |

## Installation

Zero new packages. The `smoke` subcommand is pure bash added to one existing file:

```bash
# dingofs-testsuite-tool (host-side wrapper -- the ONLY file changed)
# Add: cmd_smoke() function (80-120 lines)
# Add: "smoke" case to main dingofs-testsuite-tool() dispatch
# Add: smoke usage to show_help()
```

No Dockerfile changes. No new container image. No new scripts.

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| Host-side orchestration: `cmd_smoke()` in dtt wrapper calls `run_testsuite()` 3 times (3 containers) | In-container orchestration: `smoke_run()` in entrypoint.sh calls `pjdtest_run/mdtest_run/ltp_run` in sequence (1 container) | In-container approach requires significant entrypoint.sh changes, cannot guarantee clean environment between tools, harder to isolate per-tool output directories. Host-side reuses existing run_testsuite verbatim. |
| Pure bash `grep`/`awk` parsing of TAP and LTP output | Python script (e.g., `scripts/parse_results.py`) | Adds runtime dependency. Parsing is simple line-oriented text matching -- awk is more than sufficient. |
| Parse pjdtest per-assertion TAP lines (`ok`/`not ok`) for counts | Parse `prove` summary footer only (`Result: PASS`, `Files=N, Tests=N`) | Both are useful. Use `prove` footer for aggregated totals (handles SKIP/TODO correctly) and TAP line counting for per-test detail when needed. |
| Parse LTP `<<<test_start>>>/<<<test_end>>>` blocks per-test | Parse LTP summary table at end of log | Summary table (`Total Tests: N`, `Total Failures: N`, `Total Skipped Tests: N`) is simpler and sufficient for smoke. Per-test block parsing only needed for listing individual failed test names. |
| New `smoke` config key for output prefix | Reuse existing `output` config key + append `smoke_` prefix | No new config needed. The smoke output directory is deterministic: `${OUTPUT}/smoke_${TIMESTAMP}`. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Python / Ruby / Perl for result parsing | Adds runtime dependency to a bash-only codebase. Parsing is simple text extraction. | bash builtins + awk + grep |
| `jq` for structured output | Adds dependency. Output is consumed by humans and notification templates, not machine interfaces. | Plain text + the existing notify.sh markdown templates. |
| New dedicated `smoke.sh` script file | Creates file fragmentation. A single function in the existing wrapper is cleaner and easier to maintain. | `cmd_smoke()` function inside `dingofs-testsuite-tool`. |
| New `SMOKE_` config keys | Unnecessary complexity. Reuse existing `testdir`, `output`, `image`, `webhook_url`, `email`, `runtime` config keys. | `dtt config set` keys already in place. |
| New container image or Dockerfile changes | smoke is orchestration, not a new test tool. Runs existing tools inside the existing container. | Reuse `localhost/dingofs-testsuite-tools:latest`. |
| `set -e` in the smoke orchestrator function | Would cause the entire smoke run to abort on first tool failure. | Use explicit exit code checks per tool. Continue to next tool even if one fails. Collect all results. |

## Parsing Approach: pjdtest (TAP via prove)

The current `pjdtest_run()` writes output to: `$output/pjdtest_${RUN_TIMESTAMP}/$SCENARIO/pjdtest_${timestamp}`

Contents of this file follow the TAP (Test Anything Protocol) format:

**Per-assertion lines:**
```
ok 1 - chmod changes permissions correctly
not ok 3 - chmod fails on nonexistent path
ok 4 # skip root-only test
```

**prove summary footer (on success):**
```
All tests successful.
Files=233, Tests=8832, 120 wallclock secs
Result: PASS
```

**prove summary footer (on failure):**
```
Test Summary Report
-------------------
./tests/chmod/12.t (Wstat: 0 Tests: 14 Failed: 6)
  Failed tests:  3-4, 7-8, 11-12
Files=232, Tests=8789, 704 wallclock secs
Result: FAIL
```

**Recommended parser (bash, added as helper inside `cmd_smoke`):**
```bash
parse_pjdtest_results() {
    local output_file="$1"
    local pass=0 fail=0 skip=0 total=0

    # Method 1: Extract from prove footer (most reliable for aggregated counts)
    if grep -q 'Result: FAIL' "$output_file" 2>/dev/null; then
        local overall="FAIL"
    else
        local overall="PASS"
    fi

    # Try to get totals from "Files=N, Tests=N" footer line
    total=$(grep -oP 'Tests=\K\d+' "$output_file" 2>/dev/null | tail -1 || echo 0)

    # If footer totals unavailable, fall back to counting TAP lines
    if [[ "$total" -eq 0 ]]; then
        pass=$(grep -cE '^ok\b' "$output_file" 2>/dev/null || echo 0)
        fail=$(grep -cE '^not ok\b' "$output_file" 2>/dev/null || echo 0)
        skip=$(grep -cE '^ok\b.*#\s*[Ss][Kk][Ii][Pp]' "$output_file" 2>/dev/null || echo 0)
        pass=$((pass - skip))  # ok lines counted SKIP directives, subtract them
        total=$((pass + fail + skip))
    else
        # Derive pass/fail/skip from individual test file summaries
        # and TAP line counts
        pass=$(grep -cE '^ok\b' "$output_file" 2>/dev/null || echo 0)
        fail=$(grep -cE '^not ok\b' "$output_file" 2>/dev/null || echo 0)
        skip=$(grep -cE '^ok\b.*#\s*[Ss][Kk][Ii][Pp]' "$output_file" 2>/dev/null || echo 0)
        pass=$((pass - skip))
    fi

    printf '%d %d %d %d %s' "$total" "$pass" "$fail" "$skip" "$overall"
}
```

**Confidence: MEDIUM** -- TAP format is standardized (TAP v13 spec). `prove` output format verified via real-world run logs (Kata Containers project). Exact prove version in the Docker image should be spot-checked.

## Parsing Approach: LTP (via runltp summary table)

The current `ltp_run()` runs:
```bash
timeout 3600 /opt/ltp/runltp -f "$scenario" -d . -p "$OUTPUT" -l "${log_file}"
```

The `-l` log file ends with a **summary table**:
```
Test Start Time: Tue Jun 24 14:32:15 2014
-----------------------------------------
Testcase                       Result     Exit Value
--------                       ------     ----------
access01                       PASS       0
access02                       PASS       0
getxattr01                     CONF       32
...
-----------------------------------------------
Total Tests: 8
Total Skipped Tests: 2
Total Failures: 0
Kernel Version: 3.16.0-rc1+
Machine Architecture: x86_64
Hostname: localhost.localdomain
```

**Recommended parser (bash):**
```bash
parse_ltp_results() {
    local log_file="$1"
    local total=0 pass=0 fail=0 skip=0

    # Primary: parse the summary table footer
    total=$(grep -oP 'Total Tests:\s*\K\d+' "$log_file" 2>/dev/null | tail -1 || echo 0)
    fail=$(grep -oP 'Total Failures:\s*\K\d+' "$log_file" 2>/dev/null | tail -1 || echo 0)
    skip=$(grep -oP 'Total Skipped Tests:\s*\K\d+' "$log_file" 2>/dev/null | tail -1 || echo 0)

    # Fallback: count TPASS/TFAIL/TCONF markers in output (older LTP versions)
    if [[ "$total" -eq 0 ]]; then
        local tpass_count=$(grep -c 'TPASS:' "$log_file" 2>/dev/null || echo 0)
        local tfail_count=$(grep -c 'TFAIL:' "$log_file" 2>/dev/null || echo 0)
        local tbrok_count=$(grep -c 'TBROK:' "$log_file" 2>/dev/null || echo 0)
        local tconf_count=$(grep -c 'TCONF:' "$log_file" 2>/dev/null || echo 0)
        pass=$tpass_count
        fail=$((tfail_count + tbrok_count))
        skip=$tconf_count
        total=$((pass + fail + skip))
    else
        pass=$((total - fail - skip))
    fi

    local overall="PASS"
    [[ "$fail" -gt 0 ]] && overall="FAIL"

    printf '%d %d %d %d %s' "$total" "$pass" "$fail" "$skip" "$overall"
}
```

**Confidence: MEDIUM** -- LTP summary table format verified via DeepWiki, Yocto Project wiki, and LTP mailing list discussion. The exact format can vary between runltp versions. The TPASS/TFAIL/TCONF fallback provides resilience against format drift. Test against the actual runltp in the Docker image.

## Parsing Approach: mdtest (smoke context)

mdtest is a metadata performance benchmark, not a pass/fail test suite. For smoke purposes:

| Criteria | Mapping |
|----------|---------|
| Exit code 0 AND output contains "SUMMARY rate" | **PASS** |
| Exit code non-zero OR no SUMMARY rate found | **FAIL** |
| Skip count | Always 0 (not applicable) |
| Total count | 1 (single run granularity) |

Smoke runs mdtest with `-s all -n 8` per the milestone spec.

## Integration Points (Host-Side Orchestration -- Recommended)

### Single file changed: `dingofs-testsuite-tool`

| Location | Change | Lines |
|----------|--------|-------|
| `show_help()` | Add `dtt smoke` usage example: `dtt smoke [--wechat] [--email] [--debug]` | ~6 lines |
| New: `cmd_smoke()` | Orchestrator function: create directories, call run_testsuite 3 times, parse results, write summary, notify | ~120 lines |
| `dingofs-testsuite-tool()` dispatch | Add `smoke)` case that calls `cmd_smoke "$@"` | ~3 lines |

### Files NOT changed

| File | Reason |
|------|--------|
| `entrypoint.sh` | All tool run functions used as-is via existing `run_testsuite()` |
| `scripts/notify.sh` | Existing notification functions accept tool/duration/details args. Smoke passes combined summary as details string. |
| `Dockerfile` | No new tools, no new dependencies |
| `install.sh` / `uninstall.sh` | No new files to deploy |
| `scripts/generate_report.py` | No new report format needed |

### smoke output directory structure

```
${OUTPUT}/smoke_20260519_143052/
  pjdtest/             # pjdtest run output (from run_testsuite -t pjdtest -s all)
    pjdtest_*/         # timestamped subdirectory from pjdtest_run
  mdtest/              # mdtest run output (from run_testsuite -t mdtest -s all -n 8)
    mdtest_*/          # timestamped subdirectory from mdtest_run
  ltp/                 # ltp smoke output (from run_testsuite -t ltp -s smoke)
    ltp_*/             # timestamped subdirectory from ltp_run
  smoke_summary.txt    # combined pass/fail/skip/total for all 3 tools
  result.log           # aggregated result log entries
```

### smoke_summary.txt format

```
DingoFS Smoke Test Summary
===========================
Run Time: 2026-05-19 14:30:52
Duration: 5m 32s

Tool        Total   Passed  Failed  Skipped  Status
--------    -----   ------  ------  -------  ------
pjdtest     8832    8828    4       0        FAIL
mdtest      1       1       0       0        PASS
ltp         8       6       0       2        PASS
--------    -----   ------  ------  -------  ------
TOTAL       8841    8835    4       2        FAIL (1/3 tools failed)
```

### Notification integration

Smoke sends a **single combined notification** after all three tools complete, using the existing `send_wechat_notification` / `send_email_notification` functions directly from `cmd_smoke()` (since the notification functions are sourced). The details string contains the pass/fail/skip/total breakdown for each tool.

For WeChat: The combined summary is formatted as a markdown_v2 table in the notification content.
For Email: The combined summary is formatted as an HTML table, reusing the existing email template structure.

## Sources

- TAP v13 Specification: http://testanything.org/tap-version-13-specification.html -- pjdtest output line format (HIGH confidence)
- Kata Containers issue #826: https://github.com/kata-containers/runtime/issues/826 -- Real-world pjdfstest/prove output including `Result: FAIL`, `Files=N, Tests=N` footer (MEDIUM confidence)
- DeepWiki: LTP Test Result Reporting: https://deepwiki.com/linux-test-project/ltp/2.2-test-result-reporting -- LTP `<<<test_start>>>`/`<<<test_end>>>` block format, termination_id bitmask, summary table (HIGH confidence)
- Yocto Project LTP Result Wiki: https://wiki.yoctoproject.org/wiki/LTP_result -- LTP summary table: "Total Tests:", "Total Failures:", "Total Skipped Tests:" (MEDIUM confidence)
- LTP Mailing List: https://lists.linux.it/pipermail/ltp/2022-December/032235.html -- Discussion of runltp log output format (MEDIUM confidence)
- OE-Core LTP Parser: http://git.enea.com/cgit/linux/poky.git/commit/meta/lib/oeqa/utils/logparser.py?id=b398c7653ec6272178dd6403dfcadf475f677bf5 -- Reference implementation of LTP result parsing with TPASS/TFAIL/TCONF mapping (MEDIUM confidence)
- Existing codebase: `dingofs-testsuite-tool` (wrapper), `entrypoint.sh` (runner), `scripts/notify.sh` (notifications) -- Full source analysis for architecture and integration points (HIGH confidence)

---
*Stack research for: dtt smoke subcommand*
*Researched: 2026-05-19*
