#!/usr/bin/env bash
# =============================================================================
# MLPerf Storage Benchmark - Single-Model Runner (DTT-adapted)
# =============================================================================
# Handles the complete lifecycle for one workload:
#   1. Determine dataset size (num_files_train)
#   2. Generate dataset (datagen) — skipped if data already present
#   3. Execute benchmark (run)
#   4. Generate report (reportgen)
#
# Special handling for the "checkpointing" workload (no datagen step,
# different subcommand structure).
#
# Called by entrypoint.sh's mlperf_run():
#   run_model.sh MODEL CLIENT_MEMORY_GB NUM_PROCESSES RUN_TS
#
# All other parameters come from environment variables inherited from
# entrypoint.sh (ACCELERATOR_TYPE, NUM_ACCELERATORS, SCALE, LOOPS,
# SUBMISSION_MODE, SKIP_DATAGEN, HOSTS, NUM_CLIENT_HOSTS, CHECKPOINTING_MODEL,
# EXTRA_PARAMS).
#
# OUTPUT_BASE can be set by the caller (e.g. /output/mlperf_<timestamp>)
# to redirect results and logs to the dtt output volume. Defaults to /data.
# =============================================================================

set -eo pipefail

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
MODEL="${1:?'MODEL argument required'}"
CLIENT_MEMORY_GB="${2:?'CLIENT_MEMORY_GB argument required'}"
NUM_PROCESSES="${3:?'NUM_PROCESSES argument required'}"
RUN_TS="${4:?'RUN_TS argument required'}"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
OUTPUT_BASE="${OUTPUT_BASE:-/data}"
DATA_DIR="/data"
MODEL_DATA_DIR="${DATA_DIR}/datasets/${MODEL}"
RESULTS_DIR="${OUTPUT_BASE}/results/${MODEL}/run_${RUN_TS}"
LOGS_DIR="${OUTPUT_BASE}/logs"
mkdir -p "${MODEL_DATA_DIR}" "${RESULTS_DIR}" "${LOGS_DIR}"

# ---------------------------------------------------------------------------
# Logging helpers (plain text, no ANSI — colors handled by entrypoint.sh)
# ---------------------------------------------------------------------------
info()    { echo "[INFO]  $*"; }
success() { echo "[OK]    $*"; }
warn()    { echo "[WARN]  $*"; }
error()   { echo "[ERROR] $*" >&2; }

# ---------------------------------------------------------------------------
# Scale preset tables
# Small/medium presets for quick functional verification only.
# These do NOT satisfy the MLPerf 5x-memory requirement.
# ---------------------------------------------------------------------------
declare -A SCALE_SMALL=(
    [unet3d]=500
    [resnet50]=500
    [cosmoflow]=2000
)
declare -A SCALE_MEDIUM=(
    [unet3d]=5000
    [resnet50]=5000
    [cosmoflow]=50000
)

# ---------------------------------------------------------------------------
# Build extra param values from EXTRA_PARAMS env var
# Input:  "reader.read_threads=8,reader.prefetch_size=4"
# Output: "reader.read_threads=8 reader.prefetch_size=4"
#
# The v2.0 CLI uses --params key1=val1 key2=val2 (all in one flag, space-sep).
# Callers are responsible for combining with the fixed dataset.num_files_train
# param and wrapping in a single --params flag.
# ---------------------------------------------------------------------------
build_extra_params_values() {
    local values=""
    if [[ -n "${EXTRA_PARAMS}" ]]; then
        IFS=',' read -ra PARAMS <<< "${EXTRA_PARAMS}"
        for PARAM in "${PARAMS[@]}"; do
            PARAM="$(echo "${PARAM}" | xargs)"
            [[ -n "${PARAM}" ]] && values="${values} ${PARAM}"
        done
    fi
    echo "${values}"
}

# ---------------------------------------------------------------------------
# Handle checkpointing workload separately
# (no datagen step, different subcommand structure)
# ---------------------------------------------------------------------------
run_checkpointing() {
    info "Workload: checkpointing (model: ${CHECKPOINTING_MODEL})"
    info "Data dir:    ${MODEL_DATA_DIR}"
    info "Results dir: ${RESULTS_DIR}"
    echo ""

    local extra_values
    extra_values="$(build_extra_params_values)"

    info "Running checkpointing benchmark..."
    # shellcheck disable=SC2086
    mlpstorage checkpointing run \
        --model "${CHECKPOINTING_MODEL}" \
        --num-processes "${NUM_PROCESSES}" \
        --client-host-memory-in-gb "${CLIENT_MEMORY_GB}" \
        --checkpoint-folder "${MODEL_DATA_DIR}" \
        --results-dir "${RESULTS_DIR}" \
        --loops "${LOOPS}" \
        --allow-run-as-root \
        ${extra_values:+--params ${extra_values}}

    info "Generating checkpointing report..."
    mlpstorage reports reportgen \
        --results-dir "${RESULTS_DIR}" || \
        warn "reportgen failed (non-fatal, results still saved to ${RESULTS_DIR})"

    success "Checkpointing benchmark complete."
    success "Results: ${RESULTS_DIR}"
}

# ---------------------------------------------------------------------------
# Step 1: Determine num_files_train for training workloads
# ---------------------------------------------------------------------------
determine_num_files() {
    local model="${1}"
    local num_files=""

    case "${SCALE}" in
        small)
            num_files="${SCALE_SMALL[${model}]}"
            if [[ -z "${num_files}" ]]; then
                warn "No small preset for model '${model}', using 1000"
                num_files=1000
            fi
            info "Scale: small (${num_files} files) — functional verification only"
            ;;
        medium)
            num_files="${SCALE_MEDIUM[${model}]}"
            if [[ -z "${num_files}" ]]; then
                warn "No medium preset for model '${model}', using 5000"
                num_files=5000
            fi
            info "Scale: medium (${num_files} files) — functional verification only"
            ;;
        large|auto)
            info "Scale: ${SCALE} — calling mlpstorage training datasize..."
            local datasize_output
            datasize_output=$(mlpstorage training datasize \
                --model "${model}" \
                --client-host-memory-in-gb "${CLIENT_MEMORY_GB}" \
                --num-client-hosts "${NUM_CLIENT_HOSTS}" \
                --max-accelerators "${NUM_ACCELERATORS}" \
                --accelerator-type "${ACCELERATOR_TYPE}" \
                --allow-run-as-root 2>&1) || true

            echo "${datasize_output}"

            # Parse num_files_train from datasize output.
            # The command typically outputs a line containing "num_files_train: <N>"
            num_files=$(echo "${datasize_output}" | \
                grep -oP 'num_files_train[=:\s]+\K[0-9]+' | head -1 || true)

            if [[ -z "${num_files}" ]]; then
                warn "Could not parse num_files_train from datasize output."
                warn "Falling back to small preset for functional verification."
                num_files="${SCALE_SMALL[${model}]:-1000}"
                warn "Using num_files_train=${num_files} (override with SCALE=<integer>)"
            else
                info "datasize → num_files_train=${num_files}"
            fi
            ;;
        ''|*[!0-9]*)
            # Not a pure integer and not a known preset — error
            error "Invalid SCALE value: '${SCALE}'"
            error "Valid values: small, medium, large, auto, or a positive integer"
            return 1
            ;;
        *)
            # Pure integer — use directly
            num_files="${SCALE}"
            info "Scale: custom (${num_files} files)"
            ;;
    esac

    echo "${num_files}"
}

# ---------------------------------------------------------------------------
# Step 2: Decide whether to run datagen
# ---------------------------------------------------------------------------
should_run_datagen() {
    local model="${1}"
    local expected_files="${2}"
    local data_dir="${3}"

    case "${SKIP_DATAGEN}" in
        true)
            info "SKIP_DATAGEN=true — skipping dataset generation."
            return 1  # 1 = skip
            ;;
        false)
            info "SKIP_DATAGEN=false — regenerating dataset."
            return 0  # 0 = run datagen
            ;;
        auto|*)
            # Count existing files in the data directory
            if [[ ! -d "${data_dir}" ]]; then
                return 0  # directory doesn't exist, run datagen
            fi

            local existing_count
            existing_count=$(find "${data_dir}" -type f 2>/dev/null | wc -l)

            if [[ "${existing_count}" -ge "${expected_files}" ]]; then
                info "SKIP_DATAGEN=auto — found ${existing_count} files >= expected ${expected_files}."
                info "Skipping datagen. (Set SKIP_DATAGEN=false to force regeneration.)"
                return 1  # skip
            else
                info "SKIP_DATAGEN=auto — found ${existing_count} files < expected ${expected_files}."
                info "Running datagen to generate ${expected_files} files."
                return 0  # run datagen
            fi
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Step 3: Run datagen
# ---------------------------------------------------------------------------
run_datagen() {
    local model="${1}"
    local num_files="${2}"
    local data_dir="${3}"
    local results_dir="${4}"
    local allow_invalid="${5:-false}"

    local extra_values
    extra_values="$(build_extra_params_values)"
    local invalid_flag=""
    [[ "${allow_invalid}" == "true" ]] && invalid_flag="--allow-invalid-params"

    info "Generating dataset: model=${model}, num_files=${num_files}"
    info "Output: ${data_dir}"
    echo ""

    # shellcheck disable=SC2086
    mlpstorage training datagen \
        --hosts "${HOSTS}" \
        --model "${model}" \
        --num-processes "${NUM_PROCESSES}" \
        --data-dir "${data_dir}" \
        --results-dir "${results_dir}" \
        --params "dataset.num_files_train=${num_files}" ${extra_values} \
        --allow-run-as-root \
        ${invalid_flag}

    success "Datagen complete."
}

# ---------------------------------------------------------------------------
# Step 4: Run benchmark
# ---------------------------------------------------------------------------
run_benchmark() {
    local model="${1}"
    local num_files="${2}"
    local data_dir="${3}"
    local results_dir="${4}"
    local allow_invalid="${5:-false}"

    local extra_values
    extra_values="$(build_extra_params_values)"
    local invalid_flag=""
    [[ "${allow_invalid}" == "true" ]] && invalid_flag="--allow-invalid-params"
    local submission_flag="--${SUBMISSION_MODE}"

    info "Running benchmark: model=${model}, accelerators=${NUM_ACCELERATORS}x ${ACCELERATOR_TYPE}"
    info "Loops: ${LOOPS}, Mode: ${SUBMISSION_MODE}"
    echo ""

    # shellcheck disable=SC2086
    # Note: 'training run' does not take --num-processes; the number of
    # worker processes is derived from --num-accelerators * --num-client-hosts.
    mlpstorage training run \
        --hosts "${HOSTS}" \
        --model "${model}" \
        --num-accelerators "${NUM_ACCELERATORS}" \
        --accelerator-type "${ACCELERATOR_TYPE}" \
        --num-client-hosts "${NUM_CLIENT_HOSTS}" \
        --client-host-memory-in-gb "${CLIENT_MEMORY_GB}" \
        --data-dir "${data_dir}" \
        --results-dir "${results_dir}" \
        --params "dataset.num_files_train=${num_files}" ${extra_values} \
        --loops "${LOOPS}" \
        ${submission_flag} \
        --allow-run-as-root \
        ${invalid_flag}

    success "Benchmark run complete."
}

# ---------------------------------------------------------------------------
# Step 5: Generate report
# ---------------------------------------------------------------------------
run_reportgen() {
    local results_dir="${1}"

    info "Generating report..."
    mlpstorage reports reportgen \
        --results-dir "${results_dir}" || \
        warn "reportgen failed (non-fatal, results still saved to ${results_dir})"

    success "Report generated: ${results_dir}"
}

# ---------------------------------------------------------------------------
# Main: dispatch to training or checkpointing workflow
# ---------------------------------------------------------------------------
main() {
    if [[ "${MODEL}" == "checkpointing" ]]; then
        run_checkpointing
        return $?
    fi

    # --- Training workflow ---
    info "Workload: ${MODEL}"
    info "Data dir:    ${MODEL_DATA_DIR}"
    info "Results dir: ${RESULTS_DIR}"
    echo ""

    # Determine whether this is a non-compliant small/medium run
    ALLOW_INVALID="false"
    if [[ "${SCALE}" == "small" || "${SCALE}" == "medium" ]]; then
        ALLOW_INVALID="true"
    fi

    # Step 1: Determine num_files_train
    # We capture only the last line (the number) to avoid capturing info logs
    NUM_FILES_OUTPUT=$(determine_num_files "${MODEL}")
    NUM_FILES=$(echo "${NUM_FILES_OUTPUT}" | tail -1)

    # Validate that we got a number
    if ! [[ "${NUM_FILES}" =~ ^[0-9]+$ ]]; then
        error "Could not determine num_files_train for model '${MODEL}'"
        error "Got: '${NUM_FILES}'"
        return 1
    fi

    # Step 2: Decide whether to run datagen
    if should_run_datagen "${MODEL}" "${NUM_FILES}" "${MODEL_DATA_DIR}"; then
        # Step 3: Run datagen
        run_datagen \
            "${MODEL}" \
            "${NUM_FILES}" \
            "${MODEL_DATA_DIR}" \
            "${RESULTS_DIR}" \
            "${ALLOW_INVALID}"
    fi

    # Step 4: Run benchmark
    run_benchmark \
        "${MODEL}" \
        "${NUM_FILES}" \
        "${MODEL_DATA_DIR}" \
        "${RESULTS_DIR}" \
        "${ALLOW_INVALID}"

    # Step 5: Generate report
    run_reportgen "${RESULTS_DIR}"

    echo ""
    success "Model '${MODEL}' complete."
    success "Results saved to: ${RESULTS_DIR}"
}

main "$@"
