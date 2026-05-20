# Project Research Summary

**Project:** dtt smoke subcommand (DingoFS Testsuite Tools)
**Domain:** Bash-based storage test orchestration
**Researched:** 2026-05-19
**Confidence:** HIGH

## Executive Summary

This project adds a `dtt smoke` subcommand to the existing DingoFS Testsuite Tools -- a containerized storage testing framework in bash. The smoke command orchestrates three existing test tools (pjdtest, mdtest, ltp) in sequence, parses their outputs for pass/fail/skip/total statistics, and sends a single combined notification (WeChat or Email) with a summary table of all results.

The recommended approach is a **hybrid architecture**: a thin CLI handler (`cmd_smoke()`) in the host-side `dingofs-testsuite-tool` wrapper that launches a single container, where a new `smoke_run()` function inside `entrypoint.sh` calls the three existing `_run()` functions sequentially with `SMOKE_MODE=1` to suppress individual notifications. This avoids container startup overhead (1 container instead of 3), enables in-memory statistics aggregation across tools, and produces a unified output directory under `smoke_<RUN_TIMESTAMP>/`.

The two primary risks are: (1) bash `set -e` killing orchestration on first tool failure, mitigated by explicit `set +e`/`set -e` toggling around each tool invocation; and (2) fragile text parsing producing wrong pass/fail counts, mitigated by line-anchored regex patterns with robust fallback paths. Zero new dependencies are required -- the entire feature is pure bash added to one existing wrapper file and one existing container entrypoint file.

## Key Findings

### Recommended Stack

This is a pure bash addition to the existing codebase. No new packages, no Dockerfile changes, no new container images. The two files changed are `dingofs-testsuite-tool` (host wrapper -- new `cmd_smoke()` function and dispatch case) and `entrypoint.sh` (container -- new `smoke_run()` function, SMOKE_MODE notification guards in 3 existing `_run()` functions). Result parsing uses bash builtins plus system `grep`/`awk`/`sed` -- no Python, jq, or other runtime dependencies.

**Note on STACK.md divergence:** The STACK.md research recommends host-side orchestration (wrapper calls `run_testsuite()` 3 times = 3 containers). The ARCHITECTURE.md research, which analyzed integration points more deeply, explicitly rejects this as Anti-Pattern 1 due to: scattered output directories (3 different timestamps), per-tool notification spam (3 separate WeChat messages), no shared memory for cross-tool statistics aggregation, and container startup overhead. **The synthesis recommends the ARCHITECTURE.md approach (Option C: single-container hybrid).**

**Core technologies (all existing):**
- **Bash 5.x** (Ubuntu 24.04): Wrapper scripting and result parsing -- already in use, no new runtime
- **Docker / Podman**: Container runtime -- already abstracted via `runtime` config key, `cmd_smoke()` builds docker commands directly
- **prove (Perl Test::Harness)**: Runs pjdtest and generates TAP-format output -- already invoked by `pjdtest_run()`
- **runltp (LTP)**: Runs LTP with structured log output -- already invoked by `ltp_run()`
- **mdtest (MPI binary)**: Metadata benchmark -- already invoked by `mdtest_run()`, run with `-n 8` for smoke
- **notify.sh**: WeChat + Email notification -- existing functions reused as-is for combined smoke summary

**What NOT to use:** Python/Ruby for parsing (adds runtime dependency), jq (unnecessary dependency), `set -e` with `|| true` (masks real infrastructure failures), new Dockerfile/container image (smoke is orchestration, not a new tool).

### Expected Features

**Must have (table stakes -- P1, v1):**
- `dtt smoke` command recognized by the CLI wrapper -- single entry point
- `smoke_run()` orchestrates pjdtest, mdtest, ltp sequentially -- reuse existing `_run()` functions
- Output under `$OUTPUT/smoke_<RUN_TIMESTAMP>/` with per-tool subdirectories -- organized results
- Per-tool pass/fail/skip/total statistics parsed from tool outputs -- core differentiator
- Single unified WeChat/Email notification with all three tools' summary -- consistent UX
- Aggregate exit code (0 = all pass, non-zero = any failure) -- CI/CD integration
- Progress display during execution (echo section headers between tools)

**Should have (differentiators -- P2, v1.x):**
- `result.json` structured output for machine consumption -- CI/CD dashboards
- `smoke_summary.txt` or `smoke_report.md` human-readable output -- offline sharing
- Detailed failed test names in notifications -- debugging aid
- `--fail-fast` flag to stop after first tool failure -- user choice

**Defer to v2+:**
- Historical smoke result comparison (diff against last run) -- requires persistent state
- Performance regression detection in mdtest (ops/s thresholds) -- thresholds need per-environment calibration
- Configurable smoke tool set -- dilutes "opinionated smoke" value proposition
- Smoke result trending dashboard -- belongs in monitoring system, not test tool

**Anti-features (explicitly rejected):**
- Parallel execution of three tools -- disk I/O contention, file collision, non-deterministic results
- Custom tool/scenario selection for smoke -- breaks comparability, defeats "one command" purpose
- Smoke-specific config keys -- fragments configuration, adds cognitive load
- Auto-retry on failure -- hides flakiness, confuses result provenance
- Real-time per-test streaming to notifications -- notification spam

**Protocol note:** FEATURES.md lists fast-fail (stop on pjdtest failure) as MVP. ARCHITECTURE.md and PITFALLS.md both indicate running all three tools by default regardless and aggregating results. The synthesis resolution is: run all three tools by default (provides complete picture in one run), with `--fail-fast` as an optional P2 flag. This matches user expectations of `dtt smoke` producing a full summary table.

### Architecture Approach

**Recommended: Option C (Hybrid -- single-container orchestration with thin CLI wrapper)**

The dtt wrapper adds a `cmd_smoke()` handler that builds a single docker command with `-t smoke` plus notification env vars. The container's `entrypoint.sh` adds a `smoke_run()` function that orchestrates the three tools within a single process. This preserves the existing architectural boundary (wrapper = CLI/config, container = test execution) while enabling in-memory statistics aggregation and a single combined notification.

The key architectural decisions:

1. **SMOKE_MODE guard**: `smoke_run()` sets `SMOKE_MODE=1` before calling each `_run()`. Each existing `_run()` function (pjdtest, mdtest, ltp) wraps its notification blocks in `if [[ "$SMOKE_MODE" != "1" ]]`. This is the minimal-touch approach -- 2 lines per function, 6 lines total across 3 functions.

2. **OUTPUT override**: `smoke_run()` temporarily sets `OUTPUT=$OUTPUT/smoke_<ts>` before calling each `_run()`, so all tool output lands under a unified `smoke_` prefix. The original `$OUTPUT` is restored after.

3. **Single notification at end**: `smoke_run()` collects pass/fail/skip/total for all three tools, then calls `send_wechat_notification()` and `send_email_notification()` once with a combined summary table. No per-tool notifications during smoke mode.

4. **Single container, single timestamp**: All three tools share the same `RUN_TIMESTAMP`, making output directories predictable and correlated.

**Major components and responsibilities:**

| Component | Location | Responsibility | Status |
|-----------|----------|----------------|--------|
| `cmd_smoke()` | dtt wrapper | CLI parsing, docker command construction, env var passthrough | NEW |
| `smoke)` dispatch case | dtt wrapper | Routes `dtt smoke` to `cmd_smoke()` | NEW |
| `smoke_run()` | entrypoint.sh | Orchestrate 3 tools, aggregate stats, write summary, send combined notification | NEW |
| `smoke)` dispatch case | entrypoint.sh | Routes `-t smoke` to `smoke_run()` | NEW |
| SMOKE_MODE guards | 3 `_run()` functions | Suppress per-tool notifications during smoke | MODIFIED (2 lines each) |
| `notify.sh` | scripts/notify.sh | WeChat/Email primitives | UNCHANGED |
| `Dockerfile` | repo root | All tools in single image | UNCHANGED |

**Build order (dependency-aware):**
```
Step 1: Add SMOKE_MODE guards (entrypoint.sh)     -- no dependencies
Step 2: Add smoke_run() function (entrypoint.sh)   -- depends on Step 1
Step 3: Wire smoke into dispatch/validation         -- depends on Step 2
Step 4: Add cmd_smoke() handler (dtt wrapper)      -- depends on Step 3
Step 5: Wire smoke into wrapper dispatch + help     -- depends on Step 4
```

### Critical Pitfalls

The PITFALLS.md research identifies 10 pitfalls across three categories: orchestration bugs, parsing bugs, and integration bugs. The top 5 most likely to cause rewrites:

1. **`set -e` kills orchestration on first tool failure** (Critical) -- Both `entrypoint.sh` and the dtt wrapper have global `set -e`. If pjdtest has any failure, the entire script exits before mdtest or LTP run. **Mitigation:** Explicitly toggle `set +e`/`set -e` around each tool invocation in `smoke_run()`. Do NOT use `|| true` on docker commands -- that masks real infrastructure failures.

2. **LTP log parsing regex matches TPASS inside test descriptions** (Critical) -- A naive `grep -c 'TPASS:'` can inflate counts if test names contain the string. **Mitigation:** Use awk for structured field matching (`$2 ~ /^[0-9]+$/ && $3 == "TPASS:"`) rather than substring matching. Parse individual TPASS/TFAIL/TCONF/TBROK lines (stable format since LTP inception) as primary, with summary block as fallback only.

3. **pjdtest TAP parsing counts TODO tests as failures** (Critical) -- `not ok N # TODO` directives are expected failures and should be counted as "skipped", not "failed". **Mitigation:** Use line-anchored bash regex patterns: `^ok[[:space:]]+[0-9]+` for pass, `^not[[:space:]]+ok[[:space:]]+[0-9]+.*"# TODO"` for skip, `^not[[:space:]]+ok[[:space:]]+[0-9]+` for fail.

4. **Smoke notification duplicates per-tool notifications** (Critical) -- If per-tool `_run()` functions still fire notifications during smoke, users get 4 messages (3 per-tool + 1 aggregate) instead of 1. **Mitigation:** SMOKE_MODE guard in each `_run()` skips individual notifications. `smoke_run()` sends exactly one combined notification at the end.

5. **mdtest "pass" for a broken filesystem** (Moderate) -- mdtest is a performance benchmark, not a correctness test. Exit code 0 with "SUMMARY rate" output does not mean the filesystem is healthy. **Mitigation:** Verify non-zero operation counts (creates, stats, removes > 0). Flag zero-operation runs as FAIL.

**Additional pitfalls addressed by research:** LTP summary format variance across versions (use per-line TPASS/TFAIL as primary), LTP timeout truncation (check exit code 124 and mark as TIMEOUT), file-based communication between tools (use explicit directory paths, not globs), argument parsing collision between smoke and normal modes (don't call `run_testsuite()` in a loop -- build docker commands directly in `cmd_smoke()`), and exit code semantics for multi-tool aggregate (binary: 0 if all pass, 1 if any fail; use `smoke_result.json` for per-tool detail).

## Implications for Roadmap

Based on combined research, recommended phase structure:

### Phase 1: Core Orchestration (entrypoint.sh -- SMOKE_MODE guards + smoke_run)
**Rationale:** The container is the execution environment. SMOKE_MODE guards must be added first so `smoke_run()` can call existing `_run()` functions without notification side effects. This phase is testable inside the container before any wrapper changes.
**Delivers:** Three existing `_run()` functions with SMOKE_MODE guards, new `smoke_run()` function that calls them sequentially, suppression of per-tool notifications.
**Addresses:** All P1 table-stakes features (serial execution, unified output directory, reuse existing functions).
**Avoids:** Pitfall 1 (set -e), Pitfall 7 (notification duplication), Pitfall 9 (arg collision -- smoke_run owns its state).
**Components:** Step 1 and Step 2 from Architecture build order.

### Phase 2: Result Parsing and Aggregation (entrypoint.sh -- statistics + summary output)
**Rationale:** The core value of smoke over three individual `dtt` commands is quantitative per-tool statistics and combined summary. This phase adds parsing for TAP, LTP log, and mdtest output, plus smoke_summary.json and smoke_summary.txt writing. Depends on Phase 1 (needs smoke_run to produce output for parsing).
**Delivers:** pjdtest TAP parser, LTP log parser, mdtest smoke result validator, `smoke_summary.txt`, `smoke_result.json`, aggregate statistics table in memory.
**Addresses:** Statistics parsing differentiators, structured output for CI/CD.
**Avoids:** Pitfall 2 (LTP regex), Pitfall 3 (LTP summary variance), Pitfall 4 (pjdtest TODO parsing), Pitfall 6 (mdtest semantics), Pitfall 8 (LTP timeout).
**Components:** Step 3 from Architecture build order (wire smoke into dispatch/validation).

### Phase 3: Wrapper CLI and Notification (dtt wrapper -- cmd_smoke + combined notification)
**Rationale:** Users access smoke through `dtt smoke`, not by running containers directly. The wrapper handler builds the docker command and passes env vars. Combined notification goes here because it bridges container-side results with the wrapper's notification primitives. Depends on Phase 2 (container must fully support `-t smoke`).
**Delivers:** `dtt smoke` command recognized, `cmd_smoke()` handler with --wechat/--email/--debug flags, single combined WeChat+Email notification, aggregate exit code, help text.
**Addresses:** Single command entry point, unified notification, CI/CD exit code contract.
**Avoids:** Pitfall 5 (deterministic paths), Pitfall 10 (exit code semantics), Pitfall 7 (notification duplication -- verified end-to-end).
**Components:** Step 4 and Step 5 from Architecture build order.

### Phase 4: Polish and Edge Cases (v1.x)
**Rationale:** Once the core loop works, add quality-of-life features and handle edge cases discovered during testing. This phase is lower priority and can ship separately.
**Delivers:** `--fail-fast` flag, `smoke_report.md` human-readable summary, detailed failed test names in notifications, LTP timeout handling (exit 124 detection), zero-results-as-parse-error detection.
**Addresses:** P2 features from FEATURES.md, "Looks Done But Isn't" checklist from PITFALLS.md.
**Avoids:** Edge cases found during Phase 1-3 testing.

### Phase Ordering Rationale

- **Container-first (Phases 1-2 before 3):** The container is where orchestration and parsing happen. The wrapper only needs to pass `-t smoke`. Building the wrapper first creates a chicken-and-egg problem where you can't test end-to-end. Starting inside the container allows isolated testing via `docker run ... -t smoke`.
- **Parsing after orchestration (Phase 2 after 1):** You cannot parse results until `smoke_run()` produces output. The parsing functions need real output files to test against.
- **Granular phases reflect build order dependencies:** The Architecture research identifies a strict 5-step dependency chain (SMOKE_MODE guards -> smoke_run -> dispatch wiring -> cmd_smoke -> wrapper dispatch). Grouping them into 3 phases respects these dependencies while keeping each phase independently testable.
- **Polish last:** The "Looks Done But Isn't" checklist from PITFALLS.md (9 items) should be addressed after the core loop works. Attempting them during earlier phases creates scope creep.

### Research Flags

**Phases needing deeper research during planning (`/gsd:research-phase`):**
- **Phase 2 (Result Parsing):** TAP and LTP output formats need validation against the actual Docker image's prove/runltp versions. The regex patterns in STACK.md are written from documentation sources -- spot-check against real output before implementation. Confidence: MEDIUM.
- **Phase 3 (Notification):** The combined notification format needs UX consideration. Should it be a markdown table? Plain text? HTML table for email? The WeChat webhook has a 20 msg/min rate limit that affects testing. Confidence: HIGH (patterns are established in existing notify.sh).

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (Core Orchestration):** Purely bash function composition inside an existing framework. All called functions are well-understood. The SMOKE_MODE guard pattern is straightforward (wrap 2 lines in `if` block). Confidence: HIGH.
- **Phase 4 (Polish):** Incremental additions to a working system. No architectural decisions needed. Each item is a self-contained flag or output format change.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Zero new dependencies. Existing bash/codebase patterns well-understood through direct source analysis. TAP and LTP output formats verified against official specs and real-world project logs. |
| Features | HIGH | Features derived from PROJECT.md milestone definition + competitive analysis of pytest/LTP runltp. MVP scope is clearly bounded. Anti-features identified proactively. |
| Architecture | HIGH | Direct source analysis of all 4 relevant files (wrapper, entrypoint, notify.sh, Dockerfile). Three options evaluated with explicit rejection rationale. Build order dependency graph validated. |
| Pitfalls | HIGH | 10 pitfalls categorized by severity with specific code-level mitigations. Sources verified against LTP official docs, Perl Test::Harness format docs, and existing codebase patterns. "Looks Done But Isn't" checklist covers 9 validation points. |

**Overall confidence: HIGH**

Note: The STACK.md research recommends a different architectural approach (multi-container) than ARCHITECTURE.md (single-container hybrid). This synthesis resolves the divergence in favor of ARCHITECTURE.md's Option C, which provides a more detailed analysis of integration points and output directory management. The STACK.md parsing approaches (TAP regex, LTP awk, mdtest criteria) remain valid and are incorporated into Phase 2.

### Gaps to Address

- **TAP output format validation:** The `prove -rv` output format used by `pjdtest_run()` should be spot-checked against the actual Docker image. The TAP v13 spec and Kata Containers real-world logs confirm the format, but the exact prove version in the Ubuntu 24.04 image may differ. **Resolution:** First task in Phase 2 planning -- run `dtt -t pjdtest -s all` and capture sample output for parser testing.
- **LTP version pinning:** The Dockerfile installs LTP from source but does not pin a specific version/commit. A future image rebuild could change the LTP version and alter output format. **Resolution:** Note in Phase 2 to verify parsing against the installed version; consider pinning the LTP commit SHA in Dockerfile.
- **mdtest `-n 8` output format:** The exact format of mdtest output with `-n 8` (very fast, few files) may differ subtly from the standard output format. The SUMMARY rate section should always be present, but operation count extraction regex should be validated. **Resolution:** Run `dtt -t mdtest -s all -n 8` manually and capture output for parser testing before Phase 2 implementation.

## Sources

### Primary (HIGH confidence -- direct codebase analysis)
- `dingofs-testsuite-tool` (823 lines) -- host-side CLI wrapper, config loading, `run_testsuite()` function
- `entrypoint.sh` (1837 lines) -- container entrypoint, all 6 `_run()` functions, `dispatch_tool()`, `parse_args()`
- `scripts/notify.sh` (289 lines) -- WeChat notification (`send_wechat_notification` L201), Email notification (`send_email_notification` L25)
- `Dockerfile` -- all tools installed in single image (fio, vdbench, mdtest, pjdtest, ltp)
- `scripts/generate_report.py` -- existing report generation patterns

### Primary (HIGH confidence -- official documentation)
- TAP v13 Specification (http://testanything.org/) -- pjdtest TAP output line format
- LTP Test Result Reporting (DeepWiki, https://deepwiki.com) -- TPASS/TFAIL/TCONF/TBROK bitmask values, `<<<test_start>>>`/`<<<test_end>>>` block format
- PROJECT.md milestone definition -- "一条 dtt smoke 命令自动串行执行三个测试场景，快速验证存储系统基本健康状态"

### Secondary (MEDIUM confidence -- community/real-world confirmation)
- Kata Containers issue #826 -- real-world pjdfstest/prove output with `Result: FAIL`, `Files=N, Tests=N` footer
- Yocto Project LTP Result Wiki -- LTP summary table format confirmation
- LTP Mailing List (Dec 2022) -- discussion of runltp log output format stability
- OE-Core LTP Parser (Poky) -- reference Python implementation of TPASS/TFAIL/TCONF parsing

---
*Research completed: 2026-05-19*
*Ready for roadmap: yes*
*Architecture divergence resolved: Option C (single-container hybrid) supersedes STACK.md multi-container recommendation*
