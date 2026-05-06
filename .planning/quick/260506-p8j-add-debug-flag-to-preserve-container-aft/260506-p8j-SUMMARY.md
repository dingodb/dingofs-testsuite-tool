# Quick Task 260506-p8j: Summary

**Description:** add --debug flag to preserve container after test
**Date:** 2026-05-06
**Status:** Complete

## Changes

- Added `debug=""` local variable in `run_testsuite()`
- Added `--debug)` case in argument parsing while loop
- Conditionally omit `--rm` from docker run for both general flow and mlperf flow
- Added `--debug` to `show_help()` options
- Added `--debug` to main entry point case pattern

## Behavior

| Command | Docker flag | Container |
|---------|------------|-----------|
| `dtt -t int -s quota` | `--rm` | Auto-deleted |
| `dtt -t int -s quota --debug` | no `--rm` | Preserved |
