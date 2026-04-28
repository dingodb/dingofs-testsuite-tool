---
name: Fix BS_SIZE=small path and size
description: Fix scenario_exists and get_scenario_paths for BS_SIZE=small, change small scenario filesize to 400M
type: quick
gsd_quick: true
date: 2026-04-24
phase: v1.3 notification feature
status: completed
---

# Fix BS_SIZE=small Path and Filesize

## Problem

1. `dtt -t fio -s all --bs_size small` returned "Error: No scenario found for 'all'"
2. Small block size fio scenarios had size=8G instead of size=400M

## Root Cause

1. `scenario_exists()` function hardcoded `/scenarios/fio/` path - did not handle BS_SIZE=small case
2. Generator script output to wrong directory (`scenarios/fio/fio_small` instead of `scenarios/fio_small`)

## Changes

### 1. entrypoint.sh - scenario_exists function (line ~396)

Added BS_SIZE=small handling to use `/scenarios/fio_small` directory:

```bash
fio)
    local fio_scenarios_dir="/scenarios/fio"
    if [[ "$BS_SIZE" == "small" ]]; then
        fio_scenarios_dir="/scenarios/fio_small"
    fi
    # Accept "all" to run all scenarios
    if [[ "$scenario" == "all" ]]; then
        return 0
    fi
    # Check exact match first
    if [[ -f "/custom/${scenario}.fio" ]] || [[ -f "/custom/${scenario}.conf" ]] || [[ -f "${fio_scenarios_dir}/${scenario}.fio" ]]; then
        return 0
    fi
    # Check for prefix matches
    if [[ -n "$(ls "${fio_scenarios_dir}/${scenario}"_*.fio 2>/dev/null | head -1)" ]]; then
        return 0
    fi
    return 1
```

### 2. entrypoint.sh - get_scenario_paths function (line ~448)

Already had correct BS_SIZE handling via SCENARIOS_DIR override in fio_run().

### 3. scenarios/fio/gen_fio_scenarios_small.sh

Changed OUTPUT_DIR from `${SCRIPT_DIR}/fio_small` to `${SCRIPT_DIR}/../fio_small` to output to correct location.

Also changed `size=8G` to `size=400M`.

## Verification

```bash
dtt -t fio -s all --bs_size small
# Now finds 224 scenarios and runs correctly
```

## Files Modified

- entrypoint.sh: scenario_exists function
- scenarios/fio/gen_fio_scenarios_small.sh: OUTPUT_DIR path and size value
