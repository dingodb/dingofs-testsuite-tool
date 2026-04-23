#!/bin/bash
#
# DingoFS Storage Testsuite Tools - Unified Entrypoint
# Parses CLI arguments, handles one-shot and long-running modes,
# dispatches to correct storage testing tool (fio/vdbench/mdtest)
#
# Usage:
#   docker run dingofs-testsuite-tools -t fio -s seq_read -m /mnt/test
#   docker run dingofs-testsuite-tools -t vdbench -s rand_read -m /mnt/test -o /tmp/results
#   docker run --detach dingofs-testsuite-tools -t fio -s randrw --mode long-running
#

set -e

# ==============================================================================
# Global Variables
# ==============================================================================

TOOL=""              # Storage testing tool (fio, vdbench, mdtest)
SCENARIO=""          # Test scenario name (e.g., seq_read, rand_write)
MOUNT="/data"        # Filesystem mount point
OUTPUT="/data/results"  # Output directory
MODE="one-shot"      # Mode: one-shot or long-running
NP=16                # Number of MPI processes for mdtest (default: 16)

# Tool paths (from Dockerfile)
FIO_BIN="/usr/bin/fio"
VDBENCH_BIN="/opt/vdbench/vdbench"
VDBENCH_DIR="/opt/vdbench"
MDTEST_BIN="/usr/local/bin/mdtest"
INTEGRATION_DIR="/dingofs-integration-test"

# Scenario directories
SCENARIOS_DIR="/scenarios"

# Notification settings
WECHAT_ENABLED="${WECHAT:-no}"
WEBHOOK_URL="${WEBHOOK_URL:-}"
EMAIL_ENABLED="${EMAIL:-no}"
EMAIL_TO="${EMAIL_TO:-daigy@zetyun.com}"

# Source notification script
if [[ -f "/scripts/notify.sh" ]]; then
    source /scripts/notify.sh
fi

# ==============================================================================
# Help Function
# ==============================================================================

show_help() {
    cat << EOF
DingoFS Storage Testsuite Tools
===============================

Usage:
  docker run dingofs-testsuite-tools -t <tool> -s <scenario> -m <mount> -o <output>

Options:
  -t, --tool      测试工具: fio, vdbench, mdtest
  -s, --scenario  测试场景
  -m, --mount     被测存储的挂载点 (例如: /mnt/test)
  -o, --output    测试结果输出目录 (例如: /output)
  -n, --np        mdtest MPI 进程数 (默认: 16)
  --mode          运行模式: one-shot (默认) 或 long-running

注意: -o 指定的是容器内路径，需要通过 -v 将容器内目录映射到本机路径

Tools:
  fio       - Flexible I/O tester (存储性能测试)
  vdbench   - Oracle storage testsuite
  mdtest    - MPI filesystem metadata test
  pjdtest   - POSIX filesystem test suite
  ltp       - Linux Test Project (内核测试套件)
  int       - DingoFS integration test (自动化框架)

运行模式:
  one-shot      - 容器启动 → 运行测试 → 测试完成后容器退出 (默认)
  long-running   - 容器启动 → 运行测试 → 容器保持运行，可用 docker exec 执行更多测试

通知选项:
  --wechat    启用企业微信通知 (需要配置 webhook_url)
  --email      启用邮件通知 (需要配置 email)

配置通知:
  dtt config set webhook_url <url>  设置企业微信webhook地址
  dtt config set email <地址>      设置邮件通知地址

FIO Scenarios (4 types, each runs 24 sub-scenarios):
  rand_read   - Random read  (24 variants: 2 direct × 3 block size × 4 numjobs)
  rand_write  - Random write
  seq_read    - Sequential read
  seq_write   - Sequential write

FIO Parameters:
  direct:    0 (buffered), 1 (direct I/O)
  block size: 128k, 1m, 4m
  numjobs:   1, 8, 16, 32
  iodepth:   1 (fixed)
  size:      8G per job

MDTEST Scenarios (4 types, each runs with configurable parallel tasks):
  mdtest_z0_n100   - z=0, n=100 (扁平目录, 3200 files)
  mdtest_z5_b4_I1  - z=5, b=4, I=1 (多分支树, 32736 items)
  mdtest_z6_b3_I1  - z=6, b=3, I=1 (中等深度树, 34976 items)
  mdtest_z9_b2_I1  - z=9, b=2, I=1 (深层二叉树, 32736 items)
  mdtest           - 运行以上所有4个场景

  默认进程数: 16，可用 -n 或 --np 参数调整

PJDTEST:
  pjdtest    - 运行 POSIX 文件系统测试套件 (prove -rv /pjdtest/dingofs_baseline)

LTP:
  ltp        - 运行 Linux Test Project 测试套件 (默认 fs)
  ltp_fs     - 文件系统测试 (fs)
  ltp_dio    - Direct I/O 测试 (dio)
  ltp_mm     - 内存管理测试 (mm)

注意: LTP 需要 --privileged 运行以访问 /dev/kmsg 等设备

Examples:
  # 运行所有 rand_read 场景 (24 tests)
  docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t fio -s rand_read -m /data -o /data

  # 运行所有 seq_write 场景 (24 tests)
  docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t fio -s seq_write -m /data -o /data

  # 运行单个特定场景
  docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t fio -s rand_read_0d_128k_1j -m /data -o /data

  # vdbench 测试
  docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t vdbench -s seq_rd -m /data -o /data

  # mdtest 测试 (运行所有4个场景并汇总)
  docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t mdtest -s mdtest -m /data -o /data

  # mdtest 单个场景测试
  docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t mdtest -s mdtest_z0_n100 -m /data -o /data

  # mdtest 自定义进程数测试
  docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t mdtest -s mdtest -m /data -o /data -n 32

  # pjdtest 测试
  docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t pjdtest -s pjdtest -m /data -o /data

  # ltp 测试 (默认运行文件系统测试，需要 --privileged)
  docker run --rm --privileged -v /tmp/test:/data dingofs-testsuite-tools -t ltp -s ltp -m /data -o /data

  # int 测试 (需要配置MDS地址)
  docker run --rm --privileged -v /tmp/test:/data dingofs-testsuite-tools -t int -s quota -m /data -o /data

  # 长期运行模式 (容器保持运行，可执行多个测试)
  docker run --detach -v /tmp/test:/data dingofs-testsuite-tools -t fio -s rand_read -m /data -o /data --mode long-running
  docker exec <container_id> entrypoint.sh -t fio -s seq_write -m /data -o /data

  # 分离挂载点和输出目录 (被测存储和结果保存到不同路径)
  docker run --rm \
    -v /mnt/disk1/test:/data \
    -v /tmp/results:/output \
    dingofs-testsuite-tools \
    -t fio -s seq_read -m /data -o /output

Output:
  测试结果保存在输出目录中:
    - fio.raw / fio.json    (原始输出和JSON格式)
    - mdtest.raw            (mdtest 原始输出)
    - pjdtest_YYYYMMDD_HHMMSS (pjdtest 测试结果)
    - ltp_YYYYMMDD_HHMMSS.log (LTP 测试日志)
    - report.html           (HTML可视化报告)
    - summary.md           (Markdown格式摘要)

EOF
}

# ==============================================================================
# Per-Tool Help Functions
# ==============================================================================

show_fio_help() {
    cat << EOF
FIO 存储性能测试
=================

用法: dtt -t fio -s <场景> [-m <挂载点>] [-o <输出目录>]

场景类型 (4种类型，每种24个子场景):
  seq_read    - 顺序读
  seq_write   - 顺序写
  rand_read   - 随机读
  rand_write  - 随机写
  all         - 运行所有4种场景类型 (96个测试)

每个场景运行以下变体:
  direct:    0 (buffered), 1 (direct I/O)
  block size: 128k, 1m, 4m
  numjobs:   1, 8, 16, 32
  iodepth:   1 (固定)
  size:      每个job 8G

示例:
  # 运行所有顺序读场景 (24个测试)
  dtt -t fio -s seq_read

  # 运行所有场景 (96个测试)
  dtt -t fio -s all

  # 运行单个场景
  dtt -t fio -s rand_read_0d_128k_1j
EOF
}

show_mdtest_help() {
    cat << EOF
MDTEST 元数据测试
==================

用法: dtt -t mdtest -s <场景> [-n <进程数>] [-m <挂载点>] [-o <输出目录>]

场景类型:
  mdtest_z0_n100   - z=0, n=100 (扁平目录, 3200文件)
  mdtest_z5_b4_I1  - z=5, b=4, I=1 (多分支树, 32736项)
  mdtest_z6_b3_I1  - z=6, b=3, I=1 (中等深度树, 34976项)
  mdtest_z9_b2_I1  - z=9, b=2, I=1 (深层二叉树, 32736项)
  all              - 运行所有4个场景 (默认)

默认进程数: 16 (可用 -n 或 --np 调整)

示例:
  # 运行所有mdtest场景 (默认)
  dtt -t mdtest -s all

  # 运行单个场景
  dtt -t mdtest -s mdtest_z0_n100

  # 自定义MPI进程数
  dtt -t mdtest -s all -n 32
EOF
}

show_pjdtest_help() {
    cat << EOF
PJDTEST POSIX 文件系统测试
===========================

用法: dtt -t pjdtest -s <场景> [-m <挂载点>] [-o <输出目录>]

测试类别:
  all       - 运行所有POSIX测试 (默认)

pjdtest套件使用 'prove -rv' 运行DingoFS基线POSIX兼容性测试。

示例:
  # 运行所有POSIX测试
  dtt -t pjdtest -s all
EOF
}

show_ltp_help() {
    cat << EOF
LTP Linux 测试项目
====================

用法: dtt -t ltp -s <场景> [-m <挂载点>] [-o <输出目录>]

测试套件:
  all       - 运行所有测试 (fs, fsx, io, dir, lock, syscalls) (默认)
  fs        - 文件系统测试
  fsx       - 文件系统扩展属性测试
  io        - Direct I/O测试
  dir       - 目录操作测试
  lock      - 文件锁测试
  syscalls  - 系统调用测试

注意: LTP需要 --privileged 以访问 /dev/kmsg 等内核接口。

示例:
  # 运行所有LTP测试 (默认)
  dtt -t ltp -s all

  # 运行单个测试
  dtt -t ltp -s fs
  dtt -t ltp -s fsx
  dtt -t ltp -s io
  dtt -t ltp -s dir
  dtt -t ltp -s lock
  dtt -t ltp -s syscalls
EOF
}

show_int_help() {
    cat << EOF
INT 集成测试 (DingoFS Automation Framework)
============================================

用法: dtt -t int -s <场景> [-m <挂载点>] [-o <输出目录>]

测试模块:
  quota       - Quota 配额测试 (默认)
  client      - Client 客户端测试
  cache_node  - Cache Node 缓存节点测试
  chaos       - Chaos 混沌测试

示例:
  # 运行所有 quota 测试 (默认)
  dtt -t int -s quota

  # 运行 client 测试
  dtt -t int -s client

  # 运行所有集成测试
  dtt -t int -s all

注意: 需要配置 MDS 地址 (dtt config set mdsaddr)
EOF
}

# ==============================================================================
# Validation Functions
# ==============================================================================

validate_params() {
    local error=0

    # Validate TOOL (PARM-06)
    if [[ -z "$TOOL" ]]; then
        echo "Error: Tool is required. Use -t or --tool to specify (fio, vdbench, mdtest, pjdtest, ltp, int)."
        error=1
    elif [[ ! "$TOOL" =~ ^(fio|vdbench|mdtest|pjdtest|ltp|int)$ ]]; then
        echo "Error: Invalid tool '$TOOL'. Valid options: fio, vdbench, mdtest, pjdtest, ltp, int"
        error=1
    fi

    # Validate SCENARIO (PARM-06) - mdtest doesn't require a scenario
    if [[ "$TOOL" != "mdtest" ]]; then
        if [[ -z "$SCENARIO" ]]; then
            echo "Error: Scenario is required. Use -s or --scenario to specify."
            error=1
        else
            # Check if scenario exists (either in /custom/ or /scenarios/)
            if ! scenario_exists "$TOOL" "$SCENARIO"; then
                echo "Error: Scenario '$SCENARIO' not found for tool '$TOOL'"
                error=1
            fi
        fi
    fi

    # Validate MOUNT directory
    if [[ ! -d "$MOUNT" ]]; then
        echo "Error: Mount point '$MOUNT' does not exist"
        error=1
    fi

    # Validate OUTPUT directory (or that it can be created)
    if [[ ! -d "$OUTPUT" ]]; then
        if ! mkdir -p "$OUTPUT" 2>/dev/null; then
            echo "Error: Cannot create output directory '$OUTPUT'"
            error=1
        fi
    fi

    # Validate MODE
    if [[ ! "$MODE" =~ ^(one-shot|long-running)$ ]]; then
        echo "Error: Invalid mode '$MODE'. Valid modes: one-shot, long-running"
        error=1
    fi

    if [[ $error -eq 1 ]]; then
        echo ""
        echo "Run 'entrypoint.sh --help' for usage information."
        exit 1
    fi
}

scenario_exists() {
    local tool="$1"
    local scenario="$2"

    # Check custom override first
    case "$tool" in
        fio)
            # Accept "all" to run all scenarios
            if [[ "$scenario" == "all" ]]; then
                return 0
            fi
            # Check exact match first
            if [[ -f "/custom/${scenario}.fio" ]] || [[ -f "/custom/${scenario}.conf" ]] || [[ -f "${SCENARIOS_DIR}/fio/${scenario}.fio" ]]; then
                return 0
            fi
            # Check for prefix matches (e.g., seq_read matches seq_read_*.fio)
            if [[ -n "$(ls "${SCENARIOS_DIR}/fio/${scenario}"_*.fio 2>/dev/null | head -1)" ]]; then
                return 0
            fi
            return 1
            ;;
        vdbench)
            [[ -f "/custom/${scenario}.par" ]] || [[ -f "${SCENARIOS_DIR}/vdbench/${scenario}.par" ]]
            ;;
        mdtest)
            # mdtest scenarios: mdtest_z0_n100, mdtest_z5_b4_I1, mdtest_z6_b3_I1, mdtest_z9_b2_I1
            # Also accept "all" or "mdtest" to run all scenarios
            if [[ "$scenario" == "all" ]] || [[ "$scenario" == "mdtest" ]]; then
                return 0
            fi
            [[ -f "${SCENARIOS_DIR}/mdtest/${scenario}.sh" ]]
            ;;
        pjdtest)
            # pjdtest: accept "all" or "pjdtest" to run all tests
            [[ "$scenario" == "all" ]] || [[ "$scenario" == "pjdtest" ]]
            ;;
        ltp)
            # ltp scenarios: all, fs, fsx, io, dir, lock, syscalls
            [[ "$scenario" == "all" ]] || [[ "$scenario" =~ ^(fs|fsx|io|dir|lock|syscalls)$ ]]
            ;;
        int|integration)
            # int scenarios: quota, client, cache_node, chaos, all
            [[ "$scenario" == "all" ]] || [[ "$scenario" =~ ^(quota|client|cache_node|chaos)$ ]]
            ;;
        *)
            return 1
            ;;
    esac
}

get_scenario_paths() {
    local tool="$1"
    local scenario="$2"
    local paths=()

    case "$tool" in
        fio)
            # If "all", run all 4 scenario types
            if [[ "$scenario" == "all" ]]; then
                # Run all 4 scenario types: seq_read, seq_write, rand_read, rand_write
                local all_types="seq_read seq_write rand_read rand_write"
                for type in $all_types; do
                    while IFS= read -r file; do
                        paths+=("$file")
                    done < <(ls "${SCENARIOS_DIR}/fio/${type}"_*.fio 2>/dev/null | sort)
                done
            # Check custom override first (exact match only)
            elif [[ -f "/custom/${scenario}.fio" ]]; then
                paths+=("/custom/${scenario}.fio")
            elif [[ -f "/custom/${scenario}.conf" ]]; then
                paths+=("/custom/${scenario}.conf")
            elif [[ -f "${SCENARIOS_DIR}/fio/${scenario}.fio" ]]; then
                paths+=("${SCENARIOS_DIR}/fio/${scenario}.fio")
            else
                # Check for prefix matches
                while IFS= read -r file; do
                    paths+=("$file")
                done < <(ls "${SCENARIOS_DIR}/fio/${scenario}"_*.fio 2>/dev/null | sort)
            fi
            ;;
        vdbench)
            if [[ -f "/custom/${scenario}.par" ]]; then
                paths+=("/custom/${scenario}.par")
            else
                paths+=("${SCENARIOS_DIR}/vdbench/${scenario}.par")
            fi
            ;;
        mdtest)
            # mdtest can run all scenarios at once
            if [[ "$scenario" == "all" ]] || [[ "$scenario" == "mdtest" ]]; then
                for script in "${SCENARIOS_DIR}"/mdtest/*.sh; do
                    [[ -f "$script" ]] && paths+=("$script")
                done
            else
                paths+=("${SCENARIOS_DIR}/mdtest/${scenario}.sh")
            fi
            ;;
    esac

    # Print paths (one per line) - use printf to preserve newlines
    for path in "${paths[@]}"; do
        printf '%s\n' "$path"
    done
}

get_scenario_name() {
    # Extract scenario name from file path
    local path="$1"
    local filename=$(basename "$path" .fio)
    echo "$filename"
}

# ==============================================================================
# Argument Parsing
# ==============================================================================

parse_args() {
    # Check for -- separator and extract app args
    local app_args=()
    local found_separator=false

    for arg in "$@"; do
        if [[ "$found_separator" == true ]]; then
            app_args+=("$arg")
        elif [[ "$arg" == "--" ]]; then
            found_separator=true
        else
            app_args+=("$arg")
        fi
    done

    # Use getopt for long options support
    local opts
    opts=$(getopt -o t:s:m:o:n:h \
                  -l tool:,scenario:,mount:,output:,np:,help \
                  -n 'entrypoint.sh' -- "${app_args[@]}" 2>&1) || {
        echo "Error: $opts"
        exit 1
    }

    eval set -- "$opts"

    while true; do
        case "$1" in
            -t|--tool)
                TOOL="$2"
                # Check if next arg is --help
                if [[ "$3" == "--help" ]]; then
                    case "$TOOL" in
                        fio) show_fio_help; exit 0 ;;
                        vdbench) echo "vdbench: use --help for general help"; exit 0 ;;
                        mdtest) show_mdtest_help; exit 0 ;;
                        pjdtest) show_pjdtest_help; exit 0 ;;
                        ltp) show_ltp_help; exit 0 ;;
                        int|integration) show_int_help; exit 0 ;;
                        *) echo "Unknown tool: $TOOL"; exit 1 ;;
                    esac
                fi
                shift 2
                ;;
            -s|--scenario)
                SCENARIO="$2"
                shift 2
                ;;
            -m|--mount)
                MOUNT="$2"
                shift 2
                ;;
            -o|--output)
                OUTPUT="$2"
                shift 2
                ;;
            -n|--np)
                NP="$2"
                shift 2
                ;;
            --mode)
                MODE="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            --)
                shift
                break
                ;;
            *)
                echo "Error: Unknown option '$1'"
                exit 1
                ;;
        esac
    done
}

# ==============================================================================
# Result Logging Functions
# ==============================================================================

# Log test result to result.log
# Usage: log_result <tool> <scenario> <exit_code> <start_time> <output_dir> [status_override] [details_override]
log_result() {
    local tool="$1"
    local scenario="$2"
    local exit_code="$3"
    local start_time_str="$4"
    local output_dir="$5"
    local status_override="${6:-}"
    local details_override="${7:-}"
    local result_log="$output_dir/result.log"

    # Calculate execution time using epoch seconds
    local end_time=$(date +%s)
    local start_time=$(date -d "$start_time_str" +%s 2>/dev/null || echo "$end_time")
    local duration=$((end_time - start_time))
    local duration_str=""
    if [[ $duration -ge 60 ]]; then
        duration_str="${duration}s ($((${duration} / 60))m $((${duration} % 60))s)"
    else
        duration_str="${duration}s"
    fi

    # Determine success/failure based on tool-specific criteria
    local status="FAIL"
    local details=""

    case "$tool" in
        fio)
            # Check if summary report has normal metrics (latency or bandwidth)
            if [[ -f "$output_dir/${scenario}_summary_"*.md ]]; then
                local summary_file
                summary_file=$(ls "$output_dir"/${scenario}_summary_*.md 2>/dev/null | head -1)
                if [[ -n "$summary_file" ]] && grep -qE "(latency|bandwidth|bw|MiB|BW)" "$summary_file" 2>/dev/null; then
                    # Check if values are non-zero
                    if grep -qE "(latency|bandwidth|bw|MiB|BW).*[^0-.]" "$summary_file" 2>/dev/null; then
                        status="SUCCESS"
                    fi
                fi
            fi
            # Also check JSON for actual data
            if [[ -f "$output_dir/fio.json" ]]; then
                if grep -q '"bw" : [1-9]' "$output_dir/fio.json" 2>/dev/null; then
                    status="SUCCESS"
                fi
            fi
            ;;
        mdtest)
            # Check mdtest.raw for "SUMMARY rate" to determine success
            # mdtest.raw is in subdirectories: $output_dir/{scenario}/mdtest.raw
            local found_summary=false
            for raw_file in "$output_dir"/*/mdtest.raw; do
                if [[ -f "$raw_file" ]] && grep -q "SUMMARY rate" "$raw_file" 2>/dev/null; then
                    found_summary=true
                    break
                fi
            done
            if [[ "$found_summary" == "true" ]]; then
                status="SUCCESS"
                details="mdtest completed successfully"
            fi
            ;;
        pjdtest)
            # Check if output contains PASS or FAIL
            # Find the most recent pjdtest output file
            local pjdtest_output
            pjdtest_output=$(ls -t "$output_dir"/pjdtest_* 2>/dev/null | head -1)
            if [[ -n "$pjdtest_output" ]] && [[ -f "$pjdtest_output" ]]; then
                # Check for PASS/FAIL result
                if grep -qE "(Result:|PASS|FAIL)" "$pjdtest_output" 2>/dev/null; then
                    status="SUCCESS"
                    details=$(grep -E "(Result:|PASS|FAIL)" "$pjdtest_output" 2>/dev/null | tail -1 || true)
                fi
            fi
            ;;
        vdbench)
            # vdbench success based on exit code
            if [[ $exit_code -eq 0 ]]; then
                status="SUCCESS"
            fi
            ;;
        ltp)
            # ltp success based on exit code
            if [[ $exit_code -eq 0 ]]; then
                status="SUCCESS"
            fi
            ;;
        int)
            # For integration tests, use the parsed results if provided
            # Otherwise, try to parse from log file
            if [[ -n "$status_override" ]]; then
                status="$status_override"
                details="$details_override"
            else
                # Try to find passed/failed counts from log
                local int_log_file
                int_log_file=$(ls -t "$output_dir"/int_*.log 2>/dev/null | head -1)
                if [[ -n "$int_log_file" ]] && [[ -f "$int_log_file" ]]; then
                    local passed_count=$(grep "Passed:" "$int_log_file" 2>/dev/null | tail -1 | sed 's/.*Passed: //' | sed 's/[^0-9].*//' || echo "0")
                    local failed_count=$(grep "Failed:" "$int_log_file" 2>/dev/null | tail -1 | sed 's/.*Failed: //' | sed 's/[^0-9].*//' || echo "0")

                    if [[ -n "$failed_count" ]] && [[ "$failed_count" == "0" ]]; then
                        status="SUCCESS"
                        details="Integration tests passed (Passed: ${passed_count:-0}, Failed: ${failed_count:-0})"
                    elif [[ -n "$failed_count" ]] && [[ "$failed_count" -gt "0" ]]; then
                        status="FAIL"
                        details="Integration tests failed (Passed: ${passed_count:-0}, Failed: ${failed_count:-0})"
                    fi
                fi
            fi
            ;;
    esac

    # Append to result.log in the scenario directory
    {
        echo "========================================"
        echo "Tool: $tool"
        echo "Scenario: $scenario"
        echo "Start Time: $start_time_str"
        echo "Duration: $duration_str"
        echo "Exit Code: $exit_code"
        echo "Status: $status"
        [[ -n "$details" ]] && echo "Details: $details"
        echo "Command: $tool -s $scenario -m $MOUNT -o $output_dir"
        echo ""
    } >> "$result_log"

    # Also append to result.log in the base OUTPUT directory
    # This ensures users can find the log in the main output directory
    if [[ "$output_dir" != "$OUTPUT" ]]; then
        local base_result_log="$OUTPUT/result.log"
        {
            echo "========================================"
            echo "Tool: $tool"
            echo "Scenario: $scenario"
            echo "Start Time: $start_time_str"
            echo "Duration: $duration_str"
            echo "Exit Code: $exit_code"
            echo "Status: $status"
            [[ -n "$details" ]] && echo "Details: $details"
            echo "Command: $tool -s $scenario -m $MOUNT -o $output_dir"
            echo ""
        } >> "$base_result_log"
        echo "Result also logged to: $base_result_log"
    fi

    echo "Result logged to: $result_log"
}


# ==============================================================================
# Tool Dispatch Functions
# ==============================================================================

dispatch_tool() {
    case "$TOOL" in
        fio)
            fio_run
            ;;
        vdbench)
            vdbench_run
            ;;
        mdtest)
            mdtest_run
            ;;
        pjdtest)
            pjdtest_run
            ;;
        ltp)
            ltp_run
            ;;
        int|integration)
            integration_run
            ;;
        *)
            echo "Error: Unknown tool '$TOOL'"
            exit 1
            ;;
    esac
}

fio_run() {
    # Get all matching scenario paths
    local scenario_paths
    scenario_paths=$(get_scenario_paths fio "$SCENARIO")

    local path_count
    path_count=$(echo "$scenario_paths" | grep -c "^" || true)

    if [[ -z "$scenario_paths" ]] || [[ "$path_count" -eq 0 ]]; then
        echo "Error: No scenario found for '$SCENARIO'"
        exit 1
    fi

    echo "Found $path_count scenario(s) for '$SCENARIO'"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"
    echo ""

    # Create base output directory and tool subdirectory
    mkdir -p "$OUTPUT"
    mkdir -p "$OUTPUT/fio"

    # Determine output subdirectory based on SCENARIO
    # For "all", use scenario type subdirectories (seq_read, seq_write, rand_read, rand_write)
    # For specific scenario, use SCENARIO directly
    local output_subdir="$SCENARIO"

    local overall_exit=0
    local run_num=0

    # Run each scenario
    while IFS= read -r config; do
        [[ -z "$config" ]] && continue

        run_num=$((run_num + 1))
        local scenario_name
        scenario_name=$(get_scenario_name "$config")

        # For "all" scenario, group by scenario type (seq_read, seq_write, etc.)
        # For specific scenario, also use subdirectory for each variant
        if [[ "$SCENARIO" == "all" ]]; then
            # Extract scenario type from config filename (e.g., seq_read_0d_128k_1j -> seq_read)
            # Use first two underscore-separated parts
            local scenario_type
            scenario_type=$(echo "$scenario_name" | cut -d'_' -f1,2)
            local scenario_output="$OUTPUT/fio/$scenario_type/$scenario_name"
        else
            # Each variant gets its own subdirectory
            local scenario_output="$OUTPUT/fio/$SCENARIO/$scenario_name"
        fi
        local scenario_start_time=$(date +"%Y-%m-%d %H:%M:%S")

        echo "=============================================="
        echo "Running scenario $run_num/$path_count: $scenario_name"
        echo "Config: $config"
        echo "Output: $scenario_output"
        echo "=============================================="

        # Create output directory for this scenario
        mkdir -p "$scenario_output"

        # Build fio command
        local fio_cmd=("$FIO_BIN" "$config" "--output-format=json")

        # Override directory if MOUNT is specified
        if [[ -d "$MOUNT" ]]; then
            fio_cmd+=("--directory=$MOUNT")
        fi

        echo "Executing: ${fio_cmd[*]}"

        # Run fio and capture output - allow Ctrl+C to interrupt
        # Use subshell to handle signals properly
        (
            trap 'kill -INT $$' INT TERM
            "${fio_cmd[@]}" 2>&1 | tee "$scenario_output/fio.raw" > "$scenario_output/fio.json"
        )
        local fio_exit=${PIPESTATUS[0]}

        if [[ $fio_exit -ne 0 ]]; then
            echo "Warning: Scenario '$scenario_name' exited with code $fio_exit"
            overall_exit=$fio_exit
        fi

        # Generate report for this scenario
        echo "Generating report for $scenario_name..."
        python3 /scripts/generate_report.py --tool fio --output-dir "$scenario_output" --scenario "$scenario_name" --mount "$MOUNT"

        # Log result
        log_result "fio" "$scenario_name" "$fio_exit" "$scenario_start_time" "$scenario_output"

        # Calculate duration for notification
        local scenario_end_time=$(date +%s)
        local scenario_start_epoch=$(date -d "$scenario_start_time" +%s 2>/dev/null || echo "$scenario_end_time")
        local scenario_duration=$((scenario_end_time - scenario_start_epoch))
        local scenario_duration_str=""
        if [[ $scenario_duration -ge 60 ]]; then
            scenario_duration_str="${scenario_duration}s ($((${scenario_duration} / 60))m $((${scenario_duration} % 60))s)"
        else
            scenario_duration_str="${scenario_duration}s"
        fi

        # Send WeChat notification if enabled
        if [[ "$WECHAT_ENABLED" == "yes" ]]; then
            local fio_status="FAIL"
            if [[ $fio_exit -eq 0 ]]; then
                fio_status="SUCCESS"
            fi
            send_wechat_notification "fio" "$scenario_name" "$fio_status" "$scenario_duration_str"
        fi

        echo ""
    done <<< "$scenario_paths"

    # Generate combined report if multiple scenarios
    if [[ $path_count -gt 1 ]]; then
        echo "Generating combined report..."
        # For "all" scenario, aggregate from all scenario type subdirectories
        # For specific scenario, use that scenario's subdirectory
        if [[ "$SCENARIO" == "all" ]]; then
            python3 /scripts/generate_report.py --tool fio --output-dir "$OUTPUT/fio" --scenario "$SCENARIO" --mount "$MOUNT" --combined
        else
            python3 /scripts/generate_report.py --tool fio --output-dir "$OUTPUT/fio/$SCENARIO" --scenario "$SCENARIO" --mount "$MOUNT" --combined
        fi
    fi

    echo ""
    echo "All fio scenarios completed."
    return $overall_exit
}

vdbench_run() {
    local config
    config=$(get_scenario_paths vdbench "$SCENARIO" | head -1)

    local vdbench_start_time=$(date +"%Y-%m-%d %H:%M:%S")

    echo "Running vdbench with config: $config"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"

    # Create output directory and tool subdirectory
    mkdir -p "$OUTPUT"
    mkdir -p "$OUTPUT/vdbench/$SCENARIO"

    # Replace anchor paths in config with MOUNT if needed
    # vdbench configs often have wd= anchor=/path/to/mount
    local vdbench_output="$OUTPUT/vdbench/$SCENARIO"
    local vdbench_cmd=("$VDBENCH_BIN" "-f" "$config" "-o" "$vdbench_output")

    # Change to vdbench directory for execution
    cd "$VDBENCH_DIR"

    echo "Executing: ./vdbench -f $config -o $vdbench_output"

    # Capture console output to raw file while running vdbench
    # Use subshell to allow Ctrl+C to interrupt
    (
        trap 'kill -INT $$' INT TERM
        "./vdbench" -f "$config" -o "$vdbench_output" 2>&1 | tee "$vdbench_output/vdbench.raw"
    )
    local vdbench_exit=${PIPESTATUS[0]}

    # Generate reports
    echo "Generating reports..."
    python3 /scripts/generate_report.py --tool vdbench --output-dir "$vdbench_output" --scenario "$SCENARIO" --mount "$MOUNT"

    # Log result
    log_result "vdbench" "$SCENARIO" "$vdbench_exit" "$vdbench_start_time" "$vdbench_output"

    # Calculate duration for notification
    local vdbench_end_time=$(date +%s)
    local vdbench_start_epoch=$(date -d "$vdbench_start_time" +%s 2>/dev/null || echo "$vdbench_end_time")
    local vdbench_duration=$((vdbench_end_time - vdbench_start_epoch))
    local vdbench_duration_str=""
    if [[ $vdbench_duration -ge 60 ]]; then
        vdbench_duration_str="${vdbench_duration}s ($((${vdbench_duration} / 60))m $((${vdbench_duration} % 60))s)"
    else
        vdbench_duration_str="${vdbench_duration}s"
    fi

    # Send WeChat notification if enabled
    if [[ "$WECHAT_ENABLED" == "yes" ]]; then
        local vdbench_status="FAIL"
        if [[ $vdbench_exit -eq 0 ]]; then
            vdbench_status="SUCCESS"
        fi
        send_wechat_notification "vdbench" "$SCENARIO" "$vdbench_status" "$vdbench_duration_str"
    fi

    return $vdbench_exit
}

mdtest_run() {
    # Get all matching scenario paths
    local scenario_paths
    scenario_paths=$(get_scenario_paths mdtest "$SCENARIO")

    local path_count
    path_count=$(echo "$scenario_paths" | grep -c "^" || true)

    if [[ -z "$scenario_paths" ]] || [[ "$path_count" -eq 0 ]]; then
        echo "Error: No scenario found for '$SCENARIO'"
        exit 1
    fi

    echo "Found $path_count mdtest scenario(s) for '$SCENARIO'"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"
    echo "  NP: $NP"
    echo ""

    # Create base output directory and tool subdirectory
    mkdir -p "$OUTPUT"
    mkdir -p "$OUTPUT/mdtest"

    local overall_exit=0
    local run_num=0

    # Change to mount directory for test execution
    cd "$MOUNT"

    # Export MDTEST_NP for use by scenario scripts
    export MDTEST_NP="$NP"

    # Run each scenario
    # Use array instead of while read to avoid set -e issues
    mapfile -t scenario_array <<< "$scenario_paths"
    local total=${#scenario_array[@]}
    local run_num=0

    # Arrays to collect scenario info for later logging
    local -a scenario_names=()
    local -a scenario_exits=()
    local -a scenario_times=()

    # Output subdirectory for mdtest
    # For "all", each scenario goes to its own subdirectory
    # For specific scenario, use that scenario's subdirectory
    local mdtest_base="$OUTPUT/mdtest"

    for script in "${scenario_array[@]}"; do
        [[ -z "$script" ]] && continue

        run_num=$((run_num + 1))
        local scenario_name
        scenario_name=$(basename "$script" .sh)
        # Each scenario gets its own subdirectory
        local scenario_output="$mdtest_base/$scenario_name"
        local scenario_start_time=$(date +"%Y-%m-%d %H:%M:%S")

        echo "=============================================="
        echo "Running mdtest scenario $run_num/$total: $scenario_name"
        echo "Script: $script"
        echo "Output: $scenario_output"
        echo "=============================================="

        # Create output directory for this scenario
        mkdir -p "$scenario_output"

        echo "Executing: $script"

        # Run the mdtest scenario script
        # Capture output to raw file
        set +e
        "$script" > "$scenario_output/mdtest.raw" 2>&1
        local mdtest_exit=$?
        set -e

        if [[ $mdtest_exit -ne 0 ]]; then
            echo "Warning: Scenario '$scenario_name' exited with code $mdtest_exit"
            overall_exit=$mdtest_exit
        fi

        # Collect scenario info for later
        scenario_names+=("$scenario_name")
        scenario_exits+=("$mdtest_exit")
        scenario_times+=("$scenario_start_time")

        echo "" || true
    done

    # Generate combined report for all mdtest scenarios (BEFORE logging results)
    # For "all", generate combined report at base mdtest dir
    # For specific scenario, generate at that scenario's dir
    echo "Generating combined mdtest report..."
    if [[ "$SCENARIO" == "all" ]]; then
        python3 /scripts/generate_report.py --tool mdtest --output-dir "$mdtest_base" --scenario "mdtest" --mount "$MOUNT" --np "$NP" --combined
        local mdtest_report_dir="$mdtest_base"
    else
        python3 /scripts/generate_report.py --tool mdtest --output-dir "$mdtest_base/$SCENARIO" --scenario "$SCENARIO" --mount "$MOUNT" --np "$NP" --combined
        local mdtest_report_dir="$mdtest_base/$SCENARIO"
    fi

    # Now log results for each scenario (combined summary now exists)
    for i in "${!scenario_names[@]}"; do
        log_result "mdtest" "${scenario_names[$i]}" "${scenario_exits[$i]}" "${scenario_times[$i]}" "$mdtest_report_dir"

        # Calculate duration for notification
        local mdtest_end_time=$(date +%s)
        local mdtest_start_epoch=$(date -d "${scenario_times[$i]}" +%s 2>/dev/null || echo "$mdtest_end_time")
        local mdtest_duration=$((mdtest_end_time - mdtest_start_epoch))
        local mdtest_duration_str=""
        if [[ $mdtest_duration -ge 60 ]]; then
            mdtest_duration_str="${mdtest_duration}s ($((${mdtest_duration} / 60))m $((${mdtest_duration} % 60))s)"
        else
            mdtest_duration_str="${mdtest_duration}s"
        fi

        # Send WeChat notification if enabled
        if [[ "$WECHAT_ENABLED" == "yes" ]]; then
            local mdtest_status="FAIL"
            if [[ ${scenario_exits[$i]} -eq 0 ]]; then
                mdtest_status="SUCCESS"
            fi
            send_wechat_notification "mdtest" "${scenario_names[$i]}" "$mdtest_status" "$mdtest_duration_str"
        fi
    done

    echo ""
    echo "All mdtest scenarios completed."
    return $overall_exit
}

pjdtest_run() {
    local pjdtest_start_time=$(date +"%Y-%m-%d %H:%M:%S")

    echo "Running pjdtest"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"

    # Create output directory and tool subdirectory
    mkdir -p "$OUTPUT"
    mkdir -p "$OUTPUT/pjdtest/$SCENARIO"

    # Change to mount directory for test execution
    cd "$MOUNT"

    # Generate timestamp for output file
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    local pjdtest_output="$OUTPUT/pjdtest/$SCENARIO"
    local output_file="${pjdtest_output}/pjdtest_${timestamp}"

    echo "Executing: prove -rv /pjdtest/dingofs_baseline"
    echo "Output file: ${output_file}"

    # Run pjdtest using prove - allow Ctrl+C to interrupt
    (
        trap 'kill -INT $$' INT TERM
        prove -rv /pjdtest/dingofs_baseline > "${output_file}" 2>&1
    )
    local pjdtest_exit=$?

    if [[ $pjdtest_exit -ne 0 ]]; then
        echo "Warning: pjdtest exited with code $pjdtest_exit"
    else
        echo "pjdtest completed successfully."
    fi

    # Log result
    log_result "pjdtest" "pjdtest" "$pjdtest_exit" "$pjdtest_start_time" "$pjdtest_output"

    # Calculate duration for notification
    local pjdtest_end_time=$(date +%s)
    local pjdtest_start_epoch=$(date -d "$pjdtest_start_time" +%s 2>/dev/null || echo "$pjdtest_end_time")
    local pjdtest_duration=$((pjdtest_end_time - pjdtest_start_epoch))
    local pjdtest_duration_str=""
    if [[ $pjdtest_duration -ge 60 ]]; then
        pjdtest_duration_str="${pjdtest_duration}s ($((${pjdtest_duration} / 60))m $((${pjdtest_duration} % 60))s)"
    else
        pjdtest_duration_str="${pjdtest_duration}s"
    fi

    # Send WeChat notification if enabled
    if [[ "$WECHAT_ENABLED" == "yes" ]]; then
        local pjdtest_status="FAIL"
        if [[ $pjdtest_exit -eq 0 ]]; then
            pjdtest_status="SUCCESS"
        fi
        send_wechat_notification "pjdtest" "pjdtest" "$pjdtest_status" "$pjdtest_duration_str"
    fi

    echo ""
    echo "Results saved to: ${output_file}"
    return $pjdtest_exit
}

ltp_run() {
    local ltp_start_time=$(date +"%Y-%m-%d %H:%M:%S")

    echo "Running LTP test suite"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"
    echo "  Scenario: $SCENARIO"

    # Create output directory and tool subdirectory
    mkdir -p "$OUTPUT"
    mkdir -p "$OUTPUT/ltp/$SCENARIO"

    # Change to mount directory for test execution
    cd "$MOUNT"

    # Generate timestamp for output file
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    local ltp_output="$OUTPUT/ltp/$SCENARIO"
    local output_file="${ltp_output}/ltp_${timestamp}"

    # Map scenario names to LTP test suite names
    # all -> fs fsx io dir lock syscalls (run all common tests)
    # fs -> fs (filesystem tests)
    # fsx -> fsxattr (filesystem extended attribute tests)
    # io -> dio (direct I/O tests)
    # dir -> fs (directory tests use fs suite)
    # lock -> fcntl-locktests (file lock tests)
    # syscalls -> syscalls (system call tests)
    local scenarios
    case "${SCENARIO}" in
        all)
            scenarios="fs fsxattr dio fcntl-locktests syscalls"
            ;;
        fs)
            scenarios="fs"
            ;;
        fsx)
            scenarios="fsxattr"
            ;;
        io)
            scenarios="dio"
            ;;
        dir)
            scenarios="fs"
            ;;
        lock)
            scenarios="fcntl-locktests"
            ;;
        syscalls)
            scenarios="syscalls"
            ;;
        *)
            scenarios="${SCENARIO:-fs}"
            ;;
    esac

    local overall_exit=0
    for scenario in $scenarios; do
        echo "Executing LTP scenario: $scenario"
        # Use subshell to allow Ctrl+C to interrupt
        (
            trap 'kill -INT $$' INT TERM
            timeout 3600 /opt/ltp/runltp -f "$scenario" -d . -p "$OUTPUT" -l "${output_file}_${scenario}.log" 2>&1 | tee "${output_file}_${scenario}.raw"
        )
        local ltp_exit=${PIPESTATUS[0]}
        if [[ $ltp_exit -ne 0 ]]; then
            overall_exit=$ltp_exit
        fi
    done

    if [[ $overall_exit -eq 124 ]]; then
        echo "Warning: LTP test timed out after 3600 seconds"
    elif [[ $overall_exit -ne 0 ]]; then
        echo "Warning: LTP exited with code $overall_exit"
    else
        echo "LTP tests completed successfully."
    fi

    # Copy LTP results from /opt/ltp/results to OUTPUT/ltp directory
    if [[ -d "/opt/ltp/results" ]] && [[ -n "$(ls -A /opt/ltp/results 2>/dev/null)" ]]; then
        echo "Copying LTP results to ${ltp_output}..."
        cp -r /opt/ltp/results/* "$ltp_output/" 2>/dev/null || true
        echo "LTP results copied to: ${ltp_output}"
    fi

    # Log result
    log_result "ltp" "$SCENARIO" "$overall_exit" "$ltp_start_time" "$ltp_output"

    # Calculate duration for notification
    local ltp_end_time=$(date +%s)
    local ltp_start_epoch=$(date -d "$ltp_start_time" +%s 2>/dev/null || echo "$ltp_end_time")
    local ltp_duration=$((ltp_end_time - ltp_start_epoch))
    local ltp_duration_str=""
    if [[ $ltp_duration -ge 60 ]]; then
        ltp_duration_str="${ltp_duration}s ($((${ltp_duration} / 60))m $((${ltp_duration} % 60))s)"
    else
        ltp_duration_str="${ltp_duration}s"
    fi

    # Send WeChat notification if enabled
    if [[ "$WECHAT_ENABLED" == "yes" ]]; then
        local ltp_status="FAIL"
        if [[ $overall_exit -eq 0 ]]; then
            ltp_status="SUCCESS"
        fi
        send_wechat_notification "ltp" "$SCENARIO" "$ltp_status" "$ltp_duration_str"
    fi

    echo ""
    echo "Results saved to: ${output_file}_*.log"
    return $overall_exit
}

integration_run() {
    echo "Running DingoFS Integration Tests..."
    echo "  Module: $SCENARIO"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"
    echo ""

    # Get MDS address from environment
    local mdsaddr="${MDSADDR:-}"
    if [[ -z "$mdsaddr" ]]; then
        echo "Error: MDSADDR environment variable not set"
        echo "Please set MDS address via: dtt config set mdsaddr <address>"
        exit 1
    fi

    # Create output directory
    mkdir -p "$OUTPUT"
    mkdir -p "$OUTPUT/integration/$SCENARIO"
    mkdir -p "$OUTPUT/integration/$SCENARIO/allure-results"

    local start_time=$(date +"%Y-%m-%d %H:%M:%S")
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local int_output="$OUTPUT/integration/$SCENARIO"
    local log_file="$int_output/int_${timestamp}.log"

    # Create dynamic environment config in the framework's conf directory
    local dynamic_env_dir="$INTEGRATION_DIR/conf/env"
    local dynamic_env_file="$dynamic_env_dir/env_dynamic.yaml"

    mkdir -p "$dynamic_env_dir"
    cat > "$dynamic_env_file" << EOF
env_dynamic:
  mds_addr: ${mdsaddr}
  webhook_url: ''
  clients:
  - host: localhost
    mount_path: ${MOUNT}
    fs_name: fs-test
    dingo_tool_path: /usr/local/bin/dingo
    client_count: 1
    client_conf:
      mds.addr: ${mdsaddr}
  remote_caches: []
  storage:
    storage_type: s3
    storage_env: minio
EOF

    echo "Using MDS address: $mdsaddr"
    echo "Dynamic env file: $dynamic_env_file"
    echo ""
    echo "Log file: $log_file"
    echo ""

    # Run the integration test framework
    # Default module is quota if not specified
    local module="${SCENARIO:-quota}"

    cd "$INTEGRATION_DIR"

    # Run tests with dynamic environment and proper report directory
    # Use subshell to allow Ctrl+C to interrupt
    (
        trap 'kill -INT $$' INT TERM
        python3 run_tests.py "$module" --env env_dynamic --skip-setup \
            --report-dir "$int_output/allure-results" 2>&1 | tee "$log_file"
    )
    local exit_code=${PIPESTATUS[0]}

    # Parse test results from the log output
    local int_passed=0
    local int_failed=0
    local int_total=0
    local int_skipped=0

    # Extract test statistics from log (format: "Passed: X", "Failed: Y", "Total Cases: Z")
    if grep -q "Passed:" "$log_file"; then
        int_total=$(grep "Total Cases:" "$log_file" | sed 's/.*Total Cases: //' | sed 's/ .*//' || echo "0")
        int_passed=$(grep "Passed:" "$log_file" | sed 's/.*Passed: //' | sed 's/ .*//' || echo "0")
        int_failed=$(grep "Failed:" "$log_file" | sed 's/.*Failed: //' | sed 's/ .*//' || echo "0")
        int_skipped=$(grep "Skipped:" "$log_file" | sed 's/.*Skipped: //' | sed 's/ .*//' || echo "0")
    fi

    echo ""
    echo "=========================================="
    echo "Integration Test Summary:"
    echo "  Total: $int_total"
    echo "  Passed: $int_passed"
    echo "  Failed: $int_failed"
    echo "  Skipped: $int_skipped"
    echo "=========================================="
    echo ""

    # Determine success based on parsed results
    local status="FAIL"
    if [[ "$int_failed" == "0" ]] && [[ "$int_total" -gt "0" ]]; then
        status="SUCCESS"
    fi

    # Set details string for log_result
    local details="Total: $int_total, Passed: $int_passed, Failed: $int_failed"

    echo "Integration tests completed with exit code: $exit_code"
    echo "Status: $status"
    echo "Log saved to: $log_file"
    echo "Allure results saved to: $OUTPUT/integration/allure-results"

    # Log result with parsed details
    log_result "int" "$module" "$exit_code" "$start_time" "$int_output" "$status" "$details"

    # Calculate duration for notification
    local int_end_time=$(date +%s)
    local int_start_epoch=$(date -d "$start_time" +%s 2>/dev/null || echo "$int_end_time")
    local int_duration=$((int_end_time - int_start_epoch))
    local int_duration_str=""
    if [[ $int_duration -ge 60 ]]; then
        int_duration_str="${int_duration}s ($((${int_duration} / 60))m $((${int_duration} % 60))s)"
    else
        int_duration_str="${int_duration}s"
    fi

    # Send WeChat notification if enabled
    if [[ "$WECHAT_ENABLED" == "yes" ]]; then
        send_wechat_notification "int" "$module" "$status" "$int_duration_str" "$details"
    fi

    exit $exit_code
}

# ==============================================================================
# Mode Handling
# ==============================================================================

run_one_shot() {
    echo "Running in one-shot mode..."
    dispatch_tool
    local exit_code=$?
    echo "Test completed with exit code: $exit_code"
    exit $exit_code
}

run_long_running() {
    echo "Running in long-running mode..."

    # First, run the initial test
    dispatch_tool
    local test_exit_code=$?

    if [[ $test_exit_code -eq 0 ]]; then
        echo ""
        echo "=============================================="
        echo "Test completed. Container staying alive for additional tests."
        echo "=============================================="
        echo ""
        echo "To run additional tests:"
        echo "  docker exec <container> entrypoint.sh -t fio -s rand_read -m /mnt/test"
        echo "  docker exec <container> entrypoint.sh -t vdbench -s seq_wr -m /mnt/test"
        echo "  docker exec <container> entrypoint.sh -t mdtest -s mdtest -m /mnt/test"
        echo ""
        echo "To stop the container: docker stop <container>"
        echo ""
    else
        echo "Initial test failed with exit code: $test_exit_code"
    fi

    # Set up signal handling for graceful shutdown
    trap 'echo "Received signal, shutting down..."; exit 0' SIGTERM SIGINT

    # Keep container alive
    echo "Container is now waiting. Press Ctrl+C to stop."
    tail -f /dev/null
}

# ==============================================================================
# Main Entry Point
# ==============================================================================

main() {
    # Parse command line arguments
    parse_args "$@"

    # Validate parameters
    validate_params

    echo "=============================================="
    echo "DingoFS Storage Testsuite Tools"
    echo "=============================================="
    echo "Tool:     $TOOL"
    echo "Scenario: $SCENARIO"
    echo "Mount:    $MOUNT"
    echo "Output:   $OUTPUT"
    echo "NP:       $NP"
    echo "Mode:     $MODE"
    echo "=============================================="
    echo ""

    # Execute based on mode
    if [[ "$MODE" == "long-running" ]]; then
        run_long_running
    else
        run_one_shot
    fi
}

# Run main with all arguments
main "$@"
