# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## int-quota-email-parsing-bug — Email shows duplicate failed test list, not formatted as table

- **Date:** 2026-04-24
- **Error patterns:** email notification, failed tests duplicate, table formatting
- **Root cause:** The failed tests were displayed twice - once in the plain text "详情:" line and again via extraction logic in notify.sh. Both entrypoint.sh and notify.sh were adding failed tests to the output.
- **Fix:** Parse details string to extract individual values (Total, Passed, Failed, Pass Rate), build proper HTML table. Failed test names extracted once from `.Failed: ` separator and displayed as single row.
- **Files changed:** scripts/notify.sh

---