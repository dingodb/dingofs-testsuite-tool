# Pitfalls Research: dtt smoke Command

**Domain:** Bash-based container test orchestration with result parsing
**Researched:** 2026-05-19
**Confidence:** HIGH (verified against official LTP docs, prove TAP format docs, and existing codebase analysis)

## Executive Summary

Adding a `dtt smoke` command that orchestrates three sequential container-based test runs (pjdtest, mdtest, ltp) and parses aggregate pass/fail/skip/total statistics introduces three hazard categories: (1) bash-based multi-container orchestration where `set -e` and partial failures interact badly, (2) parsing two fundamentally different output formats (LTP's TPASS/TCONF and pjdtest's TAP), and (3) aggregating cross-run results with reliable file-based state management. The existing codebase already has `set -e` globally, patterns for PIPESTATUS handling, and per-tool notification dispatch -- all of which the smoke command must not break while adding new aggregate behavior.

---

## Critical Pitfalls

Mistakes that cause silent data loss, wrong pass/fail counts, broken notifications, or complete feature rewrites.

---

### Pitfall 1: `set -e` Kills Smoke Orchestration on First Tool Failure

**What goes wrong:**
The smoke command runs three tools sequentially. If the first tool (pjdtest) exits non-zero, `set -e` terminates the entire script before LTP or mdtest even start. Users get no results for tools 2 and 3, and the smoke summary is never generated.

**Why it happens:**
Both `entrypoint.sh` (line 3) and the dtt wrapper (line 7) declare `set -e` globally. Any command returning non-zero -- including a test tool with legitimate failures -- causes immediate script exit. The dtt wrapper's `run_testsuite()` function also propagates exit codes but always launches exactly one container. The smoke command must launch three containers even if some fail.

**Consequences:**
- Partial smoke runs with no useful aggregate result
- LTP never runs if pjdtest has even one failure
- Notifications never sent because the summary function is never reached
- Users get misleading "command not found" style errors rather than "tests failed" reports

**How to avoid:**
Use a wrapper pattern that explicitly toggles error handling around each tool invocation:

```bash
run_smoke() {
    local overall_exit=0
    local -a tool_results=()

    for tool in pjdtest mdtest ltp; do
        set +e
        run_smoke_tool "$tool"
        local exit_code=$?
        set -e
        tool_results+=("$tool:$exit_code")
        [[ $exit_code -ne 0 ]] && overall_exit=1
    done

    aggregate_smoke_results "${tool_results[@]}"
    return $overall_exit
}
```

Do NOT rely on `|| true` after each call -- this swallows real infrastructure errors (docker daemon down, disk full). Only toggle `set -e` around the expected-to-fail test invocations, not around critical setup/teardown code.

**Warning signs:**
- Smoke run stops after pjdtest and never prints LTP banner
- Error message is "command failed" with no tool name context
- `echo "LTP starting"` on line after a tool call never executes

**Phase to address:** Phase 1 (smoke orchestration function in dtt wrapper) -- must be addressed before any result parsing code is written.

---

### Pitfall 2: LTP Log Parsing Regex Matching TPASS Inside Test Names

**What goes wrong:**
A naive regex like `grep -c 'TPASS:' ltp.log` matches incorrectly when test names contain "TPASS" as a substring (rare but possible), or when a previous test's output contaminates the log file if append-mode is used.

**Why it happens:**
LTP output lines follow the format `<testname> <counter> <TAG>: <description>`. The TAG is always preceded by a digit (the counter) and a space. A regex like `grep -c 'TPASS:'` would match a line like `test_tpass_edge 5 TFAIL: expected TPASS behavior`. The correct boundary is `[[:space:]]TPASS:` preceded by one or more digits.

**Consequences:**
- Inflated pass counts on the smoke summary
- Wrong pass rate in notifications
- Hard to debug because `grep -c` is silent about what matched

**How to avoid:**
Use word-boundary-aware matching with a digit prefix:

```bash
# Correct: matches "N TPASS:" pattern (digit + space + TPASS + colon)
ltp_passed=$(grep -cP '\d\s+TPASS:' "$ltp_log" || true)

# Or for broader compatibility without -P (macOS/BSD grep):
ltp_passed=$(grep -c 'TPASS:' "$ltp_log" | head -1)
# Then validate by checking a sample line
```

Better yet, use awk for structured field matching:
```bash
awk '$2 ~ /^[0-9]+$/ && $3 == "TPASS:" {pass++}
     $2 ~ /^[0-9]+$/ && $3 == "TFAIL:" {fail++}
     $2 ~ /^[0-9]+$/ && $3 == "TCONF:" {skip++}
     $2 ~ /^[0-9]+$/ && $3 == "TBROK:" {broken++}
     END {printf "passed=%d failed=%d skipped=%d broken=%d total=%d\n",
          pass+0, fail+0, skip+0, broken+0, pass+fail+skip+broken}' \
    "$ltp_log"
```

**Warning signs:**
- Pass count > total count (impossible, indicates double-counting)
- Pass count exactly equals line count of log file (everything matched)
- Different `grep -c` and `grep -wc` counts for the same tag

**Phase to address:** Phase 2 (LTP result parsing in smoke summary) -- parsing code must use field-based matching, not substring matching.

---

### Pitfall 3: LTP `runltp` Summary Block Format Variance Across Versions

**What goes wrong:**
Code that parses `runltp`'s final "Total Tests:" summary block breaks when LTP version changes, because the summary format is not contractually stable. Some versions print "Total Tests:" while others print "Total Passed:" or use different whitespace/spacing.

**Why it happens:**
The `runltp` script is a legacy Perl/shell script (being replaced by `runltp-ng` in Python). The summary output format has varied across LTP releases. The current codebase uses LTP installed from source in the Docker image -- the version is pinned at build time but could change when the image is rebuilt.

**Consequences:**
- Summary parsing silently returns zero counts after image rebuild
- "0 passed, 0 failed" smoke result when tests actually ran
- Hard to reproduce because it only manifests after Docker image rebuild

**How to avoid:**
Parse individual TPASS/TFAIL/TCONF/TBROK lines from the log (which use a stable format since LTP's inception) rather than relying on the summary block. The per-line format (`testname N TAG: description`) has been stable across all LTP versions. Only fall back to the summary block if no per-line tags are found (which would indicate a drastically different output format).

```bash
parse_ltp_results() {
    local ltp_log="$1"
    local passed=0 failed=0 skipped=0 broken=0

    # Primary: parse individual result lines (stable format)
    while IFS= read -r line; do
        case "$line" in
            *" TPASS: "*) ((passed++)) ;;
            *" TFAIL: "*) ((failed++)) ;;
            *" TCONF: "*) ((skipped++)) ;;
            *" TBROK: "*) ((broken++)) ;;
        esac
    done < "$ltp_log"

    # Fallback: parse summary block if no individual lines found
    if [[ $((passed + failed + skipped + broken)) -eq 0 ]]; then
        passed=$(grep -oP 'Total Tests:\s*\K\d+' "$ltp_log" || echo "0")
        failed=$(grep -oP 'Total Failures:\s*\K\d+' "$ltp_log" || echo "0")
        skipped=$(grep -oP 'Total Skipped Tests:\s*\K\d+' "$ltp_log" || echo "0")
    fi

    local total=$((passed + failed + skipped + broken))
    echo "passed=$passed failed=$failed skipped=$skipped broken=$broken total=$total"
}
```

**Warning signs:**
- Smoke summary shows 0/0/0 for LTP after image rebuild
- `runltp` emits a warning about deprecated output format
- New LTP image produces JSON output (runltp-ng) instead of text

**Phase to address:** Phase 2 (LTP parsing) -- must implement dual-mode parsing with individual-line primary and summary-block fallback.

---

### Pitfall 4: pjdtest TAP `ok` / `not ok` Parsing Ambiguity with Descriptions

**What goes wrong:**
pjdtest output goes through `prove -rv`, producing both per-test TAP output lines (`ok 1`, `not ok 2 - tried '...', expected ...'`) and a final summary (`Result: PASS`, `Files=..., Tests=...`). Parsing only the summary line misses detailed pass/fail counts. Parsing only TAP lines fails when test descriptions themselves contain "ok" or "not ok" as substrings.

**Why it happens:**
TAP format has strict syntax: `ok N` or `not ok N` at the start of a line, followed by an optional `- description` or `# directive`. But `prove -v` interleaves verbose output with TAP lines, and test descriptions can contain arbitrary text including the words "ok" and "not ok". A greedy regex like `grep -c 'not ok'` matches both real failures and descriptions mentioning "not ok".

Additionally, pjdtest uses `# TODO` directives in TAP output (e.g., `not ok 5 # TODO known_issue`), which `prove` treats as expected failures (not counted as real failures). A naive parser would count these as failures.

**Consequences:**
- Inflated fail counts from TODO tests
- pjdtest comments like "expected ok behavior" matching as pass
- Skewed pass rate in smoke summary

**How to avoid:**
Parse at the TAP line level with line-anchored patterns, and handle TODO directives:

```bash
parse_pjdtest_results() {
    local pjdtest_output="$1"
    local passed=0 failed=0 skipped=0 total=0

    while IFS= read -r line; do
        # TAP: "ok N" at line start = pass
        if [[ "$line" =~ ^ok[[:space:]]+[0-9]+ ]]; then
            ((passed++))
        # TAP: "not ok N" + "# TODO" = expected failure (skip)
        elif [[ "$line" =~ ^not[[:space:]]+ok[[:space:]]+[0-9]+.*"# TODO" ]]; then
            ((skipped++))
        # TAP: "not ok N" without # TODO = real failure
        elif [[ "$line" =~ ^not[[:space:]]+ok[[:space:]]+[0-9]+ ]]; then
            ((failed++))
        fi
        # TAP plan line: "1..N" = total planned tests
        if [[ "$line" =~ ^1\.\.([0-9]+)$ ]]; then
            total="${BASH_REMATCH[1]}"
        fi
    done < "$pjdtest_output"

    # Fall back to prove summary if no TAP lines parsed
    if [[ $((passed + failed + skipped)) -eq 0 ]]; then
        if grep -q "^Result: PASS" "$pjdtest_output"; then
            total=$(grep -oP 'Tests=\K\d+' "$pjdtest_output" | head -1)
            passed="$total"
        elif grep -q "^Result: FAIL" "$pjdtest_output"; then
            total=$(grep -oP 'Tests=\K\d+' "$pjdtest_output" | head -1)
            failed=$(grep -oP 'Failed:\s*\K\d+' "$pjdtest_output" | head -1)
            passed=$((total - failed))
        fi
    fi

    echo "passed=$passed failed=$failed skipped=$skipped total=$total"
}
```

**Warning signs:**
- Fail count exceeds total test count (impossible)
- TODO tests appear in failure list
- "not ok" in test descriptions inflates counts
- prove summary and TAP parse produce different numbers

**Phase to address:** Phase 2 (pjdtest parsing in smoke summary) -- must use line-anchored patterns with TODO handling.

---

### Pitfall 5: File-Based Communication Between Sequential Container Runs

**What goes wrong:**
The smoke command runs three separate containers sequentially. Results from each tool's container run are written to the host output directory via volume mounts. If the result files are not uniquely named (e.g., all using `result.log` or metadata written to the same file), later runs overwrite earlier results.

**Why it happens:**
The current `entrypoint.sh` writes `result.log` to its output directory using `log_result()`. Each tool already writes to a timestamped subdirectory (e.g., `pjdtest_20260519_143000/`), so this specific case is handled. However, the smoke summary parser must know exactly where to find each tool's output file. If the timestamp changes between the tool run and the parsing step, or if the directory naming convention diverges, the parser finds nothing.

**Consequences:**
- Smoke summary shows "pjdtest: 0/0/0" when pjdtest actually ran
- Silent failures -- no error because `grep` on non-existent files returns empty
- LTP results parsed from pjdtest output file (wrong tool name match)

**How to avoid:**
The smoke command should explicitly set the output directory for each tool and capture the exact path used. Do not rely on globbing or "most recent" file discovery:

```bash
run_smoke() {
    local smoke_base="$OUTPUT/smoke_${RUN_TIMESTAMP}"
    mkdir -p "$smoke_base"

    local pjdtest_dir="$smoke_base/pjdtest"
    local mdtest_dir="$smoke_base/mdtest"
    local ltp_dir="$smoke_base/ltp"

    # Run each tool with explicit output directory
    run_container "pjdtest" "$pjdtest_dir"  # writes to $pjdtest_dir/
    run_container "mdtest" "$mdtest_dir"    # writes to $mdtest_dir/
    run_container "ltp" "$ltp_dir"          # writes to $ltp_dir/

    # Parse from known paths -- no globbing, no "latest file" heuristic
    parse_pjdtest_results "$pjdtest_dir"/*.log
    parse_mdtest_results "$mdtest_dir"
    parse_ltp_results "$ltp_dir"/*.log
}
```

**Warning signs:**
- Parsing uses `ls -t | head -1` instead of explicit paths
- Output directory names contain dynamic timestamps not captured as variables
- "No such file" errors during parse step but not during test execution

**Phase to address:** Phase 1 (smoke orchestration) -- the directory layout must be deterministic, not heuristic.

---

### Pitfall 6: mdtest "Pass/Fail" Semantics for a Performance Tool

**What goes wrong:**
mdtest is a metadata performance benchmark, not a correctness test. It has no concept of "pass" or "fail" -- it always "succeeds" (exit code 0) if the binary runs, regardless of whether the performance numbers are meaningful. Treating mdtest exit code zero as "passed" gives users a misleading green checkmark for a tool that might have produced nonsensical results (e.g., running against a broken filesystem that returns errors but mdtest doesn't detect).

**Why it happens:**
The existing `log_result()` for mdtest checks for "SUMMARY rate" in output. This detects whether mdtest actually ran vs. crashed. But for smoke testing with `-n 8` (only 8 files, very fast), the output contains a valid summary even if the underlying filesystem is broken. mdtest reports raw operation counts and rates -- it does not verify data integrity.

**Consequences:**
- Smoke summary shows "mdtest: PASS" when filesystem is corrupted
- Users get false confidence from a green smoke result
- LTP and pjdtest might catch the corruption, but mdtest shows green since it was never designed to catch it

**How to avoid:**
Define explicit mdtest smoke success criteria:

1. **Exit code 0** (process didn't crash)
2. **Non-zero operation counts** (at least some operations completed)
3. **Non-zero rate values** (operations/second > 0)

Do NOT attempt to compare rates against a baseline (that's performance regression testing, not smoke testing). The smoke purpose for mdtest is: "does mdtest at least run without crashing on this filesystem?"

```bash
parse_mdtest_smoke_result() {
    local mdtest_raw="$1"
    local status="FAIL"
    local summary=""

    if grep -q "SUMMARY rate" "$mdtest_raw" 2>/dev/null; then
        # Extract operation counts and verify non-zero
        local creates=$(grep "File creation" "$mdtest_raw" | awk '{print $NF}')
        local stats=$(grep "File stat" "$mdtest_raw" | awk '{print $NF}')
        local removes=$(grep "File removal" "$mdtest_raw" | awk '{print $NF}')

        if [[ "${creates:-0}" -gt 0 ]] || [[ "${stats:-0}" -gt 0 ]]; then
            status="PASS"
            summary="mdtest completed: creates=$creates, stats=$stats, removes=$removes"
        else
            status="FAIL"
            summary="mdtest ran but produced zero operations (filesystem issue?)"
        fi
    else
        status="FAIL"
        summary="mdtest did not produce SUMMARY output (crashed or timed out)"
    fi

    echo "status=$status summary=\"$summary\""
}
```

**Warning signs:**
- mdtest always shows PASS regardless of filesystem state
- "SUMMARY rate" present but all values are zero
- mdtest output is empty or truncated

**Phase to address:** Phase 2 (result aggregation) -- must define explicit non-binary success criteria for performance tools.

---

### Pitfall 7: Smoke Notification Duplicating Existing Per-Tool Notifications

**What goes wrong:**
The smoke command sends a combined notification summarizing all three tools. But if the individual tool invocations inside the container still have `--wechat` or `--email` enabled, each tool also sends its own notification. Users get 4 notifications (3 per-tool + 1 aggregate) instead of 1 summary.

**Why it happens:**
The existing `entrypoint.sh` dispatches notifications at the end of each tool run (e.g., `ltp_run()` calls `send_wechat_notification()` directly). The smoke command passes `--wechat` to the dtt wrapper, which sets `WECHAT=yes` environment variable inside each container. Each container's entrypoint.sh then dutifully sends its own notification.

**Consequences:**
- Notification spam -- 4 messages for one smoke run
- Confusion: per-tool notification says "FAIL" while aggregate says something else
- Rate limiting on WeChat webhook (20 msg/min limit)

**How to avoid:**
Two strategies, choose one:

**Strategy A (recommended):** The smoke command runs tools WITHOUT notification flags, then sends ONE aggregate notification after all three complete. Modify `run_testsuite()` to accept a `--no-notify` internal flag that suppresses per-tool notifications even when WECHAT/EMAIL env vars are set.

**Strategy B:** Keep per-tool notifications but suppress them when running under smoke mode by setting a `SMOKE_MODE=yes` environment variable, and check it in entrypoint.sh notification dispatch code.

Strategy A is preferred because it keeps the smoke notification as the single source of truth.

```bash
# In dtt wrapper: smoke mode strips notification flags
run_smoke_tool() {
    local tool="$1"
    local output_dir="$2"

    # Strip --wechat and --email to prevent per-tool notifications
    local docker_args=(
        $runtime run --rm --privileged
        -v "${mount}:/data"
        -v "${output_dir}:/output"
        "$image"
        /entrypoint.sh -t "$tool" -s "$smoke_scenario" -m /data -o /output
    )
    # Explicitly do NOT pass -e WECHAT or -e EMAIL
    "${docker_args[@]}"
}
```

**Warning signs:**
- 4 WeChat messages for one smoke command execution
- Per-tool notification timestamps are within seconds of each other
- Aggregate notification and per-tool notification show different pass/fail status

**Phase to address:** Phase 3 (notification integration) -- must coordinate notification suppression between wrapper and container.

---

### Pitfall 8: LTP Timeout Handling Produces Incomplete Logs

**What goes wrong:**
The current `ltp_run()` wraps LTP execution with `timeout 3600`. If the timeout fires (exit code 124), LTP is killed mid-execution. The log file may be truncated in the middle of a result line, or the summary block is never written. A parser that expects a complete log file produces wrong or zero counts.

**Why it happens:**
The `timeout` command sends SIGTERM to the process group, then SIGKILL after a grace period. LTP's `runltp` script does not install a signal handler for graceful shutdown on timeout. The output file may be cut off mid-line: `access01    1 TPAS` (missing the `S: ...`).

**Consequences:**
- Partial last line: `TPAS` is not matched by `TPASS:` regex -- one test silently uncounted
- Missing summary block if timeout fires before `runltp` reaches the summary printing code
- Unclear whether missing counts mean "no tests ran" or "timeout killed the parser"

**How to avoid:**
1. Check for timeout exit code (124) and mark the LTP result as "TIMEOUT" rather than trying to parse a partial log
2. When timeout detected, parse whatever is available but annotate as partial
3. Log the number of parsed lines vs. expected output to detect truncation

```bash
local ltp_exit=0
timeout 3600 /opt/ltp/runltp -f "$scenario" > "$ltp_log" 2>&1 || ltp_exit=$?

if [[ $ltp_exit -eq 124 ]]; then
    ltp_status="TIMEOUT"
    # Parse partial results but flag as incomplete
    parse_ltp_partial "$ltp_log"
elif [[ $ltp_exit -eq 0 ]]; then
    ltp_status="COMPLETE"
    parse_ltp_full "$ltp_log"
else
    ltp_status="ERROR"
fi
```

**Warning signs:**
- LTP log file ends mid-line (no newline at EOF)
- Pass+fail+skip count is less than expected "Total Tests:" value
- Log file smaller than expected (e.g., 500KB expected, got 50KB)

**Phase to address:** Phase 2 (LTP parsing) -- must handle truncated output gracefully.

---

### Pitfall 9: Bash Argument Parsing Collision Between Smoke and Normal Modes

**What goes wrong:**
The dtt wrapper's `dingofs-testsuite-tool()` function dispatches commands based on `$1`. Adding `smoke` as a new command requires changes to the case statement AND the option-forwarding logic. If the smoke command reuses `run_testsuite()` by calling it multiple times, the argument parsing inside `run_testsuite()` may consume or mutate global variables that persist between calls.

**Why it happens:**
`run_testsuite()` uses local variables for most state (`mount`, `output`, `tool`, `scenario`, etc.), but the `--wechat` flag sets `wechat="yes"` which is then passed as `-e WECHAT=yes` to all subsequent container invocations. If the smoke command calls `run_testsuite()` 3 times, the second and third calls inherit the `--wechat` flag set during the first call unless the flag state is explicitly reset.

Additionally, `run_testsuite()` accesses global config state via `load_config()` -- any mutation to config files between smoke tool runs could affect subsequent runs.

**Consequences:**
- Second tool unexpectedly sends WeChat notification even when user didn't request it
- Third tool uses wrong scenario from previous invocation
- Config state corruption if a tool run modifies config files

**How to avoid:**
The smoke command should NOT call `run_testsuite()` multiple times. Instead, it should be a self-contained function that builds docker commands directly (similar to how `run_testsuite()` builds them) with explicit, non-shared state for each invocation:

```bash
cmd_smoke() {
    local image=$(load_config image)
    local mount=$(load_config testdir)
    local smoke_output=$(load_config output)
    local runtime=$(load_config runtime)

    # Validate once, not per-tool
    validate_smoke_prerequisites

    # Run each tool with fresh state
    local -A smoke_results
    for tool in pjdtest mdtest ltp; do
        local tool_dir="${smoke_output}/smoke_${RUN_TIMESTAMP}/${tool}"
        mkdir -p "$tool_dir"

        # Build docker command inline -- no shared state from run_testsuite()
        $runtime run --rm --privileged \
            -v "${mount}:/data" \
            -v "${tool_dir}:/output" \
            "$image" \
            /entrypoint.sh -t "$tool" -s "${SMOKE_SCENARIOS[$tool]}" \
            -m /data -o /output

        smoke_results[$tool]=$?
    done

    aggregate_and_notify "${smoke_results[@]}"
}
```

**Warning signs:**
- Second tool run uses `--wechat` flag intended only for first tool
- `echo "Tool: $tool"` shows wrong tool name on second iteration
- Config state (`load_config`) changes unexpectedly between smoke tool runs

**Phase to address:** Phase 1 (smoke orchestration) -- must be a self-contained function, not a loop around `run_testsuite()`.

---

### Pitfall 10: Exit Code Semantics for Multi-Tool Aggregate

**What goes wrong:**
The smoke command aggregates three tools. If pjdtest has 1 failure, mdtest passes, and LTP passes, what should the smoke exit code be? If the exit code is always 0 (because the smoke "ran successfully" as a process), CI/CD pipelines incorrectly treat the run as green. If the exit code is always non-zero when any tool has failures, the exit code doesn't convey which tool failed.

**Why it happens:**
Unix exit codes are a single byte (0-255). There's no standard way to encode "tool A passed, tool B failed" in an exit code. CI/CD systems check `$? == 0` to determine pass/fail. The existing `run_testsuite()` returns the tool's exit code directly, which works because there's only one tool.

**Consequences:**
- CI/CD passes when a smoke test found real failures
- Operator has to read log output to know if anything failed (defeats purpose of exit codes)
- No way to programmatically check which tool failed

**How to avoid:**
Use a binary aggregate: exit 0 only if ALL three tools pass. Exit 1 if ANY tool fails. Write detailed per-tool status to a machine-readable file (e.g., `smoke_result.json`) for programmatic consumption:

```bash
# Aggregate exit code: 0 = all pass, 1 = at least one failure
if [[ $overall_exit -eq 0 ]]; then
    return 0
else
    return 1
fi

# Detailed result in smoke_result.json:
# {
#   "pjdtest": {"status": "PASS", "passed": 94, "failed": 0, "skipped": 0, "total": 94},
#   "mdtest":  {"status": "PASS", "summary": "mdtest completed: creates=8, stats=8, removes=8"},
#   "ltp":     {"status": "FAIL", "passed": 120, "failed": 3, "skipped": 15, "total": 138}
# }
```

**Warning signs:**
- Smoke always returns 0 even with "FAIL" in the summary output
- Multiple exit code values attempted (19 = pjdtest failed, 39 = ltp failed, etc.)
- `echo $?` after smoke shows 0 but log says "FAIL"

**Phase to address:** Phase 3 (aggregate result) -- must define and document exit code contract.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Parse LTP only via `runltp` summary block | One regex, fast | Breaks on LTP version change | Never -- per-line parsing is only slightly more code |
| Use `grep -c 'not ok'` for pjdtest failures | Single command | Matches TODO tests and description text | Never -- use line-anchored patterns |
| `set -e` + `|| true` on every smoke tool call | Easy to write | Masks real infrastructure errors (docker daemon down) | Never for docker run commands |
| Glob for "latest" output file (`ls -t \| head -1`) | No directory tracking needed | Wrong file when timestamps overlap | Only if output is guaranteed single-file and sequential |
| Reuse `run_testsuite()` in a loop for smoke | Less new code | State leaks between iterations, `--wechat` cascades | Never -- build dedicated smoke orchestration |

## Integration Gotchas

Common mistakes when connecting the smoke command to existing systems.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| WeChat notification | Per-tool notifications fire alongside aggregate smoke notification | Suppress per-tool notifications in smoke mode; send one aggregate message |
| Email notification | Email sent for each tool, hard to correlate with smoke run | Single email with all three tool summaries in one HTML table |
| `result.log` | Overwritten by each successive smoke tool run | Each tool writes to its own subdirectory; smoke summary has its own result.log |
| dtt wrapper entry point | `cmd_smoke` added to case statement but option forwarding broken | Smoke is a command (like `config`), not an option passthrough; matches `smoke` in `dingofs-testsuite-tool()` |
| Exit code to CI | CI sees exit 0 because wrapper's `return` doesn't propagate to `exit` | `run_smoke` returns aggregate exit code; caller uses `exit $?` |
| Config state | Smoke changes config state (mdsaddr, etc.) between tool runs | Config is read-only during smoke; no `save_config` calls in smoke path |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Smoke runs all 3 tools**: Always verify that all three output directories exist and contain output files -- a common bug is early return preventing tools 2 and 3 from running
- [ ] **LTP TCONF counted as skipped**: TCONF means "not applicable to this configuration" -- verify it is NOT counted as failure in the smoke summary
- [ ] **LTP TBROK counted as failure**: TBROK means the test infrastructure itself broke -- verify it IS counted as failure
- [ ] **pjdtest TODO tests excluded from failure count**: `not ok N # TODO` lines are expected failures -- verify they are counted as "skipped" not "failed"
- [ ] **mdtest zero operations detected**: Verify that mdtest with zero create/stat/remove counts is reported as FAIL, not PASS
- [ ] **No stale WECHAT/EMAIL env vars between smoke tools**: Verify that `--wechat` set for smoke notification does not leak into per-tool container env vars
- [ ] **Timeout results clearly marked**: Verify LTP runs killed by `timeout` (exit 124) are displayed as "TIMEOUT" not "FAIL" or "PASS"
- [ ] **Smoke notification contains per-tool breakdown**: Verify the aggregate notification shows pjdtest/mdtest/ltp results separately, not just one combined number
- [ ] **Zero results from parsing is not silently treated as success**: Verify that when parsing produces 0/0/0 counts, it's treated as a parse error, not "all passed"

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| `set -e` kills orchestration early | LOW | Wrap smoke tool invocation in `set +e`/`set -e` block |
| LTP summary format changes | MEDIUM | Switch to per-line TPASS/TFAIL/TCONF parsing |
| pjdtest parse matches `# TODO` as failures | LOW | Add `# TODO` exclusion to regex |
| Per-tool notification spam | LOW | Add `--no-notify` internal flag or unset WECHAT env var in smoke mode |
| Timeout truncates LTP log | LOW | Check exit code 124 and annotate result as partial |
| mdtest always reported as PASS | LOW | Add non-zero operation count check |
| Wrong output file parsed (stale/previous run) | MEDIUM | Use explicit subdirectory paths, not globs |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| `set -e` kills orchestration (P1) | Phase 1: Smoke orchestration | Run smoke with pjdtest guaranteed to fail (e.g., wrong mount); verify LTP still runs |
| LTP regex false matches (P2) | Phase 2: LTP result parsing | Unit test: feed LTP log with "TPASS:" in description text; verify count is correct |
| LTP summary format variance (P3) | Phase 2: LTP result parsing | Parse both old-format and new-format LTP logs; verify same counts |
| pjdtest TODO parsing (P4) | Phase 2: pjdtest parsing | Unit test: feed TAP output with `not ok 5 # TODO`; verify counted as skip |
| File-based communication (P5) | Phase 1: Smoke orchestration | Verify deterministic output paths after smoke run; no globs in parse code |
| mdtest pass/fail semantics (P6) | Phase 2: Result aggregation | Run mdtest on read-only filesystem; verify FAIL status |
| Notification duplication (P7) | Phase 3: Notification | Run smoke with --wechat; verify exactly 1 message received |
| LTP timeout truncation (P8) | Phase 2: LTP parsing | Force LTP timeout with `timeout 5`; verify graceful handling |
| Arg parsing collision (P9) | Phase 1: Smoke orchestration | Run `dtt smoke --wechat` then `dtt -t pjdtest -s all`; verify no state leak |
| Exit code semantics (P10) | Phase 3: Aggregate result | Run smoke with known failure; verify `$?` is non-zero |

## Sources

- LTP Test Result Reporting (DeepWiki): https://deepwiki.com/linux-test-project/ltp/2.2-test-result-reporting
- LTP runltp output format and parsing -- verified via LTP mailing list and source: https://github.com/linux-test-project/ltp
- Perl prove TAP output format: https://perldoc.perl.org/Test::Harness and https://metacpan.org/release/LEONT/Test-Harness-3.52
- LTP test.h bitmask result types (TPASS=0, TFAIL=1, TBROK=2, TWARN=4, TINFO=16, TCONF=32) -- confirmed from LTP source
- Existing codebase: entrypoint.sh (1837 lines), dingofs-testsuite-tool (823 lines), notify.sh (289 lines) -- analyzed for current patterns
- PROJECT.md: v1.5 smoke command milestone definition

---
*Pitfalls research for: dtt smoke command with test result parsing*
*Researched: 2026-05-19*
