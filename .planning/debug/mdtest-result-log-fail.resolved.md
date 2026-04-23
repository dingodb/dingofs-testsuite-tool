---
status: verifying
trigger: "mdtest result.log shows Status: FAIL but the test actually succeeded"
created: 2026-04-17T00:00:00Z
updated: 2026-04-17T00:00:00Z
---

## Current Focus
hypothesis: "The regex in log_result expects decimal numbers ([0-9]+\\.[0-9]+) but the summary table uses integers for file counts (e.g., 3200 not 3200.000), causing the pattern to never match"
test: "Verify that integer values in summary table don't match the decimal-only regex"
expecting: "The summary row '| mdtest_z0_n100 | 0 | - | - | 3200 | 成功 |' fails to match because 3200 has no decimal point"
next_action: "Fix the regex in log_result to accept both integers and decimals"
---

## Symptoms
expected: mdtest test succeeds and result.log shows Status: SUCCESS
actual: result.log shows Status: FAIL even when test succeeded
reproduction: Run dtt -t mdtest -s all and check result.log
started: Issue appeared after recent changes to organize output into subdirectories
---

## Eliminated
<!-- No hypotheses eliminated yet -->

## Evidence
- timestamp: 2026-04-17T00:00:00Z
  checked: "entrypoint.sh log_result function for mdtest"
  found: "log_result looks for summary_file using: ls \"$output_dir\"/mdtest_mdtest_summary_*.md"
  implication: "Checks for file named mdtest_mdtest_summary_*.md"

- timestamp: 2026-04-17T00:00:00Z
  checked: "entrypoint.sh mdtest_run function"
  found: "generate_report.py called with --scenario \"mdtest\" regardless of actual SCENARIO value"
  implication: "Combined summary filename uses 'mdtest' as scenario_str"

- timestamp: 2026-04-17T00:00:00Z
  checked: "generate_report.py main() and filename construction"
  found: "txt_filename = f\"{tool}_{scenario_str}_summary_{timestamp}.md\" -> mdtest_mdtest_summary_TIMESTAMP.md"
  implication: "Filename pattern matches what log_result expects: mdtest_mdtest_summary_*.md"

- timestamp: 2026-04-17T00:00:00Z
  checked: "Testing log_result regex pattern against actual table rows"
  found: "Summary table row '| mdtest_z0_n100 | 0 | ...' does NOT match regex '\|[[:space:]]+[a-zA-Z_ ]+[[:space:]]+\|[[:space:]]+[0-9]+\.[0-9]+[[:space:]]+\|' because [a-zA-Z_ ]+ doesn't include digits"
  implication: "The summary table row with scenario name fails to match, causing status=FAIL even when test succeeded"

- timestamp: 2026-04-17T00:00:00Z
  checked: "Detail table row format in combined report"
  found: "Detail row '| File creation | 26100.313 | ...' DOES match the regex pattern"
  implication: "The detail rows would pass the check, but they come from parse_mdtest_summary which may not find any operations if mdtest output format differs"

## Resolution
root_cause: "The regex in log_result() for mdtest expected decimal numbers only ([0-9]+\\.[0-9]+) but the summary table in the combined report uses integers (e.g., 3200 files) without decimal points, so the pattern never matched"
fix: "Changed regex from '\|[[:space:]]+[a-zA-Z_ ]+[[:space:]]+\|[[:space:]]+[0-9]+\\.[0-9]+[[:space:]]+\|' to '\|[[:space:]]+[a-zA-Z0-9_ ]+[[:space:]]+\|[[:space:]]+[0-9]+(\\.[0-9]+)?[[:space:]]+\|' which allows both integers and decimals, and also allows digits in the first column"
verification: "Tested regex against both summary table row (| mdtest_z0_n100 | 0 | - | - | 3200 |) and detail row (| File creation | 26100.313 | ...) - both now match. However, full end-to-end verification requires running mdtest which needs MPI and actual filesystem."
files_changed: ["/mnt/disk5/daigy/dingofs-testsuite-tool/entrypoint.sh"]
