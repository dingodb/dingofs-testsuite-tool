# Domain Pitfalls: Adding LTP to Docker Storage Testsuite Image

**Domain:** LTP (Linux Test Project) Docker Integration
**Researched:** 2026-04-08
**Confidence:** MEDIUM (based on training data, not verified against current sources)

## Executive Summary

Adding LTP to a Docker-based storage testsuite image introduces several categories of pitfalls: compilation complexity, image size bloat, runtime privilege requirements, kernel feature limitations, test hanging risks, multi-platform challenges, test selection complexity, and result parsing difficulties. Most critical is the privilege/capability issue - many LTP tests fundamentally require kernel-level access that containers cannot safely provide.

## Critical Pitfalls

Mistakes that cause rewrites, security issues, or complete test failures.

---

### Pitfall 1: Unrestricted Root/Meta Package Installation

**What goes wrong:** Installing full LTP development dependencies bloats image by 500MB-1GB+.

**Why it happens:** LTP requires extensive build tools: autoconf, automake, libtool, pkg-config, gcc, g++, make, bison, flex, and many `-dev` packages for kernel headers, glibc, etc.

**Consequences:**
- Violates project constraint "镜像大小: 尽量精简"
- Extends Docker build time by 10-30 minutes
- Creates attack surface with unnecessary packages

**Prevention:**
- Use multi-stage build to compile in builder stage, copy only artifacts
- Consider pre-compiled binaries if available
- Install only `-dev` packages needed for LTP build, remove build tools after

**Detection:** Image size exceeds 2GB

**Phase:** Should be addressed during Phase 1 (Build/Compile setup)

---

### Pitfall 2: Running LTP Without Required Capabilities

**What goes wrong:** Tests fail silently or report false negatives due to missing Linux capabilities.

**Why it happens:** LTP tests exercise syscalls and kernel features requiring:
- `CAP_SYS_ADMIN` - many filesystem, namespace, system tests
- `CAP_NET_ADMIN` - network-related tests
- `CAP_SYS_PTRACE` - process tracing tests
- Access to `/proc/sys/kernel/*` tuning knobs

Docker drops most capabilities by default for security.

**Consequences:**
- Tests that should pass appear to fail
- Misleading testsuite results
- Users may blame storage system for kernel behavior issues

**Prevention:**
- Document required `--cap-add` flags clearly
- Create wrapper script that adds necessary capabilities
- Consider using `--privileged` only for specific test runs (with warning)
- Use `docker run --device /dev/fuse` for fuse-related tests

**Detection:** LTP output shows "permission denied" or "operation not permitted" for tests that should work

**Phase:** Must be addressed in Phase 2 (Runtime configuration)

---

### Pitfall 3: Container Kernel Feature Mismatch

**What goes wrong:** LTP tests for kernel features that are unavailable or restricted in containerized environments.

**Why it happens:** LTP tests kernel internals:
- Namespace operations (mount, PID, network, user namespaces)
- cgroup behavior and limits
- Specific syscalls (e.g., `userfaultfd`, `io_uring` features)
- `/proc` and `/sys` filesystem behavior differences

Even with `--privileged`, some kernel features behave differently in containers vs bare metal.

**Consequences:**
- Test failures that are environment-specific, not storage-related
- Confusion about whether failures are due to DingoFS or container limitations
- False confidence - passing tests may not reflect bare-metal behavior

**Prevention:**
- Create explicit "container-compatible" test subset
- Document which test categories are expected to fail/pass in containers
- Run full LTP on bare metal for kernel compliance testing, not in container

**Detection:** Systematic failures in namespace/cgroup test categories

**Phase:** Address in Phase 2 (Runtime configuration) - test categorization

---

### Pitfall 4: Test Hanging and Resource Exhaustion

**What goes wrong:** LTP stress tests hang indefinitely or consume all container resources.

**Why it happens:**
- Some LTP tests are designed to run until failure or timeout
- Stress tests (`ltp-stress.sh`, `mmtests`) create extreme system load
- No default timeout protection in container context
- Memory/CPU limits may cause unexpected behavior vs bare metal

**Consequences:**
- Container never exits, blocks automation
- System resource exhaustion affects host
- Docker watchdog may kill container unexpectedly

**Prevention:**
- Always run LTP with explicit timeout wrapper: `timeout 3600 runltp ...`
- Set Docker resource limits: `--memory`, `--cpus`
- Use LTP's built-in `-t` timeout option if available
- Document which tests are excluded in container mode

**Detection:** Container hanging past expected completion time

**Phase:** Must be addressed in Phase 2 (Runtime) with timeout mechanism

---

### Pitfall 5: Multi-Platform Build Complexity (x86_64/ARM64)

**What goes wrong:** LTP compiles successfully on x86_64 but fails on ARM64 or vice versa.

**Why it happens:**
- Some LTP tests have architecture-specific code paths
- Compiler flags may need adjustment per architecture
- Test expectations (syscall numbers, behavior) differ between architectures
- Cross-compilation is not straightforward for test binaries

**Consequences:**
- Image only works on one platform
- Silent test differences between architectures
- Build failures on CI/CD for non-native architecture

**Prevention:**
- Use `docker buildx` with explicit platform targeting
- Test build on both architectures in CI
- Add architecture detection in entrypoint to skip incompatible tests
- Check LTP release notes for known ARM64 issues

**Detection:** Build failures or test result differences on ARM64

**Phase:** Address in Phase 1 (Build) with multi-platform verification

---

### Pitfall 6: Running Full LTP Suite Instead of Subset

**What goes wrong:** Running all LTP tests takes 24-72+ hours, generates overwhelming output.

**Why it happens:** LTP contains 2000+ test cases covering:
- Filesystem operations
- System calls
- Networking
- IPC mechanisms
- Memory management
- Device drivers

Most are not relevant to storage testsuite evaluation.

**Consequences:**
- Extremely long test times
- Gigabytes of output data
- Analysis paralysis
- User frustration

**Prevention:**
- Create predefined test subsets in `/scenarios/ltp/`
- Document recommended subsets:
  - `ltp-fs` - filesystem-related tests only
  - `ltp-stress` - stress tests only
  - `ltp-quick` - fast smoke tests
- Use `runltp -f <category>` to filter test categories

**Detection:** Test runs taking >1 hour for storage-focused evaluation

**Phase:** Address in Phase 1 (Test subset definition)

---

## Moderate Pitfalls

### Pitfall 7: Test Output Parsing Complexity

**What goes wrong:** LTP output format is difficult to parse for automated reporting.

**Why it happens:**
- LTP outputs to multiple destinations: stdout, stderr, syslog, files in `/tmp/ltp-*/`
- Exit codes: 0 = pass, 1 = fail, 2 = skip, 32+ = special conditions
- Result file format requires specific parsers

**Consequences:**
- Incomplete or incorrect test result aggregation
- Report generation failures
- Missing test details in output

**Prevention:**
- Use `-l /tmp/ltp.log -o /tmp/ltp.out` for structured output
- Parse `<?xml>` or `tap` format output for easier automation
- Write custom parser script (Python) to extract pass/fail counts

**Phase:** Address in Phase 3 (Reporting integration)

---

### Pitfall 8: Installation Source Instability

**What goes wrong:** LTP repository changes between versions, breaking builds.

**Why it happens:**
- LTP development is active, master branch may have breaking changes
- Git clone of master gets latest which may require newer kernel headers
- Autotools may need regeneration

**Consequences:**
- Build failures after repository updates
- Non-reproducible builds
- CI/CD failures

**Prevention:**
- Use pinned release tag: `git clone --depth 1 --branch 20240130 https://github.com/linux-test-project/ltp.git`
- Pin to specific commit if using master
- Test build periodically to catch breakage early

**Phase:** Address in Phase 1 (Build setup)

---

### Pitfall 9: Host Kernel Version Mismatch

**What goes wrong:** LTP tests designed for newer kernel fail on older host kernel (and vice versa).

**Why it happens:**
- LTP tracks Linux kernel development
- Tests may use syscalls/features not available on older kernels
- Host kernel version may be older than LTP test assumptions

**Consequences:**
- False test failures due to kernel age
- Confusing "unsupported syscall" errors
- Misleading storage performance conclusions

**Prevention:**
- Check host kernel version before running tests
- Document minimum kernel version requirements (typically 4.x+)
- Use `-k KERNEL_VERSION` flag if LTP supports kernel version filtering
- Skip incompatible tests gracefully

**Phase:** Address in Phase 2 (Runtime validation)

---

## Minor Pitfalls

### Pitfall 10: Missing Perl Dependencies

**What goes wrong:** LTP test runner `runltp` fails due to missing Perl modules.

**Why it happens:**
- `runltp` is a Perl script requiring modules: `Perl::Tidy`, `Time::HiRes`, `POSIX`, `Fcntl`
- Ubuntu minimal images often lack these

**Prevention:**
- Add to Dockerfile: `apt-get install -y perl libtimedate-perl`
- For additional modules: `cpan install Test::Most` if needed

---

### Pitfall 11: IPv6 Network Configuration

**What goes wrong:** Network tests fail if host has IPv6 disabled or Docker network is IPv4-only.

**Why it happens:** LTP network tests may bind to both IPv4 and IPv6, fail on IPv4-only systems.

**Prevention:**
- Filter network tests: `-f network_tests`
- Document IPv6 requirement or skip network tests in container context

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 1: Build | Unrestricted dependencies bloat image | Use multi-stage build, minimal deps |
| Phase 1: Build | Multi-platform build failures | Test on both x86_64 and ARM64 |
| Phase 1: Build | Repository instability | Pin to release tag/commit |
| Phase 2: Runtime | Missing capabilities cause false failures | Document required `--cap-add` flags |
| Phase 2: Runtime | Kernel feature mismatch | Create container-compatible test subset |
| Phase 2: Runtime | Test hanging | Always wrap with timeout |
| Phase 3: Integration | Output parsing complexity | Use structured output formats |
| Phase 3: Integration | Result reporting | Map LTP output to unified report format |

## Recommendations Summary

### Build Phase (Phase 1)
1. Use multi-stage Docker build to keep final image small
2. Pin LTP to specific release tag
3. Install only required `-dev` packages, remove build tools after
4. Test on both x86_64 and ARM64 before finalizing

### Runtime Phase (Phase 2)
1. Document required Docker capabilities: `--cap-add SYS_ADMIN` for filesystem tests
2. Create predefined test subsets: `ltp-fs`, `ltp-stress`, `ltp-quick`
3. Wrap all LTP invocations with `timeout` command
4. Add kernel version check before running tests

### Integration Phase (Phase 3)
1. Use LTP TAP or XML output format for easier parsing
2. Parse results into unified format (JSON) for report generation
3. Handle test categories: pass, fail, skip,.conf

## Sources

- **LOW confidence** - Training data only, not verified against current LTP documentation
- LTP Documentation: https://github.com/linux-test-project/ltp
- Docker Run Reference: https://docs.docker.com/engine/reference/run/
- Linux Capabilities: `man 7 capabilities`
