# Quick Task 260413-m3k: Support multiple mdsaddr addresses (comma-separated) - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Task Boundary

Support multiple mdsaddr addresses separated by commas (e.g., 172.30.14.126:6900,172.30.14.126:6901,172.30.14.126:6902) for DingoFS MDS access.

</domain>

<decisions>
## Implementation Decisions

### Validation approach
- Basic format check: validate IP:port format only, trust addresses are reachable

### Multiple addresses handling
- Pass as-is to dingo CLI: keep as comma-separated string, pass directly to dingo CLI (simplest)

</decisions>

<specifics>
## Specific Ideas

- Example format: `172.30.14.126:6900,172.30.14.126:6901,172.30.14.126:6902`
- Usage: `dingo fs list --mdsaddr 172.30.14.126:6900,172.30.14.126:6901,172.30.14.126:6902`
- For --add-host: extract unique IPs only (same IP with different ports only needs one host entry)

</specifics>

<canonical_refs>
## Canonical References

No external specs — requirements fully captured in decisions above

</canonical_refs>
