#!/bin/bash
#
# DingoFS Storage Benchmark Tools - Unified Entrypoint
# Parses CLI arguments, handles one-shot and long-running modes,
# dispatches to correct storage testing tool (fio/vdbench/mdtest)
#
# Usage:
#   docker run myimage -t fio -s seq_read -m /mnt/test
#   docker run myimage -t vdbench -s rand_read -m /mnt/test -o /tmp/results
#   docker run --detach myimage -t fio -s randrw --mode long-running
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
Usage: entrypoint.sh [OPTIONS]

DingoFS Storage Benchmark Tools - Unified entrypoint for storage performance testing.

Options:
  -t, --tool TOOL       Storage testing tool (fio, vdbench, mdtest)
  -s, --scenario NAME   Test scenario name
                        fio: seq_read, seq_write, rand_read, rand_write, randrw
                        vdbench: seq_rd, seq_wr, rand_rd, rand_wr
                        mdtest: (uses fixed internal scenarios)
  -m, --mount PATH      Filesystem mount point (default: /data)
  -o, --output PATH     Output directory (default: /data/results)
  --mode MODE           Mode: one-shot or long-running (default: one-shot)
                        one-shot: Execute test and exit
                        long-running: Stay alive for additional tests via docker exec
  -h, --help            Show this help message

Custom Config Override:
  Mount your own config files at /custom/ to override built-in scenarios:
    /custom/{scenario}.fio   (for fio)
    /custom/{scenario}.par    (for vdbench)
  Custom configs take precedence over built-in scenarios.

Examples:
  # Run fio sequential read test
  docker run myimage -t fio -s seq_read -m /mnt/test

  # Run vdbench random write test with custom output
  docker run myimage -t vdbench -s rand_wr -m /mnt/test -o /tmp/results

  # Run in long-running mode for multiple tests
  docker run --detach myimage -t fio -s randrw -m /mnt/test --mode long-running
  docker exec <container> entrypoint.sh -t fio -s seq_read -m /mnt/test

EOF
}

# ==============================================================================
# Validation Functions
# ==============================================================================

validate_params() {
    local error=0

    # Validate TOOL (PARM-06)
    if [[ -z "$TOOL" ]]; then
        echo "Error: Tool is required. Use -t or --tool to specify (fio, vdbench, mdtest)."
        error=1
    elif [[ ! "$TOOL" =~ ^(fio|vdbench|mdtest)$ ]]; then
        echo "Error: Invalid tool '$TOOL'. Valid options: fio, vdbench, mdtest"
        error=1
    fi

    # Validate SCENARIO (PARM-06)
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
            [[ -f "/custom/${scenario}.fio" ]] || [[ -f "/custom/${scenario}.conf" ]] || [[ -f "${SCENARIOS_DIR}/fio/${scenario}.fio" ]]
            ;;
        vdbench)
            [[ -f "/custom/${scenario}.par" ]] || [[ -f "${SCENARIOS_DIR}/vdbench/${scenario}.par" ]]
            ;;
        mdtest)
            # mdtest has no config file, always valid
            [[ "$scenario" =~ ^(mdtest|meta)$ ]]
            ;;
        *)
            return 1
            ;;
    esac
}

get_scenario_path() {
    local tool="$1"
    local scenario="$2"

    case "$tool" in
        fio)
            # Check custom override first
            if [[ -f "/custom/${scenario}.fio" ]]; then
                echo "/custom/${scenario}.fio"
            elif [[ -f "/custom/${scenario}.conf" ]]; then
                echo "/custom/${scenario}.conf"
            else
                echo "${SCENARIOS_DIR}/fio/${scenario}.fio"
            fi
            ;;
        vdbench)
            if [[ -f "/custom/${scenario}.par" ]]; then
                echo "/custom/${scenario}.par"
            else
                echo "${SCENARIOS_DIR}/vdbench/${scenario}.par"
            fi
            ;;
        *)
            echo ""
            ;;
    esac
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
        *)
            echo "Error: Unknown tool '$TOOL'"
            exit 1
            ;;
    esac
}

fio_run() {
    local config
    config=$(get_scenario_path fio "$SCENARIO")

    echo "Running fio with config: $config"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"

    # Create output directory
    mkdir -p "$OUTPUT"

    # Run fio with JSON output format
    # Replace directory path in config with MOUNT if needed
    local fio_cmd=("$FIO_BIN" "$config" "--output=$OUTPUT/fio.json" "--output-format=json")

    # If config has a directory parameter, we need to override it
    # fio allows overriding via command line: --directory=
    if [[ -d "$MOUNT" ]]; then
        fio_cmd+=("--directory=$MOUNT")
    fi

    echo "Executing: ${fio_cmd[*]}"
    "${fio_cmd[@]}"

    return $?
}

vdbench_run() {
    local config
    config=$(get_scenario_path vdbench "$SCENARIO")

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
    "./vdbench" -f "$config" -o "$OUTPUT"

    return $?
}

mdtest_run() {
    echo "Running mdtest"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"

    # Create output directory
    mkdir -p "$OUTPUT"

    # mdtest has fixed internal scenarios, no config file needed
    # Common mdtest flags: -d (directory), -i (iterations), -b (breadth), -e (depth)
    local mdtest_cmd=("$MDTEST_BIN" "-d" "$MOUNT")

    echo "Executing: ${mdtest_cmd[*]}"
    "${mdtest_cmd[@]}" > "$OUTPUT/mdtest.txt" 2>&1

    return $?
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
