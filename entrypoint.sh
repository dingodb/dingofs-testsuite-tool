#!/bin/bash
#
# DingoFS Storage Benchmark Tools - Unified Entrypoint
# Parses CLI arguments, handles one-shot and long-running modes,
# dispatches to correct storage testing tool (fio/vdbench/mdtest)
#
# Usage:
#   docker run dingofs-benchmark-tools -t fio -s seq_read -m /mnt/test
#   docker run dingofs-benchmark-tools -t vdbench -s rand_read -m /mnt/test -o /tmp/results
#   docker run --detach dingofs-benchmark-tools -t fio -s randrw --mode long-running
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

# Tool paths (from Dockerfile)
FIO_BIN="/usr/bin/fio"
VDBENCH_BIN="/opt/vdbench/vdbench"
VDBENCH_DIR="/opt/vdbench"
MDTEST_BIN="/usr/local/bin/mdtest"

# Scenario directories
SCENARIOS_DIR="/scenarios"

# ==============================================================================
# Help Function
# ==============================================================================

show_help() {
    cat << EOF
DingoFS Storage Benchmark Tools
===============================

Usage:
  docker run dingofs-benchmark-tools -t <tool> -s <scenario> -m <mount> -o <output>

Options:
  -t, --tool      测试工具: fio, vdbench, mdtest
  -s, --scenario  测试场景
  -m, --mount     被测存储的挂载点 (例如: /mnt/test)
  -o, --output    测试结果输出目录 (例如: /output)
  --mode          运行模式: one-shot (默认) 或 long-running

注意: -o 指定的是容器内路径，需要通过 -v 将容器内目录映射到本机路径

Tools:
  fio       - Flexible I/O tester (存储性能测试)
  vdbench   - Oracle storage benchmark
  mdtest    - MPI filesystem metadata test
  pjdtest   - POSIX filesystem test suite
  ltp       - Linux Test Project (内核测试套件)

运行模式:
  one-shot      - 容器启动 → 运行测试 → 测试完成后容器退出 (默认)
  long-running   - 容器启动 → 运行测试 → 容器保持运行，可用 docker exec 执行更多测试

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

MDTEST Scenarios (4 types, each runs with 32 parallel tasks):
  mdtest_z0_n100   - z=0, n=100 (扁平目录, 3200 files)
  mdtest_z5_b4_I1  - z=5, b=4, I=1 (多分支树, 32736 items)
  mdtest_z6_b3_I1  - z=6, b=3, I=1 (中等深度树, 34976 items)
  mdtest_z9_b2_I1  - z=9, b=2, I=1 (深层二叉树, 32736 items)
  mdtest           - 运行以上所有4个场景

PJDTEST:
  pjdtest    - 运行 POSIX 文件系统测试套件 (prove -rv /pjdtest/dingofs_baseline)

LTP:
  ltp        - 运行 Linux Test Project 测试套件 (runltp -f fs)
  ltp_fs     - 文件系统测试 (fs)
  ltp_dio    - Direct I/O 测试 (dio)
  ltp_mm     - 内存管理测试 (mm)

注意: LTP 需要 --privileged 运行以访问 /dev/kmsg 等设备

Examples:
  # 运行所有 rand_read 场景 (24 tests)

Examples:
  # 运行所有 rand_read 场景 (24 tests)
  docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t fio -s rand_read -m /data -o /data

  # 运行所有 seq_write 场景 (24 tests)
  docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t fio -s seq_write -m /data -o /data

  # 运行单个特定场景
  docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t fio -s rand_read_0d_128k_1j -m /data -o /data

  # vdbench 测试
  docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t vdbench -s seq_rd -m /data -o /data

  # mdtest 测试 (运行所有4个场景并汇总)
  docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t mdtest -s mdtest -m /data -o /data

  # mdtest 单个场景测试
  docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t mdtest -s mdtest_z0_n100 -m /data -o /data

  # pjdtest 测试
  docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t pjdtest -s pjdtest -m /data -o /data

  # ltp 测试 (默认运行文件系统测试，需要 --privileged)
  docker run --rm --privileged -v /tmp/test:/data dingofs-benchmark-tools -t ltp -s ltp -m /data -o /data

  # 长期运行模式 (容器保持运行，可执行多个测试)
  docker run --detach -v /tmp/test:/data dingofs-benchmark-tools -t fio -s rand_read -m /data -o /data --mode long-running
  docker exec <container_id> entrypoint.sh -t fio -s seq_write -m /data -o /data

  # 分离挂载点和输出目录 (被测存储和结果保存到不同路径)
  docker run --rm \
    -v /mnt/disk1/test:/data \
    -v /tmp/results:/output \
    dingofs-benchmark-tools \
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
# Validation Functions
# ==============================================================================

validate_params() {
    local error=0

    # Validate TOOL (PARM-06)
    if [[ -z "$TOOL" ]]; then
        echo "Error: Tool is required. Use -t or --tool to specify (fio, vdbench, mdtest, pjdtest, ltp)."
        error=1
    elif [[ ! "$TOOL" =~ ^(fio|vdbench|mdtest|pjdtest|ltp)$ ]]; then
        echo "Error: Invalid tool '$TOOL'. Valid options: fio, vdbench, mdtest, pjdtest, ltp"
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
            # Also accept "mdtest" alone to run all scenarios
            if [[ "$scenario" == "mdtest" ]]; then
                return 0
            fi
            [[ -f "${SCENARIOS_DIR}/mdtest/${scenario}.sh" ]]
            ;;
        pjdtest)
            # pjdtest only has one scenario: pjdtest
            [[ "$scenario" == "pjdtest" ]]
            ;;
        ltp)
            # ltp scenarios: ltp (default), ltp_fs, ltp_mm, ltp_all
            [[ "$scenario" == "ltp" ]] || [[ "$scenario" =~ ^ltp_ ]]
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
            # Check custom override first (exact match only)
            if [[ -f "/custom/${scenario}.fio" ]]; then
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
            if [[ "$scenario" == "mdtest" ]]; then
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
    opts=$(getopt -o t:s:m:o:h \
                  -l tool:,scenario:,mount:,output:,mode:,help \
                  -n 'entrypoint.sh' -- "${app_args[@]}" 2>&1) || {
        echo "Error: $opts"
        exit 1
    }

    eval set -- "$opts"

    while true; do
        case "$1" in
            -t|--tool)
                TOOL="$2"
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

    # Create base output directory
    mkdir -p "$OUTPUT"

    local overall_exit=0
    local run_num=0

    # Run each scenario
    while IFS= read -r config; do
        [[ -z "$config" ]] && continue

        run_num=$((run_num + 1))
        local scenario_name
        scenario_name=$(get_scenario_name "$config")
        local scenario_output="$OUTPUT/$scenario_name"

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

        # Run fio and capture output
        "${fio_cmd[@]}" 2>&1 | tee "$scenario_output/fio.raw" > "$scenario_output/fio.json"
        local fio_exit=${PIPESTATUS[0]}

        if [[ $fio_exit -ne 0 ]]; then
            echo "Warning: Scenario '$scenario_name' exited with code $fio_exit"
            overall_exit=$fio_exit
        fi

        # Generate report for this scenario
        echo "Generating report for $scenario_name..."
        python3 /scripts/generate_report.py --tool fio --output-dir "$scenario_output" --scenario "$scenario_name" --mount "$MOUNT"

        echo ""
    done <<< "$scenario_paths"

    # Generate combined report if multiple scenarios
    if [[ $path_count -gt 1 ]]; then
        echo "Generating combined report..."
        python3 /scripts/generate_report.py --tool fio --output-dir "$OUTPUT" --scenario "$SCENARIO" --mount "$MOUNT" --combined
    fi

    echo ""
    echo "All fio scenarios completed."
    return $overall_exit
}

vdbench_run() {
    local config
    config=$(get_scenario_paths vdbench "$SCENARIO" | head -1)

    echo "Running vdbench with config: $config"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"

    # Create output directory
    mkdir -p "$OUTPUT"

    # Replace anchor paths in config with MOUNT if needed
    # vdbench configs often have wd= anchor=/path/to/mount
    local vdbench_cmd=("$VDBENCH_BIN" "-f" "$config" "-o" "$OUTPUT")

    # Change to vdbench directory for execution
    cd "$VDBENCH_DIR"

    echo "Executing: ./vdbench -f $config -o $OUTPUT"

    # Capture console output to raw file while running vdbench
    # Use PIPESTATUS[0] to get vdbench exit code after tee
    "./vdbench" -f "$config" -o "$OUTPUT" 2>&1 | tee "$OUTPUT/vdbench.raw"
    local vdbench_exit=${PIPESTATUS[0]}

    # Generate reports
    echo "Generating reports..."
    python3 /scripts/generate_report.py --tool vdbench --output-dir "$OUTPUT" --scenario "$SCENARIO" --mount "$MOUNT"

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
    echo ""

    # Create base output directory
    mkdir -p "$OUTPUT"

    local overall_exit=0
    local run_num=0

    # Change to mount directory for test execution
    cd "$MOUNT"

    # Run each scenario
    # Use array instead of while read to avoid set -e issues
    mapfile -t scenario_array <<< "$scenario_paths"
    local total=${#scenario_array[@]}
    local run_num=0

    for script in "${scenario_array[@]}"; do
        [[ -z "$script" ]] && continue

        run_num=$((run_num + 1))
        local scenario_name
        scenario_name=$(basename "$script" .sh)
        local scenario_output="$OUTPUT/$scenario_name"

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

        echo "" || true
    done

    # Generate combined report for all mdtest scenarios
    echo "Generating combined mdtest report..."
    python3 /scripts/generate_report.py --tool mdtest --output-dir "$OUTPUT" --scenario "mdtest" --mount "$MOUNT" --combined

    echo ""
    echo "All mdtest scenarios completed."
    return $overall_exit
}

pjdtest_run() {
    echo "Running pjdtest"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"

    # Create output directory
    mkdir -p "$OUTPUT"

    # Change to mount directory for test execution
    cd "$MOUNT"

    # Generate timestamp for output file
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    local output_file="${OUTPUT}/pjdtest_${timestamp}"

    echo "Executing: prove -rv /pjdtest/dingofs_baseline"
    echo "Output file: ${output_file}"

    # Run pjdtest using prove
    prove -rv /pjdtest/dingofs_baseline > "${output_file}" 2>&1
    local pjdtest_exit=$?

    if [[ $pjdtest_exit -ne 0 ]]; then
        echo "Warning: pjdtest exited with code $pjdtest_exit"
    else
        echo "pjdtest completed successfully."
    fi

    echo ""
    echo "Results saved to: ${output_file}"
    return $pjdtest_exit
}

ltp_run() {
    echo "Running LTP test suite"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"
    echo "  Scenario: $SCENARIO"

    # Create output directory
    mkdir -p "$OUTPUT"

    # Change to mount directory for test execution
    cd "$MOUNT"

    # Generate timestamp for output file
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    local output_file="${OUTPUT}/ltp_${timestamp}"

    # Default to filesystem tests (-f fs) if no scenario specified
    local scenario="${SCENARIO:-fs}"

    echo "Executing: timeout 3600 /opt/ltp/runltp -f $scenario -d ."
    echo "Output file: ${output_file}.log"

    # Run LTP with timeout protection (1 hour max)
    # -f: test suite (fs for filesystem tests)
    # -d .: run in current directory (mount point)
    # -p: output directory for results
    # -l: log file
    timeout 3600 /opt/ltp/runltp -f "$scenario" -d . -p "$OUTPUT" -l "${output_file}.log" 2>&1 | tee "${output_file}.raw"
    local ltp_exit=${PIPESTATUS[0]}

    if [[ $ltp_exit -eq 124 ]]; then
        echo "Warning: LTP test timed out after 3600 seconds"
    elif [[ $ltp_exit -ne 0 ]]; then
        echo "Warning: LTP exited with code $ltp_exit"
    else
        echo "LTP tests completed successfully."
    fi

    echo ""
    echo "Results saved to: ${output_file}.log"
    return $ltp_exit
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
    echo "DingoFS Storage Benchmark Tools"
    echo "=============================================="
    echo "Tool:     $TOOL"
    echo "Scenario: $SCENARIO"
    echo "Mount:    $MOUNT"
    echo "Output:   $OUTPUT"
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
