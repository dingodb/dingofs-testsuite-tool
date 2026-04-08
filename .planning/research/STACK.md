# Technology Stack: LTP Integration

**Project:** DingoFS Storage Benchmark Tools - LTP Addition
**Researched:** 2026-04-08
**Confidence:** LOW

**Note:** Research based on training knowledge (up to early 2025). Web search and official documentation fetch were unavailable for verification. All findings should be validated against current LTP repository before implementation.

---

## LTP Overview

The Linux Test Project (LTP) is a consortium of tests that validate the Linux kernel and system calls. Unlike fio/vdbench (storage benchmarks) or pjdtest (POSIX compliance), LTP focuses on kernel API correctness, stress testing, and system call validation.

**Repository:** https://github.com/linux-test-project/ltp

---

## Installation Methods

### Method 1: Source Compilation (Recommended)

LTP does not provide distribution packages. Source compilation is the standard approach.

```bash
git clone https://github.com/linux-test-project/ltp.git
cd ltp
make autotools
./configure
make -j$(nproc)
```

**Pros:**
- Latest version with newest tests
- Full control over configuration
- Supports all platforms

**Cons:**
- Long build time (15-30+ minutes)
- Requires many build dependencies
- Results in larger image

### Method 2: Distribution Packages (Limited)

Some distributions provide LTP packages, but versions are often outdated:

| Distribution | Package | Version Risk |
|--------------|---------|--------------|
| Fedora | ltp | May be outdated |
| Debian/Ubuntu | ltp | May be outdated |
| Alpine | ltp | May be outdated |

**Not recommended** - Ubuntu 24.04 packages likely outdated.

### Method 3: Use LTP Docker/OCI Image

LTP provides an official Containerfile in the repository root. However, this builds a full LTP test environment, not an integrated tool.

**Best approach for this project:** Build LTP from source and install binaries.

---

## Required Dependencies

### Already Installed (from existing Dockerfile)

The current Dockerfile already includes several LTP build dependencies:

| Package | Purpose | Status |
|---------|---------|--------|
| build-essential | gcc, g++, make | Already installed |
| autoconf | Autotools | Already installed |
| automake | Autotools | Already installed |
| libtool | Library tool | Already installed |
| pkg-config | Build configuration | Already installed |
| libaio-dev | Async I/O library | Already installed |
| git | Source retrieval | Already installed |

### Additional Required Dependencies

| Package | Purpose | Install Size |
|---------|---------|--------------|
| bison | Parser generator for configure | ~3 MB |
| flex | Lexer generator for configure | ~2 MB |
| libcap-dev | Linux capability testing | ~0.1 MB |
| libnuma-dev | NUMA API testing | ~0.3 MB |
| libpopt-dev | Command-line parsing | ~0.1 MB |
| libssl-dev | Crypto/OpenSSL testing | ~2 MB |
| uuid-dev | UUID generation | ~0.1 MB |
| php | Test script runner (some tests) | ~30 MB |

### Estimated Additional Image Size Impact

| Component | Size |
|-----------|------|
| Build dependencies (bison, flex, etc.) | ~40 MB |
| LTP source (cloned) | ~300 MB |
| LTP build artifacts | ~200 MB |
| Installed LTP binaries | ~150 MB |
| **Total additional** | **~700 MB** |

**Note:** Can be reduced by:
- Cleaning build artifacts after install
- Using multi-stage build
- Removing unnecessary test cases

---

## Build Process for Docker

### Recommended Approach: Multi-Stage Build

```dockerfile
# Stage 1: Build LTP
FROM ubuntu:24.04 AS ltp-builder

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        autoconf automake libtool pkg-config \
        bison flex \
        libcap-dev libnuma-dev libpopt-dev \
        libssl-dev uuid-dev \
        git

# Clone and build LTP
RUN git clone https://github.com/linux-test-project/ltp.git /tmp/ltp && \
    cd /tmp/ltp && \
    make autotools && \
    ./configure && \
    make -j$(nproc) && \
    make install

# Stage 2: Final image
FROM ubuntu:24.04

# Copy LTP from builder
COPY --from=ltp-builder /opt/ltp /opt/ltp
COPY --from=ltp-builder /usr/local/bin/ltp* /usr/local/bin/

# ... rest of existing Dockerfile ...
```

### Single-Stage Approach (Simpler but Larger)

Add to existing Dockerfile before the entrypoint setup:

```dockerfile
# Build LTP from source
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        bison flex libcap-dev libnuma-dev libpopt-dev libssl-dev uuid-dev && \
    git clone https://github.com/linux-test-project/ltp.git /tmp/ltp && \
    cd /tmp/ltp && \
    make autotools && \
    ./configure && \
    make -j$(nproc) && \
    make install && \
    rm -rf /tmp/ltp && \
    apt-get purge -y bison flex libcap-dev libnuma-dev libpopt-dev libssl-dev uuid-dev && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
```

---

## Version Considerations

| Aspect | Recommendation |
|--------|-----------------|
| LTP version | Use `git clone` with `--depth 1` for latest mainline |
| Major versions | LTP evolves continuously; no "stable" tags |
| Compatibility | LTP tests kernel APIs; works with Ubuntu 24.04 kernel |

**Note:** Do NOT use release tarballs - the git repository is the canonical source.

---

## Multi-Platform Support (x86_64 and ARM64)

LTP's autotools-based build system handles platform detection automatically.

| Platform | Support | Notes |
|----------|---------|-------|
| x86_64 | Full | Primary development platform |
| ARM64 (aarch64) | Full | Equal support, some tests ARM-specific |

**Dockerfile consideration:** Use `make -j$(nproc)` which works on both platforms.

**Verification:** Run `uname -m` in container to confirm platform.

---

## Integration Notes for Docker Build

### 1. Entrypoint Changes Required

Add LTP tool dispatch in `entrypoint.sh`:

```bash
# In dispatch_tool() case statement, add:
ltp)
    ltp_run
    ;;

# Add ltp_run function:
ltp_run() {
    echo "Running LTP test suite"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"

    mkdir -p "$OUTPUT"

    cd "$MOUNT"

    # Run LTP with specified test cases or default suite
    /opt/ltp/runltp -p -l "$OUTPUT/ltp.log" -o "$OUTPUT/ltp.raw" -f "$SCENARIO"

    return $?
}
```

### 2. LTP Execution Modes

| Mode | Command | Use Case |
|------|---------|----------|
| Full suite | `runltp -f all` | Comprehensive validation |
| Filesystem | `runltp -f syscalls` | System call tests |
| Specific tests | `runltp -s <testname>` | Targeted testing |
| Scenarios | Define in runtest/ directory | Custom test sets |

### 3. LTP Test Scenarios (Suggested)

| Scenario | Description | Complexity |
|----------|-------------|------------|
| ltp_syscalls | Core system call tests | Medium |
| ltp_fs | Filesystem stress tests | High |
| ltp_io | I/O stress tests | High |
| ltp_fsx | Filesystem extended tests | Medium |
| ltp_nfs | NFS-specific tests | High |

### 4. Output Handling

LTP produces:
- `ltp.log` - Summary log
- `ltp.raw` - Full test output
- Exit code reflects test pass/fail

---

## Runtime Considerations in Docker

### Container Capabilities Required

Some LTP tests require elevated capabilities:

```bash
# Run with full privileges for complete testing
docker run --privileged ...

# Or cap-add specific capabilities
docker run --cap-add=SYS_ADMIN --cap-add=SYS_PTRACE ...
```

**Note:** Many LTP tests are designed to run on bare metal and will fail or cause issues in restricted containers. This is expected behavior.

### Tests That Will Fail in Containers

| Test Category | Reason | Recommendation |
|---------------|--------|----------------|
| I/O stress (doio, iogen) | Requires raw device access | Exclude in container |
| Kernel module tests | Requires module loading | Exclude |
| Power management | Requires hardware | Exclude |
| Network stress | May conflict with container networking | Use `-I net_stress` |

### Recommended Container Execution

```bash
# Run only safe tests in container
docker run ... /opt/ltp/runltp -f syscalls -p

# Or exclude problematic tests
docker run ... /opt/ltp/runltp -e "doio,iogen,mm,vm" -f all
```

---

## Anti-Pitfalls

### Pitfall 1: Building Without Required Dependencies
**Problem:** `./configure` fails with missing library errors
**Solution:** Install all dependencies listed above before running configure

### Pitfall 2: Running Full Suite in Container
**Problem:** Many tests require kernel features unavailable in containers
**Solution:** Use `-e` to exclude tests that require bare metal, or use `--privileged`

### Pitfall 3: Image Size Explosion
**Problem:** LTP build adds 500+ MB
**Solution:** Use multi-stage build, clean build artifacts, remove source after install

### Pitfall 4: ARM64 Compatibility
**Problem:** Some LTP test cases are x86_64-specific
**Solution:** Use `make autotools` which handles platform detection; some tests auto-skip on unsupported platforms

---

## Sources

**Note:** This research could not be verified with current sources due to tool restrictions. Primary sources that should be consulted:

1. https://github.com/linux-test-project/ltp (official repo - INSTALL, README, Containerfile)
2. https://linux-test-project.readthedocs.io/ (official documentation)
3. https://github.com/linux-test-project/ltp/blob/master/INSTALL (build requirements)
4. https://github.com/linux-test-project/ltp/blob/master/Containerfile (Docker build reference)

**Confidence:** LOW - Training knowledge only, not verified against current documentation. Validation required before implementation.

---

## Recommendations

1. **Start with source compilation** - Most reliable method
2. **Use multi-stage Docker build** - Minimizes image size
3. **Include common LTP dependencies** - bison, flex, libcap-dev, libnuma-dev, libpopt-dev, libssl-dev, uuid-dev
4. **Plan for capability requirements** - Document that LTP tests may require `--privileged` or specific `--cap-add`
5. **Select subset of tests** - Not all LTP tests are suitable for container execution; focus on syscall and filesystem tests
6. **Validate before implementation** - Verify dependencies against current LTP INSTALL file in repository
