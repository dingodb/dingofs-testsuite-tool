---
status: investigating
trigger: "dtt -t fio -s all --bs_size small runs tests with correct small block sizes but summary report shows normal block sizes"
created: 2026-04-27T00:00:00Z
updated: 2026-04-27T00:00:00Z
---

## Current Focus
hypothesis: "parse_fio_scenario_name() regex does not match small block size scenario names (128, 256, 512 without k/m suffix), causing ALL data to be silently discarded"
test: "Python test showing original regex returns None for 'seq_read_0d_128_1j' and similar"
expecting: "Confirmation that regex fix resolves the data lookup issue"
next_action: "Run end-to-end test to verify small block size data now appears in summary report"

## Symptoms
expected: fio_all_summary_*.md should contain test results for small block sizes: 128B, 256B, 512B, 1K, 2K, 4K, 8K
actual: Report shows "-" for all data cells (no data displayed)
errors: No error messages, all data cells show "-" instead of actual values
reproduction: Run dtt -t fio -s all --bs_size small, then check fio_all_summary_*.md
started: Unknown

## Eliminated

## Evidence
- timestamp: 2026-04-27
  checked: "entrypoint.sh fio_run() function"
  found: "Lines 787-798: BS_SIZE correctly determines scenario directory (bs_small vs bs_normal)"
  implication: "Tests run with correct small block size fio files"

- timestamp: 2026-04-27
  checked: "entrypoint.sh combined report generation"
  found: "Lines 923-924: generate_report.py called with --combined but NO --bs_size parameter passed"
  implication: "Report generator does not know which block size category was tested"

- timestamp: 2026-04-27
  checked: "generate_report.py generate_fio_summary_tables_all_text()"
  found: "Line 1278: bs_order = ['128k', '1m', '4m'] - HARDCODED normal block sizes"
  implication: "Report uses hardcoded normal block sizes regardless of actual test data"

- timestamp: 2026-04-27
  checked: "generate_report.py generate_fio_summary_tables_text()"
  found: "Lines 1226-1227: bs_order = ['128k', '1m', '4m'] - HARDCODED normal block sizes"
  implication: "Same hardcoded block sizes in single rw_type function"

- timestamp: 2026-04-27
  checked: "parse_fio_scenario_name() regex behavior for small block size scenario names"
  found: "Original regex `r'^(.+?)_(\d)d_(\d+[km])_(\d+)j$'` only matched k/m suffixes. Scenario names like 'seq_read_0d_128_1j' returned None (not parsed)"
  implication: "No data was stored for small block size scenarios because parse_fio_scenario_name() silently failed to parse them"

- timestamp: 2026-04-27
  checked: "Fixed regex pattern"
  found: "Updated to `r'^(.+?)_(\d)d_(\d+[km]|\d+)_(\d+)j$'` which matches both k/m suffixes (128k, 1m, 4m) AND bare numbers (128, 256, 512, 1k, 2k, 4k, 8k)"
  implication: "parse_fio_scenario_name() should now correctly parse small block size scenario names"

- timestamp: 2026-04-27
  checked: "Python test of fixed regex"
  found: "Verified: seq_read_0d_128_1j -> bs=128; seq_read_0d_1k_1j -> bs=1k; seq_read_1d_4m_32j -> bs=4m; All tested patterns work correctly"
  implication: "Data should now be stored with correct bs key when parsing small block size scenarios"

## Resolution
root_cause: "Two issues: (1) parse_fio_scenario_name() regex `r'^(.+?)_(\d)d_(\d+[km])_(\d+)j$'` only matches k/m suffix block sizes (128k, 1m, 4m) but NOT bare numbers (128, 256, 512, 1k, 2k, 4k, 8k). When BS_SIZE=small, scenario names like 'seq_read_0d_128_1j' were NOT being parsed correctly (returned None), so no data was stored at all. (2) The bs_order in summary tables was hardcoded to ['128k', '1m', '4m'] regardless of bs_size parameter, but the first issue meant there was no data to lookup anyway."
fix: "Fixed regex to support both k/m suffix and bare numbers: `r'^(.+?)_(\d)d_(\d+[km]|\d+)_(\d+)j$'`"
verification: "Python test confirms regex now correctly parses both normal (128k, 1m, 4m) and small (128, 256, 512, 1k, 2k, 4k, 8k) block size scenario names. Need end-to-end test."
files_changed: ["scripts/generate_report.py"]