---
name: int quota email parsing bug
description: Email details should be formatted as table with proper fields, not plain text with duplicate failed test list
type: debug
status: resolved
date: 2026-04-24
---

# Debug: int quota email formatting bug

## Issue

**Command:** `dtt -t int -s quota --email`
**Problem:**
1. Failed tests appear TWICE - once in "详情:" line and again in "失败用例:" section
2. Details not formatted as a table

**Expected:**
- Details formatted as HTML table with: Total, Passed, Failed, Pass Rate, Failed Test Details
- Failed tests appear ONCE

## Root Cause

1. `entrypoint.sh` (lines 1480-1483) builds `details` string with failed tests appended:
   ```
   details="Total: $int_total, Passed: $int_passed, Failed: $int_failed. Failed: ${failed_tests}"
   ```

2. `notify.sh` displayed full `details` as plain text AND then extracted and displayed failed tests AGAIN, causing duplication.

## Resolution

**Root Cause:** The failed tests were being displayed twice because:
- First in the plain text `details` string (line 64: `<p><b>详情:</b> $details</p>`)
- Second via the extract logic (lines 68-75)

**Fix Applied in `scripts/notify.sh`:**

Replaced the duplicate plain-text display with proper HTML table parsing:

1. Parse `details` string to extract: Total, Passed, Failed, Pass Rate
2. Extract failed test names once from `.Failed: ` separator
3. Build HTML table with proper structure:
   - 用例总数 (Total)
   - 通过用例数 (Passed)
   - 失败用例数 (Failed)
   - 通过率 (Pass Rate)
   - 失败用例详情 (Failed Tests) - only if there are failures

**Files Changed:**
- `scripts/notify.sh` - Rewrote `send_email_notification()` to parse details and build proper HTML table

## Verification

Run `dtt -t int -s quota --email` and check received email:
- Should show table with Total, Passed, Failed, Pass Rate rows
- Failed tests should appear ONCE in the "失败用例详情" row
- No duplicate "详情:" plain text section