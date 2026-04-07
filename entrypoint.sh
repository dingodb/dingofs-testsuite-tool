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
DingoFS Storage Benchmark Tools
===============================

Usage:
  docker run myimage -t <tool> -s <scenario> -m <mount> -o <output>

Tools:
  fio       - Flexible I/O tester (storage performance)
  vdbench   - Oracle storage benchmark
  mdtest    - MPI filesystem metadata test

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

Examples:
  # Run ALL rand_read scenarios (24 tests)
  docker run --rm -v /tmp/test:/data myimage -t fio -s rand_read -m /data -o /data

  # Run ALL seq_write scenarios (24 tests)
  docker run --rm -v /tmp/test:/data myimage -t fio -s seq_write -m /data -o /data

  # Run a SINGLE specific scenario
  docker run --rm -v /tmp/test:/data myimage -t fio -s rand_read_0d_128k_1j -m /data -o /data

  # Run vdbench test
  docker run --rm -v /tmp/test:/data myimage -t vdbench -s seq_rd -m /data -o /data

  # Long-running mode (container stays alive)
  docker run --detach -v /tmp/test:/data myimage -t fio -s rand_read -m /data -o /data --mode long-running
  docker exec <container_id> entrypoint.sh -t fio -s seq_write -m /data -o /data

Output:
  Results are saved to the output directory with:
    - fio.raw / fio.json    (raw and JSON output)
    - report.html           (HTML report)
    - summary.txt           (text summary)

For more details on fio scenarios, see: ls /scenarios/fio/

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
            # mdtest has no config file, always valid
            [[ "$scenario" =~ ^(mdtest|meta)$ ]]
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
    esac

    # Print paths (one per line)
    for path in "${paths[@]}"; do
        echo "$path"
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
    echo "Running mdtest"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"

    # Create output directory
    mkdir -p "$OUTPUT"

    # mdtest has fixed internal scenarios, no config file needed
    # Common mdtest flags: -d (directory), -i (iterations), -b (breadth), -e (depth)
    local mdtest_cmd=("$MDTEST_BIN" "-d" "$MOUNT")

    echo "Executing: ${mdtest_cmd[*]}"

    # Capture to raw file using tee, keeping mdtest.txt for backward compatibility
    # Use PIPESTATUS[0] to get mdtest exit code after tee
    "${mdtest_cmd[@]}" 2>&1 | tee "$OUTPUT/mdtest.raw"
    local mdtest_exit=${PIPESTATUS[0]}

    # Generate reports
    echo "Generating reports..."
    python3 /scripts/generate_report.py --tool mdtest --output-dir "$OUTPUT" --scenario "mdtest" --mount "$MOUNT"

    return $mdtest_exit
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
