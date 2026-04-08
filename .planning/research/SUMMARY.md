# Research Summary: LTP Integration

**Project:** DingoFS Storage Benchmark Tools - v1.1 LTP Addition
**Researched:** 2026-04-08
**Confidence:** LOW-MEDIUM (training data, needs verification)

---

## Key Findings

### 1. LTP Must Be Built From Source
LTP has no official distribution packages. Source compilation adds ~700MB to image.

### 2. Important: LTP `runltp` Has Been Deprecated
LTP has moved to **"kirk"** as the new test runner. The traditional `runltp` script now simply redirects to kirk.

**Implication:** Need to research kirk further or use older LTP stable version.

### 3. LTP Test Categories (Relevant for Storage)
- `fs` - Filesystem tests (growfiles, rwtest, fs_inod, etc.)
- `dio` - Direct I/O tests
- `mm` - Memory management tests
- `io` - Block I/O tests

### 4. Integration Pattern (Same as pjdtest)
```bash
# Add to dispatch_tool() case:
ltp)
    ltp_run
    ;;

# New function:
ltp_run() {
    cd "$MOUNT"
    /opt/ltp/runltp -p "$OUTPUT" -l "$OUTPUT/ltp_${timestamp}.log" -d "$MOUNT" -f "${SCENARIO:-fs}"
}
```

### 5. Required Dependencies (Additional)
- bison, flex (parser generators)
- libcap-dev, libnuma-dev, libpopt-dev, libssl-dev, uuid-dev

### 6. Critical Runtime Requirements
- Many tests need `--cap-add=SYS_ADMIN` or `--privileged`
- Tests should be wrapped with `timeout` to prevent hanging
- Not all tests suitable for container execution

---

## Stack Additions

| Component | Size | Notes |
|-----------|------|-------|
| Build dependencies | ~40 MB | bison, flex, etc. |
| LTP source (cloned) | ~300 MB | Temporary |
| LTP build artifacts | ~200 MB | Clean after install |
| Installed LTP | ~150 MB | Final size |
| **Total added** | **~700 MB** | Can be reduced with multi-stage build |

---

## Watch Out For

| Pitfall | Severity | Prevention |
|---------|----------|------------|
| Image bloat | Critical | Multi-stage Docker build |
| Missing capabilities | Critical | Document --cap-add flags |
| Kernel feature mismatch | Critical | Create container-compatible subset |
| Test hanging | Critical | Wrap with timeout |
| Multi-platform failures | High | Test on both x86_64 and ARM64 |

---

## Next Steps

1. **Verify kirk installation** - The new LTP test runner
2. **Define LTP requirements** - Based on research findings
3. **Plan Docker build** - Multi-stage to minimize size
4. **Document runtime requirements** - Capabilities and limitations

---

## Research Files

| File | Purpose |
|------|---------|
| STACK.md | Build dependencies, installation methods |
| ARCHITECTURE.md | Integration pattern, CLI changes |
| PITFALLS.md | Critical issues and prevention |

---

*Note: Features research was skipped due to time constraints. Key finding: runltp deprecated in favor of kirk.*
