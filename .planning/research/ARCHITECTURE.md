# Architecture Research: LTP Integration

**Project:** DingoFS Storage Testsuite Tools
**Researched:** 2026-04-08
**Confidence:** LOW (based on training data; verification needed)

## Executive Summary

LTP (Linux Test Project) is a comprehensive test suite that validates Linux system reliability, stability, and correctness. Integrating LTP into the existing Docker testsuite architecture requires adding LTP as a new tool case in the `dispatch_tool()` function, installing LTP in `/opt/ltp`, and routing its output to the user-specified mount point and output directory.

The integration follows the established pattern used by pjdtest: a single tool dispatch case that runs LTP tests against the mount point and captures output to the designated output directory.

## Current Architecture

### Existing Dispatch Pattern

```
dispatch_tool() case statement:
  fio    → fio_run()
  vdbench → vdbench_run()
  mdtest  → mdtest_run()
  pjdtest → pjdtest_run()
```

### Entry Point Flow

1. `parse_args()` extracts: `-t tool`, `-s scenario`, `-m mount`, `-o output`
2. `validate_params()` checks tool validity against allowed list
3. `dispatch_tool()` routes to tool-specific run function
4. Run function executes tool against MOUNT, outputs to OUTPUT
5. `generate_report.py` creates formatted reports

### Existing Tool Install Locations

| Tool | Location | Purpose |
|------|----------|---------|
| fio | `/usr/bin/fio` | I/O performance testing |
| vdbench | `/opt/vdbench/vdbench` | Oracle storage testsuite |
| mdtest | `/usr/local/bin/mdtest` | Filesystem metadata testing |
| pjdtest | `/pjdtest/` (source) | POSIX compliance testing |

## LTP Architecture

**Note:** The following is based on training data (approximately 6-18 months stale). Verification with current LTP documentation is recommended.

### LTP Directory Structure

```
/opt/ltp/
├── runltp           # Main test runner script
├── testcases/       # Test case source code
│   ├── bin/         # Compiled test binaries
│   ├── kernel/      # Kernel-related tests
│   └── fs/          # Filesystem-specific tests
├── output/          # Test output files (stdout/stderr)
├── results/         # Test result XML files
├── log/             # Execution logs
└── .git/            # Source repository
```

### LTP Execution

**Primary command:** `/opt/ltp/runltp`

**Common flags:**
| Flag | Purpose | Example |
|------|---------|---------|
| `-p` | Output directory for results | `-p /output` |
| `-l` | Log file path | `-l /output/ltp.log` |
| `-f` | Test suites to run | `-f fs` for filesystem tests |
| `-d` | Test device/mount point | `-d /mnt/test` |
| `-t` | Timeout per test | `-t 300` |

**Test suites (relevant to storage):**
- `fs` - Filesystem tests
- `mm` - Memory management tests
- `io` - Block I/O tests
- `scsi` - SCSI subsystem tests

## Integration Design

### New Components Required

| Component | Type | Location | Purpose |
|-----------|------|----------|---------|
| LTP source | Download/build | `/opt/ltp` | Test suite |
| `ltp_run()` | Function | `entrypoint.sh` | Test execution |
| LTP validation | Case addition | `validate_params()` | Accept `ltp` tool |

### Modified Components

| Component | Change | Rationale |
|-----------|--------|-----------|
| `entrypoint.sh` | Add `ltp` to valid tools in validation | Allow `-t ltp` |
| `entrypoint.sh` | Add `ltp_run()` function | Execute LTP tests |
| `entrypoint.sh` | Add case in `dispatch_tool()` | Route `ltp` tool |
| `Dockerfile` | Add LTP build dependencies | Compile LTP from source |
| `Dockerfile` | Clone and build LTP | Install test suite |

### Installation Approach

LTP must be built from source in the Dockerfile:

```dockerfile
# Dependencies for LTP build
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        bison \
        flex \
        libaudit-dev \
        libcap-dev \
        libnuma-dev \
        libacl1-dev \
        wget \
        make \
        pkg-config && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Clone and build LTP
RUN git clone https://github.com/linux-test-project/ltp.git /opt/ltp && \
    cd /opt/ltp && \
    make autotools && \
    ./configure --prefix=/opt/ltp && \
    make -j$(nproc) && \
    make install
```

### Mount Point Handling

LTP tests require the mount point to be:
1. Passed via `-d` flag to `runltp`
2. Writable by the test user
3. Used as the working directory during tests

**Integration pattern (similar to pjdtest):**
```bash
ltp_run() {
    echo "Running LTP tests"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"
    echo "  Scenario: $SCENARIO"

    mkdir -p "$OUTPUT"

    cd "$MOUNT"

    # Generate timestamp for output file
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")

    # Run LTP with filesystem tests by default
    # -p: output directory
    # -l: log file
    # -d: test directory (mount point)
    # -f: test suite (default: fs for filesystem)
    /opt/ltp/runltp -p "$OUTPUT" -l "$OUTPUT/ltp_${timestamp}.log" -d "$MOUNT" -f "${SCENARIO:-fs}"

    return $?
}
```

### Scenario Handling

LTP scenarios map to test suites:

| Scenario | LTP Suite | Tests |
|----------|-----------|-------|
| `ltp` or `ltp_fs` | `fs` | Filesystem operations |
| `ltp_mm` | `mm` | Memory management |
| `ltp_io` | `io` | Block I/O |
| `ltp_all` | `fs mm io` | All storage-related |

### Output Handling

LTP generates multiple output files:
- `$OUTPUT/ltp_<timestamp>.log` - Execution log
- `$OUTPUT/results/` - XML result files (if configured)
- `/opt/ltp/output/` - Default output directory (symlink or copy to OUTPUT)

**Recommended approach:** Use `-p "$OUTPUT"` to redirect LTP output directly to the user-specified output directory, then copy/symlink any default output directories.

## Phase-Specific Considerations

| Phase | Consideration | Risk |
|-------|---------------|------|
| Dockerfile | LTP build dependencies may conflict with existing packages | MEDIUM |
| Dockerfile | LTP source clone + build adds significant image size (>1GB) | HIGH |
| entrypoint.sh | LTP long-running tests may need timeout handling | MEDIUM |
| Scenarios | Need LTP-specific scenario definitions in `/scenarios/ltp/` | LOW |

## Alternative Approaches

### Option 1: Full LTP Suite (Recommended)
- Install all LTP tests
- Default to `fs` suite for storage-focused testing
- Allow `-s` to specify subset (`fs`, `mm`, `io`)

**Pros:** Comprehensive testing
**Cons:** Large image size (~2-3GB added)

### Option 2: Minimal LTP-FS Only
- Only install filesystem test subset
- Smaller image footprint

**Pros:** Smaller image
**Cons:** Limited test coverage

### Option 3: Pre-built Binary
- Use a pre-built LTP Docker layer or binary package

**Pros:** Faster build time
**Cons:** Less control over version; may not support ARM64

## Recommendations

1. **Follow existing pjdtest pattern** for CLI integration
2. **Build LTP from source** in Dockerfile for version control
3. **Default to `fs` suite** for storage-specific testing
4. **Use `-p` and `-l` flags** to redirect output to user-specified directory
5. **Add `ltp` to validate_params()** tool list
6. **Create `/scenarios/ltp/`** directory with scenario shell scripts for common test runs
7. **Consider image size** - LTP is large; document the size trade-off

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Existing architecture patterns | HIGH | Verified from codebase |
| LTP directory structure | LOW | Training data only; verify with current docs |
| LTP execution flags | LOW | Training data; some flags may have changed |
| Build dependencies | MEDIUM | Common Linux packages; verify versions |
| Output format | MEDIUM | XML results standard but details may vary |

## Verification Needed

1. Current LTP installation instructions (official docs)
2. Verify `-p`, `-l`, `-d`, `-f` flags still work as described
3. Confirm output directory structure
4. Check ARM64 compatibility of LTP build

## Sources

- [LTP GitHub Repository](https://github.com/linux-test-project/ltp) - Training data reference
- Existing project codebase - Architecture patterns verified
