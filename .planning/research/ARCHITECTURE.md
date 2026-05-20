# Architecture Research: dtt smoke Command Integration

**Domain:** Storage test orchestration (smoke test command for existing containerized test tools)
**Researched:** 2026-05-19
**Confidence:** HIGH

## Recommended Architecture: Option C (Hybrid)

**Decision:** The `dtt smoke` command adds a small CLI handler in the dtt wrapper, but all test orchestration, statistics collection, and notification aggregation happens inside a single container via a new `smoke_run()` function in `entrypoint.sh`.

**One-liner rationale:** Option C preserves the existing architectural boundary (wrapper = CLI/config, container = test execution), requires zero structural changes to existing tool `_run()` functions, and enables unified statistics aggregation and a single notification at the end -- which is impossible with a multi-container approach.

## Architecture Options Evaluated

| Option | Description | Verdict |
|--------|-------------|---------|
| A | wrapper calls `run_testsuite()` 3 times, 3 containers | REJECTED |
| B | all orchestration in entrypoint.sh, no wrapper changes | REJECTED |
| C | wrapper = thin CLI handler, entrypoint = smoke orchestrator | RECOMMENDED |

### Option A: Multi-Container (Wrapper-side Orchestration)

```
dtt smoke
  -> for tool in pjdtest mdtest ltp:
       run_testsuite -t $tool -s $scenario ...   # launches new container each time
```

**Rejected because:**

1. **3 containers = 3 RUN_TIMESTAMPs.** Output directories are scattered: `pjdtest_20260519_100000/`, `mdtest_20260519_100500/`, `ltp_20260519_101000/` -- no way to group smoke results together under a unified `smoke_` prefix without fragile post-hoc directory renaming in the wrapper.

2. **Per-tool notification only.** Each `_run()` function independently fires `send_wechat_notification()`. The user who runs `dtt smoke --wechat` would get 3 separate WeChat messages, not a single combined summary. Changing this would require threading notification state across container boundaries, which ephemeral docker containers do not support.

3. **No cross-tool statistics.** Aggregating pass/fail/skip counts from three separate container exits requires parsing stdout or output files from outside the containers -- fragile and reimplements logic that `notify.sh` already handles.

4. **Container startup overhead.** Each `run_testsuite()` invocation does a full `docker run` with image loading, volume mounting, and `--privileged` setup. For three quick smoke tests, this is 3x unnecessary overhead.

5. **`run_testsuite()` is single-invocation by design.** It validates, echoes, launches docker, and exits. It is not structured as a reusable sub-function for iterative calling. The mlperf case even uses `exec` to replace the shell process entirely.

### Option B: Pure entrypoint.sh (No Wrapper Changes)

```
dtt smoke  # add a new case in dingofs-testsuite-tool() main entry
  -> run_testsuite -t smoke    # reuse existing container path
  -> container: dispatch_tool -> smoke_run()
```

**Rejected because the premise is false.** The dtt wrapper MUST change to recognize `dtt smoke` as a valid command. The main dispatch in `dingofs-testsuite-tool()` currently only matches `config`, `debug`, `help`, and option-starting args (`-t`, `-s`, etc.). Adding `smoke` to the case statement (and a `cmd_smoke()` handler) is required regardless of where the orchestration lives. There is no "pure entrypoint-only" option that avoids wrapper changes entirely.

### Option C: Hybrid (RECOMMENDED)

```
dtt smoke [--wechat] [--email] [--debug]
  -> dtt wrapper: new cmd_smoke() handler
       -> builds docker command: entrypoint.sh -t smoke
       -> passes notification flags as env vars (WECHAT, EMAIL)
  -> container: dispatch_tool adds "smoke" case -> smoke_run()
       -> smoke_run():
           1. pjdtest_run()  (reuse existing, notification guarded by SMOKE_MODE)
           2. mdtest scenarios (run with n=8, notification guarded by SMOKE_MODE)
           3. ltp_run() with s=smoke (reuse existing, notification guarded by SMOKE_MODE)
           4. parse each tool's output for pass/fail/skip counts
           5. write unified smoke summary (smoke_summary.json, smoke_summary.txt)
           6. send ONE combined WeChat/email notification
```

**Chosen because:**

1. **Single container, single timestamp.** Output goes to `$OUTPUT/smoke_<RUN_TIMESTAMP>/` with subdirectories per tool, all sharing the same timestamp -- easy to find, archive, and correlate.

2. **Statistics aggregation is natural.** All results are in memory (bash variables) within the same process. Pass/fail/skip/total can be accumulated across tools and reported in one table.

3. **Single combined notification.** One WeChat/email message with a summary table showing all three tools at once, instead of three separate pings.

4. **Existing `_run()` functions are reused but wrapped.** `pjdtest_run()`, `mdtest_run()`, and `ltp_run()` all work standalone and produce output in consistent locations. `smoke_run()` calls them sequentially with a `SMOKE_MODE` env guard that suppresses individual notifications.

5. **Minimal wrapper changes.** Only a new `smoke` case in the main command dispatcher and a `cmd_smoke()` function to build the docker command. The 600+ line `run_testsuite()` function is untouched.

6. **All tools already coexist in the same image.** The Dockerfile installs fio, vdbench, mdtest, pjdtest, ltp, and integration tools into a single image. No multi-image considerations needed.

## System Overview

```
+-----------------------------------------------------------------+
|                    dtt Wrapper (Host)                             |
|  dingofs-testsuite-tool                                          |
+-----------------------------------------------------------------+
|  +----------+  +----------+  +----------+  +---------------+   |
|  | config   |  | debug    |  | -t/--tool|  | smoke (NEW)   |   |
|  | handler  |  | handler  |  | handler  |  | handler       |   |
|  +----+-----+  +----+-----+  +----+-----+  +-------+-------+   |
|       |             |             |                 |            |
|       |        docker run     docker run       docker run        |
|       |        --privileged   --privileged     --privileged      |
|       |        + bash         + entrypoint     + entrypoint      |
|       |                          -t tool         -t smoke        |
+-------+----------------------------------------------------------+
|                 Container (dingofs-testsuite-tools image)         |
+------------------------------------------------------------------+
|  +----------------------------------------------------------+    |
|  |                    entrypoint.sh                           |    |
|  |  +----------+  +----------+  +-----------------------+   |    |
|  |  |dispatch  |  | fio_run  |  | smoke_run (NEW)       |   |    |
|  |  |_tool()   |  | vdbench_ |  |  +-- pjdtest_run()    |   |    |
|  |  |  case:   |  | run()    |  |  +-- mdtest (n=8)     |   |    |
|  |  |  fio     |  | mdtest_  |  |  +-- ltp_run(smoke)   |   |    |
|  |  |  vdbench |  | run()    |  |  +-- stats aggregate  |   |    |
|  |  |  mdtest  |  | pjdtest_ |  |  +-- combined notify  |   |    |
|  |  |  pjdtest |  | run()    |  +-----------------------+   |    |
|  |  |  ltp     |  | ltp_run()|                               |    |
|  |  |  int     |  | int_run()|                               |    |
|  |  |  mlperf  |  | mlperf_  |                               |    |
|  |  |  smoke   |  | run()    |                               |    |
|  |  |  (NEW)   |  +----------+                               |    |
|  |  +----------+                                              |    |
|  +----------------------------------------------------------+    |
|                                                                  |
|  +----------+  +----------+  +----------+  +---------------+   |
|  | pjdtest  |  | mdtest   |  | ltp      |  | notify.sh     |   |
|  | binary   |  | binary   |  | binary   |  | (wechat/email)|   |
|  +----------+  +----------+  +----------+  +---------------+   |
|                                                                  |
|  +-----------------------------------------------------------   |
|  | /output/smoke_<RUN_TIMESTAMP>/                               |
|  |   +-- pjdtest_all/                                           |
|  |   |   +-- pjdtest_<ts>              (raw output)             |
|  |   |   +-- results.log                                       |
|  |   +-- mdtest_all_n8/                                        |
|  |   |   +-- mdtest_z0_n100/          (scenario outputs)      |
|  |   |   +-- mdtest_z5_b4_I1/                                 |
|  |   |   +-- mdtest_z6_b3_I1/                                 |
|  |   |   +-- mdtest_z9_b2_I1/                                 |
|  |   |   +-- combined_report.html                              |
|  |   +-- ltp_smoke/                                            |
|  |   |   +-- ltp_<ts>_smoketest.log                            |
|  |   +-- smoke_summary.json           (aggregated stats)       |
|  |   +-- smoke_summary.txt            (human-readable)         |
|  +-----------------------------------------------------------   |
+------------------------------------------------------------------+
```

## Component Responsibilities

| Component | Location | Responsibility | Changes Needed |
|-----------|----------|----------------|----------------|
| `cmd_smoke()` | dtt wrapper (new) | CLI parsing for `dtt smoke`, builds docker command, passes env vars for --wechat/--email/--debug | NEW function |
| `smoke` case in `dingofs-testsuite-tool()` | dtt wrapper | Dispatches `smoke` keyword to `cmd_smoke()` | NEW case branch |
| `show_smoke_help()` | dtt wrapper (new) | Help text for `dtt smoke --help` | NEW function |
| `smoke` case in `parse_args()` | entrypoint.sh | Validates `-t smoke` as a recognized tool | NEW case in existing validation |
| `smoke)` case in `dispatch_tool()` | entrypoint.sh | Routes to `smoke_run()` | NEW case in existing switch |
| `smoke_run()` | entrypoint.sh (new) | Orchestrates 3 test tools sequentially, aggregates statistics, writes unified output, sends single notification | NEW function |
| `pjdtest_run()` | entrypoint.sh (existing) | POSIX test execution, produces output at standard path | MODIFY: add `SMOKE_MODE` guard around notification calls |
| `mdtest_run()` | entrypoint.sh (existing) | Metadata test execution with per-scenario subdirs | MODIFY: add `SMOKE_MODE` guard around notification calls |
| `ltp_run()` | entrypoint.sh (existing) | LTP test execution, already supports `smoke` scenario | MODIFY: add `SMOKE_MODE` guard around notification calls |
| `notify.sh` | scripts/notify.sh (existing) | WeChat/email sending primitives | NO CHANGE (reused as-is) |
| `Dockerfile` | repo root (existing) | All tools already installed in single image | NO CHANGE |

## Integration Points

### Wrapper-to-Container Boundary

```
WRAPPER (host)                         CONTAINER (image)
============================================================================
cmd_smoke()
  +-- load_config image/testdir/output
  +-- validate mount/output exist
  +-- build docker_cmd:
  |    $runtime run --rm --privileged
  |      -v ${mount}:/data
  |      -v ${output}:/output
  |      -e WECHAT=${wechat}           ->  entrypoint.sh reads $WECHAT
  |      -e EMAIL=${email}             ->  entrypoint.sh reads $EMAIL
  |      -e WEBHOOK_URL=${webhook}     ->  notify.sh reads $WEBHOOK_URL
  |      -e EMAIL_TO=${email_addr}     ->  notify.sh reads $EMAIL_TO
  |      ${image}
  |      -t smoke -m /data -o /output
  |
  +-- execute docker_cmd -------> main() -> dispatch_tool() -> smoke_run()
```

### Existing `_run()` Function Contract

Each existing `_run()` function follows this pattern. `smoke_run()` must adhere to it when composing:

```
1. Create output dir: $OUTPUT/<tool>_<RUN_TIMESTAMP>/$SCENARIO
2. Execute test binary against $MOUNT
3. Call log_result() with tool, scenario, exit code, start time, output dir
4. Calculate duration
5. [GUARDED] send_wechat_notification() if WECHAT_ENABLED and not SMOKE_MODE
6. [GUARDED] send_email_notification() if EMAIL_ENABLED and not SMOKE_MODE
7. Return exit code
```

**Key design decision -- SMOKE_MODE guard:** When called from `smoke_run()`, individual notifications (steps 5-6) must be skipped. The approach is:

- `smoke_run()` sets `SMOKE_MODE=1` before calling each `_run()`
- Each `_run()` checks `[[ "$SMOKE_MODE" != "1" ]]` before sending notifications
- This requires 3 modifications, each adding one `if` guard (2 notification blocks each = 6 total guards across 3 functions)
- Zero changes to notification content or tool execution logic

This is the minimal-touch approach. It avoids duplicating `_run()` bodies in `smoke_run()` while giving smoke full control over notification timing and content.

### Output Directory Structure

```
$OUTPUT/smoke_<RUN_TIMESTAMP>/          # All smoke tests under unified prefix
  +-- pjdtest_all/                      # pjdtest results
  |   +-- pjdtest_<ts>
  +-- mdtest_all_n8/                    # mdtest results (n=8)
  |   +-- mdtest_z0_n100/
  |   +-- mdtest_z5_b4_I1/
  |   +-- mdtest_z6_b3_I1/
  |   +-- mdtest_z9_b2_I1/
  +-- ltp_smoke/                        # LTP smoke results
  |   +-- ltp_<ts>_smoketest.log
  +-- smoke_summary.json                # Machine-readable aggregate
  +-- smoke_summary.txt                 # Human-readable aggregate
```

### How smoke_run() Produces Exact Output Paths

The existing `_run()` functions use `$OUTPUT` and `$RUN_TIMESTAMP` to build their output paths:
- `pjdtest_run()`: `mkdir -p "$OUTPUT/pjdtest_${RUN_TIMESTAMP}/$SCENARIO"` -> writes to `$OUTPUT/pjdtest_<ts>/all/`
- `mdtest_run()`: `mkdir -p "$OUTPUT/mdtest_${RUN_TIMESTAMP}"` -> writes to `$OUTPUT/mdtest_<ts>/`
- `ltp_run()`: `mkdir -p "$OUTPUT/ltp_${RUN_TIMESTAMP}/$SCENARIO"` -> writes to `$OUTPUT/ltp_<ts>/smoke/`

**The problem:** Each function uses its own tool name in the path (`pjdtest_`, `mdtest_`, `ltp_`), not a unified `smoke_` prefix.

**The fix:** `smoke_run()` temporarily overrides `$OUTPUT` before each call:

```bash
smoke_run() {
    local RUN_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    local SMOKE_BASE="$OUTPUT/smoke_${RUN_TIMESTAMP}"
    mkdir -p "$SMOKE_BASE"

    # Before each _run(), redirect OUTPUT to smoke subdirectory
    local SAVED_OUTPUT="$OUTPUT"

    OUTPUT="$SMOKE_BASE" pjdtest_run   # writes to smoke_<ts>/pjdtest_<ts>/all/
    OUTPUT="$SMOKE_BASE" TOOL_SCENARIO="all" mdtest_run  # writes to smoke_<ts>/mdtest_<ts>/
    OUTPUT="$SMOKE_BASE" SCENARIO="smoke" ltp_run  # writes to smoke_<ts>/ltp_<ts>/smoke/

    OUTPUT="$SAVED_OUTPUT"
    # ... aggregate, notify ...
}
```

## Data Flow

### Smoke Command Execution Flow

```
User: dtt smoke --wechat
  |
  v
dingofs-testsuite-tool()
  |  case "smoke": cmd_smoke "$@"
  v
cmd_smoke()
  |  Parse --wechat, --email, --debug flags
  |  Load config (image, testdir, output, webhook_url, email)
  |  Build docker run command
  |  Execute container
  v
[Container starts]
  |
  v
main() -> parse_args -> dispatch_tool()
  |  case "smoke": smoke_run
  v
smoke_run()
  |
  +-- 1. RUN_TIMESTAMP = now (shared across all 3 tools)
  |     SMOKE_BASE = $OUTPUT/smoke_$RUN_TIMESTAMP
  |     export SMOKE_MODE=1
  |
  +-- 2. OUTPUT=$SMOKE_BASE pjdtest_run()
  |     -> writes to $SMOKE_BASE/pjdtest_<ts>/all/
  |     -> captures exit code
  |     -> parse results.log for pass/fail/skip/total counts
  |
  +-- 3. OUTPUT=$SMOKE_BASE mdtest_run()  [with NP=8, SCENARIO=all]
  |     -> iterate scenario scripts with $MDTEST_NP=8
  |     -> writes to $SMOKE_BASE/mdtest_<ts>/
  |     -> captures per-scenario exit codes
  |     -> parse mdtest.raw outputs for stats
  |
  +-- 4. OUTPUT=$SMOKE_BASE ltp_run()     [with SCENARIO=smoke]
  |     -> writes to $SMOKE_BASE/ltp_<ts>/smoke/
  |     -> captures exit code
  |     -> parse LTP results for pass/fail/skip counts
  |
  +-- 5. Aggregate statistics
  |     TOOL       TOTAL  PASS  FAIL  SKIP  STATUS
  |     pjdtest    94     90    4     0     FAIL
  |     mdtest     4      4     0     0     SUCCESS
  |     ltp        12     10    1     1     FAIL
  |     =========================================
  |     Overall    110    104   5     1     FAIL
  |
  +-- 6. Write unified output
  |     -> $SMOKE_BASE/smoke_summary.json
  |     -> $SMOKE_BASE/smoke_summary.txt
  |
  +-- 7. Send ONE combined notification
        -> send_wechat_notification "smoke" "all" "$overall_status" "$duration" "$stats_details"
        -> send_email_notification "smoke" "all" "$overall_status" "$duration" "$stats_details"

  Exit with 0 if all passed, 1 if any failed
```

### Notification Flow (Before vs After)

```
BEFORE (individual tool invocation):
  +------------+
  | dtt -t pjdtest -s all --wechat
  +----+-------+
       |  docker run ... -> entrypoint.sh -t pjdtest
       v
  pjdtest_run() -> send_wechat_notification("pjdtest", ...)
  Container exits. Notification sent (1 ping).

AFTER (smoke invocation):
  +------------+
  | dtt smoke --wechat
  +----+-------+
       |  docker run ... -> entrypoint.sh -t smoke
       v
  smoke_run()
    +-- pjdtest_run() -> (notification SKIPPED, SMOKE_MODE=1)
    +-- mdtest_run()  -> (notification SKIPPED, SMOKE_MODE=1)
    +-- ltp_run()     -> (notification SKIPPED, SMOKE_MODE=1)
    +-- send_wechat_notification("smoke", "all", ..., combined_stats)
    +-- send_email_notification("smoke", "all", ..., combined_stats)
       Container exits. ONE notification with all 3 tools' results.
```

## Architectural Patterns

### Pattern 1: Command Handler Dispatch (Wrapper)

**What:** The dtt wrapper uses a flat `case "$command"` dispatch with dedicated handler functions. New commands follow this same pattern.

**Used by:** `config`, `debug`, `help`, implicit `-t` handler (which calls `run_testsuite()`)

**Example (for smoke):**
```bash
dingofs-testsuite-tool() {
    local command="$1"
    case "$command" in
        config)   shift; cmd_config "$@" ;;
        debug)    cmd_debug ;;
        smoke)    shift; cmd_smoke "$@" ;;    # NEW
        help|--help|-h) show_help ;;
        ...
    esac
}
```

### Pattern 2: Tool Dispatch (Container)

**What:** `dispatch_tool()` in entrypoint.sh maps tool names to `_run()` functions. New tools add a case.

**Example (for smoke):**
```bash
dispatch_tool() {
    case "$TOOL" in
        fio)     fio_run ;;
        vdbench) vdbench_run ;;
        mdtest)  mdtest_run ;;
        pjdtest) pjdtest_run ;;
        ltp)     ltp_run ;;
        int|integration) integration_run ;;
        mlperf)  mlperf_run ;;
        smoke)   smoke_run ;;    # NEW
        *)       echo "Error: Unknown tool '$TOOL'"; exit 1 ;;
    esac
}
```

### Pattern 3: Notification Guard for Orchestrated Mode

**What:** Existing `_run()` functions check `$SMOKE_MODE` before sending notifications. This allows `smoke_run()` to call them without triggering N separate notifications.

**Example (modification to pjdtest_run, mdtest_run, ltp_run):**
```bash
# In pjdtest_run(), mdtest_run(), ltp_run():
# Replace existing notification blocks with guarded versions:

if [[ "$SMOKE_MODE" != "1" ]]; then
    if [[ "$WECHAT_ENABLED" == "yes" ]]; then
        send_wechat_notification "pjdtest" "pjdtest" "$status" "$duration"
    fi
    if [[ "$EMAIL_ENABLED" == "yes" ]]; then
        send_email_notification "pjdtest" "pjdtest" "$status" "$duration"
    fi
fi
```

### Pattern 4: OUTPUT Override for Subdirectory Grouping

**What:** `smoke_run()` temporarily changes `$OUTPUT` to `$OUTPUT/smoke_<ts>` before calling each `_run()`, so all output lands under the unified `smoke_` prefix. The original value is restored after.

**Example:**
```bash
smoke_run() {
    local RUN_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    local SMOKE_BASE="$OUTPUT/smoke_${RUN_TIMESTAMP}"
    mkdir -p "$SMOKE_BASE"

    local SAVED_OUTPUT="$OUTPUT"

    # Each _run() creates its own <tool>_<ts> subdir under SMOKE_BASE
    OUTPUT="$SMOKE_BASE" pjdtest_run
    OUTPUT="$SMOKE_BASE" SCENARIO="all" mdtest_run
    OUTPUT="$SMOKE_BASE" SCENARIO="smoke" ltp_run

    OUTPUT="$SAVED_OUTPUT"
    # ... aggregate, write summary, notify ...
}
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Multi-Container Orchestration (Option A)

**What people do:** Call `run_testsuite()` in a loop from the wrapper, launching separate containers for each smoke test.

**Why it's wrong:**
- 3 containers = 3 separate RUN_TIMESTAMPs, output scattered across different directories
- Each container independently sends notifications (3 WeChat pings instead of 1)
- No shared memory for cross-tool statistics aggregation
- Docker startup overhead for each tool invocation

**Do this instead:** Use Option C -- single container, sequential execution, aggregated output.

### Anti-Pattern 2: Duplicating `_run()` Logic in `smoke_run()`

**What people do:** Copy-paste the body of `pjdtest_run()`, `mdtest_run()`, and `ltp_run()` into `smoke_run()` instead of calling the functions.

**Why it's wrong:**
- Any future fixes to pjdtest/mdtest/ltp execution logic must be duplicated into smoke
- Drift risk: smoke copy diverges from original over time
- Increased code surface area for bugs

**Do this instead:** Call existing `_run()` functions from `smoke_run()`, using `SMOKE_MODE=1` and OUTPUT override.

### Anti-Pattern 3: Individual Notifications During Smoke

**What people do:** Let `pjdtest_run()`, `mdtest_run()`, and `ltp_run()` each send their own notification during a smoke run.

**Why it's wrong:** The user requested `dtt smoke --wechat` and expects ONE notification with combined results. Getting 3 separate messages is confusing and spammy.

**Do this instead:** Guard notifications in `_run()` with `SMOKE_MODE` check, send one combined notification from `smoke_run()`.

### Anti-Pattern 4: Adding smoke as an Option to run_testsuite()

**What people do:** Add `smoke` as a new tool case inside the existing `run_testsuite()` function alongside fio/vdbench/mdtest handling.

**Why it's wrong:** `run_testsuite()` is a single-tool-per-invocation function. It validates a tool, builds a docker command for that one tool, and executes. Adding an orchestrator that runs multiple tools into this function would conflate two different responsibilities: (a) single-tool container launcher, and (b) multi-tool test orchestrator. The function would grow significantly in complexity with conditional branches.

**Do this instead:** Create `cmd_smoke()` as a separate handler that builds a simpler docker command (no per-tool logic needed -- just `-t smoke`) and lets the container-side `smoke_run()` handle all orchestration. The existing `run_testsuite()` remains focused on single-tool execution.

## Scaling Considerations

This is a sequential test orchestrator run on a single container. Scaling is not a primary concern, but:

| Concern | At smoke scale (3 tools) | If extended to "full" scale (all tools) |
|---------|-------------------------|------------------------------------------|
| Sequential runtime | ~minutes (smoke tests are fast) | ~hours (fio and vdbench take much longer) |
| Output dir size | <10MB (smoke output is small) | >1GB (fio/vdbench produce large raw files) |
| Image size | Already contains all tools | No change (monolithic image) |
| Notification frequency | Once at end | Once at end (same pattern) |
| Tool count | 3 fixed | Extensible via config or additional cases |

## Changes Summary

### New Components

| File | Component | Purpose |
|------|-----------|---------|
| `dingofs-testsuite-tool` | `cmd_smoke()` function | CLI handler: parse args, build docker command, pass env vars |
| `dingofs-testsuite-tool` | `smoke)` case in main dispatch | Route `dtt smoke` to `cmd_smoke()` |
| `dingofs-testsuite-tool` | `show_smoke_help()` function | Help text for `dtt smoke --help` |
| `entrypoint.sh` | `smoke_run()` function | Orchestrate 3 tools, aggregate stats, write unified output, send combined notification |
| `entrypoint.sh` | `smoke)` case in `dispatch_tool()` | Route `-t smoke` to `smoke_run()` |
| `entrypoint.sh` | `smoke)` case in `parse_args()` | Accept `smoke` as valid TOOL value |

### Modified Components

| File | Component | Change | Lines |
|------|-----------|--------|-------|
| `entrypoint.sh` | `pjdtest_run()` | Add `SMOKE_MODE` guard around notification calls | +2 if-blocks |
| `entrypoint.sh` | `mdtest_run()` | Add `SMOKE_MODE` guard around notification calls | +2 if-blocks |
| `entrypoint.sh` | `ltp_run()` | Add `SMOKE_MODE` guard around notification calls | +2 if-blocks |
| `entrypoint.sh` | `validate_params()` | Add `smoke` to valid TOOL regex | +1 line |
| `dingofs-testsuite-tool` | `show_help()` | Add smoke usage example | +2 lines |

### Unchanged Components

| Component | Reason |
|-----------|--------|
| `Dockerfile` | All tools already in image |
| `run_testsuite()` | Smoke uses its own docker command builder (`cmd_smoke()`) |
| `notify.sh` | Reused as-is; smoke composes a single combined message |
| `config` subsystem | Reused as-is for testdir/output/image |
| `fio_run()`, `vdbench_run()`, `int_run()`, `mlperf_run()` | Not part of smoke test suite |
| `cmd_debug()`, `cmd_config()` | Unrelated to smoke |

## Build Order (Dependency-Aware Sequence)

```
Step 1: entrypoint.sh -- Add SMOKE_MODE guards
  +-- pjdtest_run(): wrap notification blocks in if [[ "$SMOKE_MODE" != "1" ]]
  +-- mdtest_run(): wrap notification blocks in if [[ "$SMOKE_MODE" != "1" ]]
  +-- ltp_run(): wrap notification blocks in if [[ "$SMOKE_MODE" != "1" ]]
  DEPENDS ON: nothing
  TESTABLE: run dtt -t pjdtest -s all --wechat (should still notify; guard is inactive)

Step 2: entrypoint.sh -- Add smoke_run() function
  +-- Imports SMOKE_MODE=1, OUTPUT override pattern
  +-- Calls pjdtest_run(), mdtest_run(), ltp_run() in sequence
  +-- Aggregates stats, writes smoke_summary files
  +-- Sends combined notification
  DEPENDS ON: Step 1 (calls guarded functions)
  TESTABLE: source entrypoint.sh and call smoke_run() manually from bash inside container

Step 3: entrypoint.sh -- Wire smoke into dispatch and validation
  +-- dispatch_tool(): add "smoke)" case
  +-- parse_args(): add "smoke" to valid TOOL values
  +-- validate_params(): ensure smoke passes validation
  DEPENDS ON: Step 2 (smoke_run must exist)
  TESTABLE: docker run image -t smoke (will reach smoke_run)

Step 4: dtt wrapper -- Add cmd_smoke() function
  +-- Parse --wechat/--email/--debug flags
  +-- Load config, build docker command with -t smoke
  +-- Pass notification env vars
  DEPENDS ON: Step 3 (container must support -t smoke)
  TESTABLE: source wrapper, call cmd_smoke (or run dtt smoke after Step 5)

Step 5: dtt wrapper -- Wire smoke into main dispatch
  +-- dingofs-testsuite-tool(): add "smoke)" case
  +-- show_help(): add smoke usage example
  DEPENDS ON: Step 4 (cmd_smoke must exist)
  TESTABLE: dtt smoke (full integration test)

Dependency graph:
  Step 1 ──> Step 2 ──> Step 3 ──> Step 4 ──> Step 5
  (Steps 4+5 can happen in parallel with Steps 1-3 if container is built first)
```

## Sources

- Repository code analysis of `dingofs-testsuite-tool` (dtt wrapper, 823 lines) -- HIGH confidence (direct source inspection)
- Repository code analysis of `entrypoint.sh` (container entrypoint, 1837 lines) -- HIGH confidence (direct source inspection)
- Repository code analysis of `scripts/notify.sh` (notification script, 290 lines) -- HIGH confidence (direct source inspection)
- Repository code analysis of `Dockerfile` (all tools in single image) -- HIGH confidence (direct source inspection)
- Project milestone definition at `.planning/PROJECT.md` (v1.5 smoke test milestone) -- HIGH confidence (project authority)

---
*Architecture research for: dtt smoke command integration*
*Researched: 2026-05-19*
