---
phase: 02-core-functionality
plan: 02-02
subsystem: entrypoint
tags: [entrypoint, cli, docker, orchestration]
dependency_graph:
  requires:
    - "01-01 (Dockerfile)"
  provides:
    - "Unified entrypoint.sh with CLI parsing and tool dispatch"
  affects:
    - "entrypoint.sh"
tech_stack:
  added:
    - bash scripting
    - getopt for CLI parsing
  patterns:
    - Single entrypoint with mode handling
    - Tool dispatch pattern
    - Custom config override via /custom/
key_files:
  created:
    - entrypoint.sh
decisions:
  - "D-07: CLI uses -t/--tool, -s/--scenario, -m/--mount, -o/--output"
  - "D-08: -- separator between Docker args and app args"
  - "D-16: Two run modes (one-shot and long-running)"
  - "D-17: Default is one-shot"
  - "D-18: entrypoint.sh"
  - "D-20: -h/--help for usage information"
metrics:
  duration: "~2 minutes"
  completed: "2026-04-03T18:20:00Z"
---

# Phase 02 Plan 02: Unified Entrypoint Summary

## One-liner

Created unified entrypoint.sh that parses CLI arguments, handles one-shot and long-running modes, dispatches to fio/vdbench/mdtest, and supports custom config overrides.

## What Was Built

**entrypoint.sh** - A comprehensive bash script that serves as the unified entrypoint for the DingoFS Storage Benchmark Tools Docker image.

### Features Implemented

1. **CLI Parsing (parse_args)**
   - Short options: -t, -s, -m, -o, -h
   - Long options: --tool, --scenario, --mount, --output, --mode, --help
   - Handles `--` separator between Docker and application arguments
   - Uses getopt for robust argument parsing

2. **Help System (show_help)**
   - Clear usage information
   - Lists all options with descriptions
   - Shows scenario options per tool
   - Provides docker run examples
   - Documents custom config override

3. **Parameter Validation (validate_params)**
   - Validates tool is one of: fio, vdbench, mdtest
   - Validates scenario exists (checks /custom/ override first, then /scenarios/)
   - Validates mount point exists
   - Validates output directory is creatable
   - Validates mode is one-shot or long-running
   - Clear error messages for each validation failure

4. **Tool Dispatch (dispatch_tool, fio_run, vdbench_run, mdtest_run)**
   - Routes to correct tool based on -t argument
   - fio_run: Uses fio with config file, outputs JSON
   - vdbench_run: Changes to /opt/vdbench, runs with -f and -o flags
   - mdtest_run: Direct mdtest execution with -d flag for directory

5. **Mode Handling (run_one_shot, run_long_running)**
   - one-shot: Executes test and exits with test's exit code
   - long-running: Executes test, then stays alive with tail -f /dev/null
   - Provides docker exec instructions in long-running mode
   - Handles SIGTERM gracefully for docker stop

6. **Custom Config Override**
   - Checks /custom/ directory first before built-in /scenarios/
   - fio: /custom/{scenario}.fio or /custom/{scenario}.conf
   - vdbench: /custom/{scenario}.par
   - Allows users to mount their own configs

## Verification

| Check | Status |
|-------|--------|
| Syntax check (bash -n) | PASSED |
| Help output (-h, --help) | PASSED |
| Invalid tool error | PASSED |
| Invalid scenario error | PASSED |
| Required functions exist | PASSED (9/9) |

## Files Modified

| File | Lines | Purpose |
|------|-------|---------|
| entrypoint.sh | 416 | Unified entrypoint script |

## Commits

- `a23a3bd` - feat(02-02): create unified entrypoint.sh with CLI parsing

## Deviations from Plan

(None - plan executed exactly as written)

## Requirements Covered

| Requirement | Status |
|-------------|--------|
| PARM-01 (CLI short options) | Implemented |
| PARM-02 (CLI long options) | Implemented |
| PARM-03 (Mount point) | Implemented |
| PARM-04 (Output path) | Implemented |
| PARM-05 (Tool argument) | Implemented |
| PARM-06 (Validation) | Implemented |
| MODE-01 (One-shot mode) | Implemented |
| MODE-02 (Long-running mode) | Implemented |
| MODE-03 (docker exec support) | Implemented |
| ENTRY-01 (Entrypoint script) | Implemented |
| ENTRY-02 (Help text) | Implemented |
| ENTRY-04 (Error messages) | Implemented |

## Self-Check: PASSED

- entrypoint.sh exists at project root
- Commit a23a3bd found in git history
- All 9 required functions present
- Syntax check passed
