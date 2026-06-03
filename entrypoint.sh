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
RUN_TIMESTAMP=""     # Timestamp for this run (format: YYYYmmdd_HHMMSS)
MODE="one-shot"      # Mode: one-shot or long-running
NP=16                # Number of MPI processes for mdtest (default: 16)
BS_SIZE="${BS_SIZE:-normal}"  # Block size type: normal (128K/1M/4M) or small (128B-8K)

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

# Integration test environment
INT_ENV="${INT_ENV:-env_126_smoke}"

# Smoke exclude list (comma-separated tool names)
SMOKE_EXCLUDE="${SMOKE_EXCLUDE:-}"

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
  -t, --tool      测试工具: fio, vdbench, mdtest, pjdtest, ltp, int, mlperf, smoke
  -s, --scenario  测试场景
  -m, --mount     被测存储的挂载点 (例如: /mnt/test)
  -o, --output    测试结果输出目录 (例如: /output)
  -n, --np        mdtest MPI 进程数 (默认: 16)
  --bs_size       fio块大小类型: normal (128K/1M/4K), small (128B/256B/512B/1K/2K/4K/8K)
                   默认: normal
  --mode          运行模式: one-shot (默认) 或 long-running

注意: -o 指定的是容器内路径，需要通过 -v 将容器内目录映射到本机路径

Tools:
  fio       - Flexible I/O tester (存储性能测试)
  vdbench   - Oracle storage testsuite
  mdtest    - MPI filesystem metadata test
  pjdtest   - POSIX filesystem test suite
  ltp       - Linux Test Project (内核测试套件)
  int       - DingoFS integration test (自动化框架)
  mlperf    - MLPerf Storage 存储基准测试
  smoke     - 冒烟测试 (串行运行 pjdtest + mdtest + ltp)

运行模式:
  one-shot      - 容器启动 → 运行测试 → 测试完成后容器退出 (默认)
  long-running   - 容器启动 → 运行测试 → 容器保持运行，可用 docker exec 执行更多测试

通知选项:
  --wechat    启用企业微信通知 (需要配置 webhook_url)
  --email      启用邮件通知 (需要配置 email)

配置通知:
  dtt config set webhook_url <url>  设置企业微信webhook地址
  dtt config set email <地址>      设置邮件通知地址

FIO Scenarios (4 types, each runs multiple sub-scenarios):
  rand_read   - Random read
  rand_write  - Random write
  seq_read    - Sequential read
  seq_write   - Sequential write
  all         - 运行以上所有4个场景

FIO Block Sizes (--bs_size):
  normal (默认) - 128K, 1M, 4M
  small          - 128B, 256B, 512B, 1K, 2K, 4K, 8K

FIO Parameters:
  direct:    0 (buffered), 1 (direct I/O)
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
  # 运行所有 rand_read 场景 (normal块大小: 24 tests)
  docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t fio -s rand_read -m /data -o /data

  # 运行所有 fio 场景 (小块模式: 128B-8K, 224 tests)
  docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t fio -s all --bs_size small -m /data -o /data

  # 运行所有 seq_write 场景 (normal块大小)
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

  # mlperf 测试 (运行所有MLPerf存储基准测试场景)
  docker run --rm --privileged --shm-size=8g -v /tmp/test:/data -v /tmp/results:/output dingofs-testsuite-tools -t mlperf -s all

  # mlperf 单个场景测试
  docker run --rm --privileged --shm-size=8g -v /tmp/test:/data -v /tmp/results:/output dingofs-testsuite-tools -t mlperf -s resnet50

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
    - mlperf_YYYYMMDD_HHMMSS/ (MLPerf 测试结果和报告)

EOF
}

# ==============================================================================
# Per-Tool Help Functions
# ==============================================================================

show_smoke_help() {
    cat << 'EOF'
冒烟测试 (Smoke Test)
=====================

用法: dtt -t smoke [-m <挂载点>] [-o <输出目录>]

自动串行运行以下三个测试:
  1. pjdtest -s all    -- POSIX 文件系统兼容性测试
  2. mdtest  -s all -n 8 -- 元数据性能测试 (8 MPI 进程)
  3. ltp     -s smoke   -- LTP 冒烟测试 (smoketest 套件)

特性:
  - 单个工具的失败不会中止后续工具的运行 (fail-continue)
  - 所有结果统一输出到 smoke_<timestamp>/ 目录
  - 每个工具的结果保存在各自的子目录中

示例:
  # 运行冒烟测试 (使用默认挂载点和输出目录)
  dtt -t smoke

  # 指定挂载点和输出目录
  dtt -t smoke -m /mnt/test -o /tmp/results

注意:
  - 建议使用 --privileged 运行以支持 LTP 内核测试
  - 冒烟测试会按顺序运行所有三个工具，可能需要较长时间
EOF
}

show_fio_help() {
    cat << EOF
FIO 存储性能测试
=================

用法: dtt -t fio -s <场景> [-m <挂载点>] [-o <输出目录>] [--bs_size <类型>]

场景类型:
  seq_read    - 顺序读
  seq_write   - 顺序写
  rand_read   - 随机读
  rand_write  - 随机写
  all         - 运行所有4种场景类型

块大小类型 (--bs_size):
  normal (默认) - 128K, 1M, 4M (每种类型24个测试)
  small          - 128B, 256B, 512B, 1K, 2K, 4K, 8K (每种类型56个测试)

每个场景运行以下变体:
  direct:    0 (buffered), 1 (direct I/O)
  numjobs:   1, 8, 16, 32
  iodepth:   1 (固定)
  size:      每个job 8G

示例:
  # 运行所有顺序读场景 (normal块大小: 24个测试)
  dtt -t fio -s seq_read

  # 运行所有场景 (normal块大小: 96个测试)
  dtt -t fio -s all

  # 运行所有场景 (小块模式: 224个测试)
  dtt -t fio -s all --bs_size small

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
  smoke     - 冒烟测试 (smoketest)
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
  dtt -t ltp -s smoke
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

show_mlperf_help() {
    cat << EOF
MLPerf Storage 基准测试
=======================

用法: entrypoint.sh -t mlperf [-s <场景>]

MLPerf Storage 是 MLPerf 组织定义的存储性能基准测试套件。

场景:
  resnet50       - ResNet-50 图像分类模型
  unet3d         - 3D U-Net 医学图像分割模型
  cosmoflow      - CosmoFlow 宇宙学模拟模型
  checkpointing  - 检查点读写测试
  all            - 运行所有场景 (默认)

环境变量 (通过 docker run -e 设置):
  MODELS              测试模型列表，逗号分隔 (默认: all)
  SCALE               数据集规模: small/medium/large 或整数 (默认: small)
  NUM_ACCELERATORS    并发GPU/加速器数量 (默认: 1)
  ACCELERATOR_TYPE    加速器类型: h100/a100 (默认: h100)
  LOOPS               基准测试循环次数 (默认: 1)
  SUBMISSION_MODE     提交模式: closed/open (默认: closed)

示例:
  docker run --rm --privileged --shm-size=8g \\
    -v /mnt/test:/data -v /tmp/results:/output \\
    -e MODELS=resnet50 -e SCALE=small -e NUM_ACCELERATORS=1 \\
    dingofs-testsuite-tools -t mlperf -s all

注意:
  - 需要 --shm-size=8g 支持 PyTorch DataLoader
  - 测试数据写入 /data/datasets/ (存储性能测试目标)
  - 测试结果保存到 /output/mlperf_<timestamp>/
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
    elif [[ ! "$TOOL" =~ ^(fio|vdbench|mdtest|pjdtest|ltp|int|mlperf|smoke)$ ]]; then
        echo "Error: Invalid tool '$TOOL'. Valid options: fio, vdbench, mdtest, pjdtest, ltp, int, mlperf, smoke"
        error=1
    fi

    # Validate SCENARIO (PARM-06) - mdtest and mlperf don't require a scenario
    if [[ "$TOOL" != "mdtest" && "$TOOL" != "mlperf" && "$TOOL" != "smoke" ]]; then
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
        smoke)
            return 0
            ;;
        fio)
            # When BS_SIZE=small, files are in /scenarios/fio/bs_small
            # When BS_SIZE=normal, files are in /scenarios/fio/bs_normal
            local fio_scenarios_dir="/scenarios/fio/bs_normal"
            if [[ "$BS_SIZE" == "small" ]]; then
                fio_scenarios_dir="/scenarios/fio/bs_small"
            fi

            # Accept "all" to run all scenarios
            if [[ "$scenario" == "all" ]]; then
                return 0
            fi
            # Check exact match first
            if [[ -f "/custom/${scenario}.fio" ]] || [[ -f "/custom/${scenario}.conf" ]] || [[ -f "${fio_scenarios_dir}/${scenario}.fio" ]]; then
                return 0
            fi
            # Check for prefix matches (e.g., seq_read matches seq_read_*.fio)
            if [[ -n "$(ls "${fio_scenarios_dir}/${scenario}"_*.fio 2>/dev/null | head -1)" ]]; then
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
            [[ "$scenario" == "all" ]] || [[ "$scenario" =~ ^(fs|fsx|io|dir|lock|syscalls|smoke)$ ]]
            ;;
        int|integration)
            # int scenarios: quota, client, cache_node, chaos, all
            [[ "$scenario" == "all" ]] || [[ "$scenario" =~ ^(quota|client|cache_node|chaos)$ ]]
            ;;
        mlperf)
            # mlperf scenarios: resnet50, unet3d, cosmoflow, checkpointing, all
            [[ "$scenario" == "all" ]] || [[ "$scenario" =~ ^(resnet50|unet3d|cosmoflow|checkpointing)$ ]]
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
            # SCENARIOS_DIR is already set to /scenarios/fio/bs_normal or /scenarios/fio/bs_small
            # by fio_run() before calling get_scenario_paths(). No additional subdir needed.

            # If "all", run all 4 scenario types
            if [[ "$scenario" == "all" ]]; then
                # Run all 4 scenario types: seq_read, seq_write, rand_read, rand_write
                local all_types="seq_read seq_write rand_read rand_write"
                for type in $all_types; do
                    while IFS= read -r file; do
                        paths+=("$file")
                    done < <(ls "${SCENARIOS_DIR}/${type}"_*.fio 2>/dev/null | sort)
                done
            # Check custom override first (exact match only)
            elif [[ -f "/custom/${scenario}.fio" ]]; then
                paths+=("/custom/${scenario}.fio")
            elif [[ -f "/custom/${scenario}.conf" ]]; then
                paths+=("/custom/${scenario}.conf")
            elif [[ -f "${SCENARIOS_DIR}/${scenario}.fio" ]]; then
                paths+=("${SCENARIOS_DIR}/${scenario}.fio")
            else
                # Check for prefix matches
                while IFS= read -r file; do
                    paths+=("$file")
                done < <(ls "${SCENARIOS_DIR}/${scenario}"_*.fio 2>/dev/null | sort)
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
                        mlperf) show_mlperf_help; exit 0 ;;
                        smoke) show_smoke_help; exit 0 ;;
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
        mlperf)
            # mlperf success based on exit code
            if [[ $exit_code -eq 0 ]]; then
                status="SUCCESS"
                details="mlperf benchmark completed successfully"
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
        smoke)
            smoke_run
            ;;
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
        mlperf)
            mlperf_run
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

    # Set fio scenarios directory based on BS_SIZE
    # When BS_SIZE=small, files are in /scenarios/fio/bs_small
    # When BS_SIZE=normal, files are in /scenarios/fio/bs_normal
    local fio_base_dir="/scenarios/fio/bs_normal"
    if [[ "$BS_SIZE" == "small" ]]; then
        fio_base_dir="/scenarios/fio/bs_small"
    fi

    # Override SCENARIOS_DIR temporarily for fio
    local orig_scenarios_dir="$SCENARIOS_DIR"
    SCENARIOS_DIR="${fio_base_dir}"
    scenario_paths=$(get_scenario_paths fio "$SCENARIO")
    SCENARIOS_DIR="$orig_scenarios_dir"

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

    # Create base output directory and tool subdirectory with timestamp
    mkdir -p "$OUTPUT"
    mkdir -p "$OUTPUT/fio_${RUN_TIMESTAMP}"

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
            local scenario_output="$OUTPUT/fio_${RUN_TIMESTAMP}/$scenario_type/$scenario_name"
        else
            # Each variant gets its own subdirectory
            local scenario_output="$OUTPUT/fio_${RUN_TIMESTAMP}/$SCENARIO/$scenario_name"
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
        python3 /scripts/generate_report.py --tool fio --output-dir "$scenario_output" --scenario "$scenario_name" --mount "$MOUNT" --bs-size "$BS_SIZE"

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

        if [[ "$EMAIL_ENABLED" == "yes" ]]; then
            local fio_status="FAIL"
            if [[ $fio_exit -eq 0 ]]; then
                fio_status="SUCCESS"
            fi
            send_email_notification "fio" "$scenario_name" "$fio_status" "$scenario_duration_str"
        fi

        echo ""
    done <<< "$scenario_paths"

    # Generate combined report if multiple scenarios
    if [[ $path_count -gt 1 ]]; then
        echo "Generating combined report..."
        # For "all" scenario, aggregate from all scenario type subdirectories
        # For specific scenario, use that scenario's subdirectory
        if [[ "$SCENARIO" == "all" ]]; then
            python3 /scripts/generate_report.py --tool fio --output-dir "$OUTPUT/fio_${RUN_TIMESTAMP}" --scenario "$SCENARIO" --mount "$MOUNT" --combined --bs-size "$BS_SIZE"
        else
            python3 /scripts/generate_report.py --tool fio --output-dir "$OUTPUT/fio_${RUN_TIMESTAMP}/$SCENARIO" --scenario "$SCENARIO" --mount "$MOUNT" --combined --bs-size "$BS_SIZE"
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
    mkdir -p "$OUTPUT/vdbench_${RUN_TIMESTAMP}/$SCENARIO"

    # Replace anchor paths in config with MOUNT if needed
    # vdbench configs often have wd= anchor=/path/to/mount
    local vdbench_output="$OUTPUT/vdbench_${RUN_TIMESTAMP}/$SCENARIO"
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

    # Send Email notification if enabled
    if [[ "$EMAIL_ENABLED" == "yes" ]]; then
        local vdbench_status="FAIL"
        if [[ $vdbench_exit -eq 0 ]]; then
            vdbench_status="SUCCESS"
        fi
        send_email_notification "vdbench" "$SCENARIO" "$vdbench_status" "$vdbench_duration_str"
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
    mkdir -p "$OUTPUT/mdtest_${RUN_TIMESTAMP}"

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
    local mdtest_base="$OUTPUT/mdtest_${RUN_TIMESTAMP}"

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

        if [[ "$SMOKE_MODE" != "1" ]]; then
            # Send WeChat notification if enabled
            if [[ "$WECHAT_ENABLED" == "yes" ]]; then
                local mdtest_status="FAIL"
                if [[ ${scenario_exits[$i]} -eq 0 ]]; then
                    mdtest_status="SUCCESS"
                fi
                send_wechat_notification "mdtest" "${scenario_names[$i]}" "$mdtest_status" "$mdtest_duration_str"
            fi

            # Send Email notification if enabled
            if [[ "$EMAIL_ENABLED" == "yes" ]]; then
                local mdtest_status="FAIL"
                if [[ ${scenario_exits[$i]} -eq 0 ]]; then
                    mdtest_status="SUCCESS"
                fi
                send_email_notification "mdtest" "${scenario_names[$i]}" "$mdtest_status" "$mdtest_duration_str"
            fi
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
    mkdir -p "$OUTPUT/pjdtest_${RUN_TIMESTAMP}/$SCENARIO"

    # Change to mount directory for test execution
    cd "$MOUNT"

    # Generate timestamp for output file
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    local pjdtest_output="$OUTPUT/pjdtest_${RUN_TIMESTAMP}/$SCENARIO"
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

    if [[ "$SMOKE_MODE" != "1" ]]; then
        # Send WeChat notification if enabled
        if [[ "$WECHAT_ENABLED" == "yes" ]]; then
            local pjdtest_status="FAIL"
            if [[ $pjdtest_exit -eq 0 ]]; then
                pjdtest_status="SUCCESS"
            fi
            send_wechat_notification "pjdtest" "pjdtest" "$pjdtest_status" "$pjdtest_duration_str"
        fi

        # Send Email notification if enabled
        if [[ "$EMAIL_ENABLED" == "yes" ]]; then
            local pjdtest_status="FAIL"
            if [[ $pjdtest_exit -eq 0 ]]; then
                pjdtest_status="SUCCESS"
            fi
            send_email_notification "pjdtest" "pjdtest" "$pjdtest_status" "$pjdtest_duration_str"
        fi
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
    mkdir -p "$OUTPUT/ltp_${RUN_TIMESTAMP}/$SCENARIO"

    # Change to mount directory for test execution
    cd "$MOUNT"

    # Clean up stale ltp-pan zoo files so non-root user can create new ones
    rm -f /tmp/ltp-zoo.* 2>/dev/null || true

    # Generate timestamp for output file
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    local ltp_output="$OUTPUT/ltp_${RUN_TIMESTAMP}/$SCENARIO"
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
        smoke)
            scenarios="smoketest"
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

    if [[ "$SMOKE_MODE" != "1" ]]; then
        # Send WeChat notification if enabled
        if [[ "$WECHAT_ENABLED" == "yes" ]]; then
            local ltp_status="FAIL"
            if [[ $overall_exit -eq 0 ]]; then
                ltp_status="SUCCESS"
            fi
            send_wechat_notification "ltp" "$SCENARIO" "$ltp_status" "$ltp_duration_str"
        fi

        # Send Email notification if enabled
        if [[ "$EMAIL_ENABLED" == "yes" ]]; then
            local ltp_status="FAIL"
            if [[ $overall_exit -eq 0 ]]; then
                ltp_status="SUCCESS"
            fi
            send_email_notification "ltp" "$SCENARIO" "$ltp_status" "$ltp_duration_str"
        fi
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
    mkdir -p "$OUTPUT/integration_${RUN_TIMESTAMP}/$SCENARIO"
    mkdir -p "$OUTPUT/integration_${RUN_TIMESTAMP}/$SCENARIO/allure-results"

    local start_time=$(date +"%Y-%m-%d %H:%M:%S")
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local int_output="$OUTPUT/integration_${RUN_TIMESTAMP}/$SCENARIO"
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
    local pytest_file="tests/test_${module}_pytest.py"
    local allure_dir="$int_output/allure-results"

    cd "$INTEGRATION_DIR"

    # Run tests with pytest
    # Use subshell to allow Ctrl+C to interrupt
    (
        trap 'kill -INT $$' INT TERM
        pytest "$pytest_file" --env=env_126_docker_base \
            --alluredir="$allure_dir" -v -s --mdsaddr="$mdsaddr" --reruns 5 2>&1 | tee "$log_file"
    )
    local exit_code=${PIPESTATUS[0]}

    # Parse test results from the log output
    # Format: "============= 4 failed, 90 passed, 23 rerun in 1412.22s (0:23:32) =============="
    local int_passed=0
    local int_failed=0
    local int_total=0
    local int_rerun=0
    local failed_tests=""

    # Extract test statistics from pytest summary line
    # Format examples:
    #   "======= 4 failed, 90 passed, 23 rerun in 1412.22s =======" (with reruns)
    #   "======= 4 failed, 90 passed in 100.00s =======" (no reruns)
    #   "======= 90 passed in 100.00s =======" (all pass, no failures)
    #   "======= 90 passed, 4 failed in 100.00s =======" (passed before failed)
    local summary_line=""
    if grep -qE "=+.*[0-9]+.*(passed|failed).*in [0-9]" "$log_file"; then
        summary_line=$(grep -E "=+.*[0-9]+.*(passed|failed).*in [0-9]" "$log_file" | tail -1)
    fi

    if [[ -n "$summary_line" ]]; then
        # Extract failed count: use [^0-9] prefix to ensure word boundary
        # (prevents greedy .* from splitting multi-digit numbers like 10 -> 0)
        int_failed=$(echo "$summary_line" | sed -n 's/.*[^0-9]\([0-9]\+\) failed.*/\1/p' | head -1)
        [[ -z "$int_failed" ]] && int_failed=0

        # Extract passed count: handle both "failed, X passed" and "X passed, Y failed" orderings
        int_passed=$(echo "$summary_line" | sed -n 's/.*failed, \([0-9]\+\) passed.*/\1/p' | head -1)
        if [[ -z "$int_passed" ]]; then
            # Try alternative ordering: "X passed" before "Y failed"
            int_passed=$(echo "$summary_line" | sed -n 's/.*[^0-9]\([0-9]\+\) passed.*/\1/p' | head -1)
        fi
        [[ -z "$int_passed" ]] && int_passed=0

        # Extract rerun count (if present)
        int_rerun=$(echo "$summary_line" | sed -n 's/.*[^0-9]\([0-9]\+\) rerun.*/\1/p' | head -1)
        [[ -z "$int_rerun" ]] && int_rerun=0

        # Calculate total (failed + passed)
        int_total=$((int_passed + int_failed))
    fi

    # Extract failed test names from "short test summary info" section
    if grep -q "short test summary info" "$log_file"; then
        local in_short_summary=false
        while IFS= read -r line; do
            if [[ "$in_short_summary" == true ]]; then
                # Skip the separator line (====...====)
                if [[ "$line" =~ ^=+ ]]; then
                    continue
                fi
                # Skip empty lines
                [[ -z "$line" ]] && continue
                # This is a failed test name
                if [[ -n "$failed_tests" ]]; then
                    failed_tests="${failed_tests}, ${line}"
                else
                    failed_tests="${line}"
                fi
            fi
            if [[ "$line" =~ "short test summary info" ]]; then
                in_short_summary=true
            fi
        done < "$log_file"
    fi

    echo ""
    echo "=========================================="
    echo "Integration Test Summary:"
    echo "  Total: $int_total"
    echo "  Passed: $int_passed"
    echo "  Failed: $int_failed"
    echo "=========================================="
    echo ""
    if [[ -n "$failed_tests" ]]; then
        echo "Failed Tests:"
        echo "  $failed_tests"
        echo ""
    fi

    # Determine success based on parsed results
    local status="FAIL"
    if [[ "$int_failed" == "0" ]] && [[ "$int_total" -gt "0" ]]; then
        status="SUCCESS"
    fi

    # Set details string for log_result
    local details="Total: $int_total, Passed: $int_passed, Failed: $int_failed"
    if [[ -n "$failed_tests" ]]; then
        details="${details}. Failed: ${failed_tests}"
    fi

    echo "Integration tests completed with exit code: $exit_code"
    echo "Status: $status"
    echo "Log saved to: $log_file"
    echo "Allure results saved to: $OUTPUT/integration_${RUN_TIMESTAMP}/allure-results"

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

    # Send Email notification if enabled
    if [[ "$EMAIL_ENABLED" == "yes" ]]; then
        send_email_notification "int" "$module" "$status" "$int_duration_str" "$details"
    fi

    exit $exit_code
}

mlperf_run() {
    local mlperf_start_time=$(date +"%Y-%m-%d %H:%M:%S")
    local RUN_TS=$(date +%Y%m%d_%H%M%S)

    echo "Running MLPerf Storage Benchmark"
    echo "  Mount: $MOUNT"
    echo "  Output: $OUTPUT"
    echo ""

    # Create output directories (results go to /output, datasets to /data)
    local OUTPUT_BASE="$OUTPUT/mlperf_${RUN_TS}"
    mkdir -p "$OUTPUT_BASE/results" "$OUTPUT_BASE/logs"

    # Set up dataset directories on the test filesystem
    mkdir -p /data/datasets

    # Export OUTPUT_BASE so run_model.sh writes results there
    export OUTPUT_BASE

    # Set defaults for mlperf env vars (dtt wrapper may override via -e)
    export MODELS="${MODELS:-all}"
    export SCALE="${SCALE:-small}"
    export NUM_ACCELERATORS="${NUM_ACCELERATORS:-1}"
    export ACCELERATOR_TYPE="${ACCELERATOR_TYPE:-h100}"
    export LOOPS="${LOOPS:-1}"
    export SUBMISSION_MODE="${SUBMISSION_MODE:-closed}"
    export SKIP_DATAGEN="${SKIP_DATAGEN:-auto}"
    export NUM_CLIENT_HOSTS="${NUM_CLIENT_HOSTS:-1}"
    export HOSTS="${HOSTS:-127.0.0.1}"
    export CHECKPOINTING_MODEL="${CHECKPOINTING_MODEL:-llama3-8b}"

    # Auto-detect memory
    if [[ -z "${CLIENT_HOST_MEMORY_GB}" ]]; then
        if [[ -f /proc/meminfo ]]; then
            local MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
            CLIENT_HOST_MEMORY_GB=$(( MEM_KB / 1024 / 1024 ))
            [[ "${CLIENT_HOST_MEMORY_GB}" -lt 1 ]] && CLIENT_HOST_MEMORY_GB=1
        else
            CLIENT_HOST_MEMORY_GB=16
        fi
        export CLIENT_HOST_MEMORY_GB
    fi

    # Auto-detect CPU count
    if [[ -z "${NUM_PROCESSES}" ]]; then
        NUM_PROCESSES=$(nproc 2>/dev/null || echo "4")
        export NUM_PROCESSES
    fi

    # Expand "all" shorthand
    if [[ "${MODELS}" == "all" ]]; then
        MODELS="unet3d,resnet50,cosmoflow,checkpointing"
        export MODELS
    fi

    # Validate MODELS
    IFS=',' read -ra MODEL_LIST <<< "${MODELS}"
    for MODEL in "${MODEL_LIST[@]}"; do
        MODEL="$(echo "${MODEL}" | xargs)"
        if [[ "${MODEL}" != "unet3d" && "${MODEL}" != "resnet50" && \
              "${MODEL}" != "cosmoflow" && "${MODEL}" != "checkpointing" ]]; then
            echo "Error: Unknown mlperf model: '${MODEL}'"
            echo "Valid options: unet3d, resnet50, cosmoflow, checkpointing, all"
            return 1
        fi
    done

    # Print configuration banner
    echo ""
    echo "=============================================="
    echo "  MLPerf Storage Benchmark v2.0"
    echo "=============================================="
    echo "  Models:            ${MODELS}"
    echo "  Scale:             ${SCALE}"
    echo "  Num Accelerators:  ${NUM_ACCELERATORS}"
    echo "  Accelerator Type:  ${ACCELERATOR_TYPE}"
    echo "  Loops:             ${LOOPS}"
    echo "  Submission Mode:   ${SUBMISSION_MODE}"
    echo "  Client Memory:     ${CLIENT_HOST_MEMORY_GB} GB"
    echo "  Num Processes:     ${NUM_PROCESSES}"
    echo "  Data Root:         /data/datasets"
    echo "  Results Root:      ${OUTPUT_BASE}/results"
    echo "=============================================="
    echo ""

    # Run each model sequentially
    local overall_exit=0
    local -a model_status=()
    local -a model_names=()

    for MODEL in "${MODEL_LIST[@]}"; do
        MODEL="$(echo "${MODEL}" | xargs)"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Running: ${MODEL}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""

        if /usr/local/bin/run_model.sh \
                "${MODEL}" \
                "${CLIENT_HOST_MEMORY_GB}" \
                "${NUM_PROCESSES}" \
                "${RUN_TS}"; then
            model_status+=("PASSED")
            model_names+=("${MODEL}")
            echo "[OK] Model ${MODEL} completed successfully"
        else
            model_status+=("FAILED")
            model_names+=("${MODEL}")
            echo "[ERROR] Model ${MODEL} failed"
            overall_exit=1
        fi
        echo ""
    done

    # Print summary
    echo ""
    echo "=============================================="
    echo "  MLPerf Results Summary"
    echo "=============================================="
    for i in "${!model_names[@]}"; do
        printf "  %-20s  %s\n" "${model_names[$i]}" "${model_status[$i]}"
    done
    echo ""
    echo "  Results directory: ${OUTPUT_BASE}/results"
    echo "  Full log:          ${OUTPUT_BASE}/logs"
    echo "=============================================="

    # Log result using the standard log_result function
    log_result "mlperf" "$SCENARIO" "$overall_exit" "$mlperf_start_time" "$OUTPUT_BASE"

    # Send notifications if enabled
    local mlperf_end_time=$(date +%s)
    local mlperf_start_epoch=$(date -d "$mlperf_start_time" +%s 2>/dev/null || echo "$mlperf_end_time")
    local mlperf_duration=$((mlperf_end_time - mlperf_start_epoch))
    local mlperf_duration_str="${mlperf_duration}s"
    if [[ $mlperf_duration -ge 60 ]]; then
        mlperf_duration_str="${mlperf_duration}s ($((${mlperf_duration} / 60))m $((${mlperf_duration} % 60))s)"
    fi

    local mlperf_status="FAIL"
    if [[ $overall_exit -eq 0 ]]; then
        mlperf_status="SUCCESS"
    fi

    if [[ "$WECHAT_ENABLED" == "yes" ]]; then
        send_wechat_notification "mlperf" "$SCENARIO" "$mlperf_status" "$mlperf_duration_str"
    fi
    if [[ "$EMAIL_ENABLED" == "yes" ]]; then
        send_email_notification "mlperf" "$SCENARIO" "$mlperf_status" "$mlperf_duration_str"
    fi

    echo ""
    return $overall_exit
}

# ==============================================================================
# Smoke Result Parsing Functions
# ==============================================================================

# Parse pjdtest TAP output to count pass/fail/skip/total test cases.
# Arguments: $1 = directory path containing pjdtest output files.
# Reads TAP output, sets global SMOKE_PJD_* variables.
parse_pjdtest_tap() {
    local tap_file
    tap_file=$(find "$1" -type f -name 'pjdtest_*' 2>/dev/null | sort | tail -1)

    if [[ -z "$tap_file" ]] || [[ ! -f "$tap_file" ]]; then
        SMOKE_PJD_PASS=0
        SMOKE_PJD_FAIL=0
        SMOKE_PJD_SKIP=0
        SMOKE_PJD_TOTAL=0
        echo "pjdtest stats: pass=0 fail=0 skip=0 total=0 (no TAP file found)"
        return 0
    fi

    local pass_count
    local skip_count
    local not_ok_count
    local fail_count

    pass_count=$(grep -cE '^ok[[:space:]]+[0-9]+' "$tap_file" 2>/dev/null || true)
    skip_count=$(grep -cE '^not[[:space:]]+ok[[:space:]]+[0-9]+.*#.*TODO' "$tap_file" 2>/dev/null || true)
    not_ok_count=$(grep -cE '^not[[:space:]]+ok[[:space:]]+[0-9]+' "$tap_file" 2>/dev/null || true)
    fail_count=$((not_ok_count - skip_count))

    SMOKE_PJD_PASS=$pass_count
    SMOKE_PJD_FAIL=$fail_count
    SMOKE_PJD_SKIP=$skip_count
    SMOKE_PJD_TOTAL=$((pass_count + fail_count + skip_count))

    echo "pjdtest stats: pass=$SMOKE_PJD_PASS fail=$SMOKE_PJD_FAIL skip=$SMOKE_PJD_SKIP total=$SMOKE_PJD_TOTAL"
}

# Parse LTP raw output to count pass/fail/skip/total test cases.
# Arguments: $1 = directory path containing LTP output files; $2 = ltp_exit code.
# Reads *_smoketest.raw files, sets global SMOKE_LTP_* variables.
parse_ltp_output() {
    local raw_file
    raw_file=$(find "$1" -type f -name '*_smoketest.raw' 2>/dev/null | head -1)

    if [[ -z "$raw_file" ]] || [[ ! -f "$raw_file" ]]; then
        SMOKE_LTP_PASS=0
        SMOKE_LTP_FAIL=0
        SMOKE_LTP_SKIP=0
        SMOKE_LTP_TOTAL=0
        SMOKE_LTP_TIMEOUT=0
        echo "ltp stats: pass=0 fail=0 skip=0 total=0 (no LTP raw file found)"
        return 0
    fi

    local pass_count
    local fail_tfail
    local fail_tbrok
    local skip_count
    local fail_count

    pass_count=$(grep -cE '[[:space:]]TPASS:' "$raw_file" 2>/dev/null || true)
    fail_tfail=$(grep -cE '[[:space:]]TFAIL:' "$raw_file" 2>/dev/null || true)
    fail_tbrok=$(grep -cE '[[:space:]]TBROK:' "$raw_file" 2>/dev/null || true)
    skip_count=$(grep -cE '[[:space:]]TCONF:' "$raw_file" 2>/dev/null || true)
    fail_count=$((fail_tfail + fail_tbrok))

    SMOKE_LTP_PASS=$pass_count
    SMOKE_LTP_FAIL=$fail_count
    SMOKE_LTP_SKIP=$skip_count
    SMOKE_LTP_TOTAL=$((pass_count + fail_count + skip_count))

    if [[ "$2" == "124" ]]; then
        SMOKE_LTP_TIMEOUT=1
    else
        SMOKE_LTP_TIMEOUT=0
    fi

    local timeout_str="no"
    [[ $SMOKE_LTP_TIMEOUT -eq 1 ]] && timeout_str="yes"
    echo "ltp stats: pass=$SMOKE_LTP_PASS fail=$SMOKE_LTP_FAIL skip=$SMOKE_LTP_SKIP total=$SMOKE_LTP_TOTAL [timeout=$timeout_str]"
}

# Parse integration test output for smoke results.
# Handles both run_tests.py "TEST SUITE SUMMARY" format and pytest summary lines.
# Arguments: $1 = log file path; $2 = variable prefix (e.g., SMOKE_INT_CLIENT).
# Sets global ${prefix}_PASS, ${prefix}_FAIL, ${prefix}_TOTAL variables.
parse_int_smoke_output() {
    local log_file="$1"
    local prefix="$2"

    local int_passed=0
    local int_failed=0
    local int_total=0

    if [[ ! -f "$log_file" ]]; then
        eval "${prefix}_PASS=0"
        eval "${prefix}_FAIL=0"
        eval "${prefix}_TOTAL=0"
        echo "${prefix} stats: pass=0 fail=0 total=0 (no log file)"
        return 0
    fi

    # Try run_tests.py "TEST SUITE SUMMARY" format first
    # Lines: Total Cases: N / Passed: N / Failed: N
    if grep -q "TEST SUITE SUMMARY" "$log_file" 2>/dev/null; then
        int_total=$(grep "Total Cases:" "$log_file" 2>/dev/null | tail -1 | sed -n 's/.*Total Cases:[[:space:]]*\([0-9]\+\).*/\1/p')
        int_passed=$(grep "Passed:" "$log_file" 2>/dev/null | tail -1 | sed -n 's/.*Passed:[[:space:]]*\([0-9]\+\).*/\1/p')
        int_failed=$(grep "Failed:" "$log_file" 2>/dev/null | tail -1 | sed -n 's/.*Failed:[[:space:]]*\([0-9]\+\).*/\1/p')
        [[ -z "$int_total" ]] && int_total=0
        [[ -z "$int_passed" ]] && int_passed=0
        [[ -z "$int_failed" ]] && int_failed=0
    else
        # Fallback: try pytest summary line (e.g., "======= X passed, Y failed in Zs =======")
        local summary_line
        summary_line=$(grep -E "=+.*[0-9]+.*(passed|failed).*in [0-9]" "$log_file" 2>/dev/null | tail -1 || true)
        if [[ -n "$summary_line" ]]; then
            int_passed=$(echo "$summary_line" | sed -n 's/.*failed, \([0-9]\+\) passed.*/\1/p' | head -1)
            if [[ -z "$int_passed" ]]; then
                int_passed=$(echo "$summary_line" | sed -n 's/.*[^0-9]\([0-9]\+\) passed.*/\1/p' | head -1)
            fi
            [[ -z "$int_passed" ]] && int_passed=0
            int_failed=$(echo "$summary_line" | sed -n 's/.*[^0-9]\([0-9]\+\) failed.*/\1/p' | head -1)
            [[ -z "$int_failed" ]] && int_failed=0
            int_total=$((int_passed + int_failed))
        fi
    fi

    eval "${prefix}_PASS=$int_passed"
    eval "${prefix}_FAIL=$int_failed"
    eval "${prefix}_TOTAL=$int_total"

    echo "${prefix} stats: pass=$int_passed fail=$int_failed total=$int_total"
}

# Validate mdtest smoke results using three conditions:
# 1. Exit code is 0, 2. SUMMARY rate is present, 3. Operation counts are non-zero.
# Arguments: $1 = directory path containing mdtest.raw files; $2 = mdtest exit code.
# Sets global SMOKE_MDT_PASS (1=pass, 0=fail).
validate_mdtest_smoke() {
    local raw_files
    raw_files=$(find "$1" -type f -name 'mdtest.raw' 2>/dev/null)

    if [[ -z "$raw_files" ]]; then
        SMOKE_MDT_PASS=0
        echo "mdtest validation: FAIL (reason: no mdtest.raw files found)"
        return 0
    fi

    # Condition 1: exit code must be 0
    if [[ "$2" != "0" ]]; then
        SMOKE_MDT_PASS=0
        echo "mdtest validation: FAIL (reason: non-zero exit code $2)"
        return 0
    fi

    # Condition 2: at least one file must contain SUMMARY rate
    local has_summary=false
    local summary_file=""
    while IFS= read -r raw_file; do
        if grep -q "SUMMARY rate" "$raw_file" 2>/dev/null; then
            has_summary=true
            summary_file="$raw_file"
            break
        fi
    done <<< "$raw_files"

    if [[ "$has_summary" != "true" ]]; then
        SMOKE_MDT_PASS=0
        echo "mdtest validation: FAIL (reason: no SUMMARY rate found)"
        return 0
    fi

    # Condition 3: at least one file with SUMMARY rate must have non-zero operation counts
    local has_nonzero_ops=false
    while IFS= read -r raw_file; do
        if grep -q "SUMMARY rate" "$raw_file" 2>/dev/null; then
            # Extract the block after SUMMARY rate and check for non-zero operation rates
            if grep -A 100 "SUMMARY rate" "$raw_file" 2>/dev/null | grep -qE '(File creation|File stat|File removal).*[1-9][0-9]*\.[0-9]+'; then
                has_nonzero_ops=true
                break
            fi
        fi
    done <<< "$raw_files"

    if [[ "$has_nonzero_ops" != "true" ]]; then
        SMOKE_MDT_PASS=0
        echo "mdtest validation: FAIL (reason: zero operation counts)"
        return 0
    fi

    SMOKE_MDT_PASS=1
    echo "mdtest validation: PASS"
}

# Generate combined smoke summary reports (JSON + text).
# Arguments: $1 = smoke_base directory path; $2 = aggregate exit code.
# Reads global SMOKE_PJD_*, SMOKE_LTP_*, SMOKE_MDT_PASS variables.
generate_smoke_summary() {
    local smoke_base="$1"
    local aggregate_exit="$2"

    # Determine per-tool status strings
    local pjd_status="FAIL"
    if [[ $SMOKE_PJD_FAIL -eq 0 ]] && [[ $SMOKE_PJD_TOTAL -gt 0 ]]; then
        pjd_status="PASS"
    fi

    local mdt_status="FAIL"
    [[ $SMOKE_MDT_PASS -eq 1 ]] && mdt_status="PASS"

    local ltp_status="FAIL"
    if [[ $SMOKE_LTP_TIMEOUT -eq 1 ]]; then
        ltp_status="TIMEOUT"
    elif [[ $SMOKE_LTP_FAIL -eq 0 ]] && [[ $SMOKE_LTP_TOTAL -gt 0 ]]; then
        ltp_status="PASS"
    fi

    local int_client_status="FAIL"
    if [[ ${SMOKE_INT_CLIENT_FAIL:-0} -eq 0 ]] && [[ ${SMOKE_INT_CLIENT_TOTAL:-0} -gt 0 ]]; then
        int_client_status="PASS"
    fi

    local int_cachenode_status="FAIL"
    if [[ ${SMOKE_INT_CACHENODE_FAIL:-0} -eq 0 ]] && [[ ${SMOKE_INT_CACHENODE_TOTAL:-0} -gt 0 ]]; then
        int_cachenode_status="PASS"
    fi

    local int_quota_status="FAIL"
    if [[ ${SMOKE_INT_QUOTA_FAIL:-0} -eq 0 ]] && [[ ${SMOKE_INT_QUOTA_TOTAL:-0} -gt 0 ]]; then
        int_quota_status="PASS"
    fi

    local agg_status="FAIL"
    [[ $aggregate_exit -eq 0 ]] && agg_status="PASS"

    # Generate smoke_summary.json
    cat > "${smoke_base}/smoke_summary.json" << EOF
{
  "smoke_timestamp": "${RUN_TIMESTAMP}",
  "tools": {
    "pjdtest": {
      "status": "${pjd_status}",
      "pass": ${SMOKE_PJD_PASS:-0},
      "fail": ${SMOKE_PJD_FAIL:-0},
      "skip": ${SMOKE_PJD_SKIP:-0},
      "total": ${SMOKE_PJD_TOTAL:-0}
    },
    "mdtest": {
      "status": "${mdt_status}",
      "pass": 0,
      "fail": 0,
      "skip": 0,
      "total": 0,
      "note": "Performance benchmark - pass/fail determined by exit code, SUMMARY rate presence, and non-zero operation counts"
    },
    "ltp": {
      "status": "${ltp_status}",
      "pass": ${SMOKE_LTP_PASS:-0},
      "fail": ${SMOKE_LTP_FAIL:-0},
      "skip": ${SMOKE_LTP_SKIP:-0},
      "total": ${SMOKE_LTP_TOTAL:-0},
      "timeout": ${SMOKE_LTP_TIMEOUT:-0}
    },
    "int_client": {
      "status": "${int_client_status}",
      "pass": ${SMOKE_INT_CLIENT_PASS:-0},
      "fail": ${SMOKE_INT_CLIENT_FAIL:-0},
      "total": ${SMOKE_INT_CLIENT_TOTAL:-0},
      "env": "${INT_ENV}"
    },
    "int_cache_node": {
      "status": "${int_cachenode_status}",
      "pass": ${SMOKE_INT_CACHENODE_PASS:-0},
      "fail": ${SMOKE_INT_CACHENODE_FAIL:-0},
      "total": ${SMOKE_INT_CACHENODE_TOTAL:-0},
      "env": "${INT_ENV}"
    },
    "int_quota": {
      "status": "${int_quota_status}",
      "pass": ${SMOKE_INT_QUOTA_PASS:-0},
      "fail": ${SMOKE_INT_QUOTA_FAIL:-0},
      "total": ${SMOKE_INT_QUOTA_TOTAL:-0},
      "env": "${INT_ENV}"
    }
  },
  "aggregate": {
    "status": "${agg_status}",
    "exit_code": ${aggregate_exit}
  }
}
EOF

    # Determine mdtest reason string for text output
    local mdt_reason="SUMMARY rate verified, non-zero operations"
    if [[ $SMOKE_MDT_PASS -eq 1 ]]; then
        mdt_reason="SUMMARY rate verified, non-zero operations"
    else
        # Extract reason from validate_mdtest_smoke output (best effort fallback)
        mdt_reason="FAIL - see smoke_summary.json for details"
    fi

    # Generate smoke_summary.txt
    cat > "${smoke_base}/smoke_summary.txt" << EOF
==============================================
Smoke Test Summary
Timestamp: ${RUN_TIMESTAMP}
==============================================

pjdtest       [${pjd_status}]  pass: ${SMOKE_PJD_PASS:-0}  fail: ${SMOKE_PJD_FAIL:-0}  skip: ${SMOKE_PJD_SKIP:-0}  total: ${SMOKE_PJD_TOTAL:-0}
mdtest        [${mdt_status}]  ${mdt_reason}
ltp           [${ltp_status}]  pass: ${SMOKE_LTP_PASS:-0}  fail: ${SMOKE_LTP_FAIL:-0}  skip: ${SMOKE_LTP_SKIP:-0}  total: ${SMOKE_LTP_TOTAL:-0}
int_client    [${int_client_status}]  pass: ${SMOKE_INT_CLIENT_PASS:-0}  fail: ${SMOKE_INT_CLIENT_FAIL:-0}  total: ${SMOKE_INT_CLIENT_TOTAL:-0}  env: ${INT_ENV}
int_cache_node [${int_cachenode_status}]  pass: ${SMOKE_INT_CACHENODE_PASS:-0}  fail: ${SMOKE_INT_CACHENODE_FAIL:-0}  total: ${SMOKE_INT_CACHENODE_TOTAL:-0}  env: ${INT_ENV}
int_quota     [${int_quota_status}]  pass: ${SMOKE_INT_QUOTA_PASS:-0}  fail: ${SMOKE_INT_QUOTA_FAIL:-0}  total: ${SMOKE_INT_QUOTA_TOTAL:-0}  env: ${INT_ENV}

Aggregate: ${agg_status}
==============================================
EOF

    echo "Smoke summary reports generated: ${smoke_base}/smoke_summary.json, ${smoke_base}/smoke_summary.txt"
}

# Send combined smoke notification (WeChat + Email) with all three tools' results.
# Arguments: $1 = smoke_base directory path; $2 = aggregate exit code; $3 = start timestamp (seconds since epoch).
# Reads global SMOKE_PJD_*, SMOKE_LTP_*, SMOKE_MDT_PASS variables set by parse/validate functions.
send_smoke_notification() {
    local smoke_base="$1"
    local aggregate_exit="$2"
    local start_ts="$3"

    # Calculate total duration
    local end_ts=$(date +%s)
    local duration_sec=$((end_ts - start_ts))
    local duration_str
    duration_str=$(printf '%dm%ds' $((duration_sec/60)) $((duration_sec%60)))

    # Determine aggregate status
    local agg_status="SUCCESS"
    if [[ $aggregate_exit -ne 0 ]]; then
        agg_status="FAIL"
    fi

    # Determine per-tool statuses
    local pjd_status="PASS"
    if [[ ${SMOKE_PJD_FAIL:-0} -ne 0 ]] || [[ ${SMOKE_PJD_TOTAL:-0} -eq 0 ]]; then
        pjd_status="FAIL"
    fi

    local mdt_status="PASS"
    if [[ ${SMOKE_MDT_PASS:-0} -ne 1 ]]; then
        mdt_status="FAIL"
    fi

    local ltp_status="PASS"
    if [[ ${SMOKE_LTP_TIMEOUT:-0} -eq 1 ]]; then
        ltp_status="TIMEOUT"
    elif [[ ${SMOKE_LTP_FAIL:-0} -ne 0 ]] || [[ ${SMOKE_LTP_TOTAL:-0} -eq 0 ]]; then
        ltp_status="FAIL"
    fi

    local int_client_status="PASS"
    if [[ ${SMOKE_INT_CLIENT_FAIL:-0} -ne 0 ]] || [[ ${SMOKE_INT_CLIENT_TOTAL:-0} -eq 0 ]]; then
        int_client_status="FAIL"
    fi

    local int_cachenode_status="PASS"
    if [[ ${SMOKE_INT_CACHENODE_FAIL:-0} -ne 0 ]] || [[ ${SMOKE_INT_CACHENODE_TOTAL:-0} -eq 0 ]]; then
        int_cachenode_status="FAIL"
    fi

    local int_quota_status="PASS"
    if [[ ${SMOKE_INT_QUOTA_FAIL:-0} -ne 0 ]] || [[ ${SMOKE_INT_QUOTA_TOTAL:-0} -eq 0 ]]; then
        int_quota_status="FAIL"
    fi

    # Build combined details string for notification functions (newline-separated for readability)
    local details="pjdtest[${pjd_status}] pass:${SMOKE_PJD_PASS:-0} fail:${SMOKE_PJD_FAIL:-0} skip:${SMOKE_PJD_SKIP:-0} total:${SMOKE_PJD_TOTAL:-0}
mdtest[${mdt_status}]
ltp[${ltp_status}] pass:${SMOKE_LTP_PASS:-0} fail:${SMOKE_LTP_FAIL:-0} skip:${SMOKE_LTP_SKIP:-0} total:${SMOKE_LTP_TOTAL:-0}
int_client[${int_client_status}] pass:${SMOKE_INT_CLIENT_PASS:-0} fail:${SMOKE_INT_CLIENT_FAIL:-0} total:${SMOKE_INT_CLIENT_TOTAL:-0}
int_cache_node[${int_cachenode_status}] pass:${SMOKE_INT_CACHENODE_PASS:-0} fail:${SMOKE_INT_CACHENODE_FAIL:-0} total:${SMOKE_INT_CACHENODE_TOTAL:-0}
int_quota[${int_quota_status}] pass:${SMOKE_INT_QUOTA_PASS:-0} fail:${SMOKE_INT_QUOTA_FAIL:-0} total:${SMOKE_INT_QUOTA_TOTAL:-0}"

    echo ""
    echo "[notify] Sending combined smoke notification (WeChat: $WECHAT_ENABLED, Email: $EMAIL_ENABLED)..."

    # Send WeChat notification (function sourced from notify.sh)
    send_wechat_notification "smoke" "smoke" "$agg_status" "$duration_str" "$details"

    # Send Email notification (function sourced from notify.sh)
    send_email_notification "smoke" "smoke" "$agg_status" "$duration_str" "$details"

    echo "[notify] Combined smoke notification sent."
}

# Check if a tool is in the SMOKE_EXCLUDE list.
# "int" in the exclude list matches all int_* tools.
is_excluded() {
    local tool="$1"
    [[ -z "$SMOKE_EXCLUDE" ]] && return 1

    local IFS=','
    local -a items=($SMOKE_EXCLUDE)
    for item in "${items[@]}"; do
        item=$(echo "$item" | xargs)
        [[ "$item" == "$tool" ]] && return 0
        # "int" excludes all int_* tools
        if [[ "$item" == "int" ]] && [[ "$tool" == int_* ]]; then
            return 0
        fi
    done
    return 1
}

smoke_run() {
    # Build list of tools to run for display
    local tools_list=""
    if ! is_excluded "pjdtest"; then
        tools_list="${tools_list}  pjdtest\n"
    fi
    if ! is_excluded "mdtest"; then
        tools_list="${tools_list}  mdtest\n"
    fi
    if ! is_excluded "ltp"; then
        tools_list="${tools_list}  ltp\n"
    fi
    if ! is_excluded "int_client"; then
        tools_list="${tools_list}  int_client\n"
    fi
    if ! is_excluded "int_cache_node"; then
        tools_list="${tools_list}  int_cache_node\n"
    fi
    if ! is_excluded "int_quota"; then
        tools_list="${tools_list}  int_quota\n"
    fi

    echo "=============================================="
    echo "Smoke Test Suite"
    echo "=============================================="
    if [[ -n "$SMOKE_EXCLUDE" ]]; then
        echo "Excluding: $SMOKE_EXCLUDE"
    fi
    echo "Tools to run:"
    echo -e "$tools_list"
    echo "Output: $OUTPUT/smoke_${RUN_TIMESTAMP}/"
    echo "Mode:   fail-continue (all tools run regardless)"
    echo "=============================================="
    echo ""

    # Record start time for notification duration calculation
    local smoke_start_ts=$(date +%s)

    # Save original environment
    local orig_output="$OUTPUT"
    local orig_scenario="$SCENARIO"
    local orig_np="$NP"

    # Create unified smoke output directory
    local smoke_base="$OUTPUT/smoke_${RUN_TIMESTAMP}"
    mkdir -p "$smoke_base"

    # Enable SMOKE_MODE to suppress per-tool notifications
    export SMOKE_MODE=1

    # Track per-tool exit codes
    local pjdtest_exit=0
    local mdtest_exit=0
    local ltp_exit=0
    local aggregate_exit=0

    # ---- Setup: test environment initialization ----
    echo "=============================================="
    echo "[Setup] Running test environment setup: $INT_ENV"
    echo "=============================================="
    local setup_output
    set +e
    setup_output=$(
        trap 'kill -INT $$' INT TERM
        cd "$INTEGRATION_DIR" && python3 tests/test_env_setup.py "$INT_ENV" 2>&1
    )
    local setup_exit=$?
    set -e
    echo "$setup_output"
    if [[ $setup_exit -ne 0 ]]; then
        echo "WARNING: test_env_setup.py failed (exit: $setup_exit) -- continuing"
        aggregate_exit=1
    else
        echo "test_env_setup.py completed successfully"
    fi

    # Extract DINGOFS_TEMP_MOUNTDIR from setup output.
    # The host parent dir is bind-mounted to /data, so the container path
    # is /data/<basename_of_temp_mountdir>.
    local temp_mountdir_host
    temp_mountdir_host=$(echo "$setup_output" | sed -n 's/.*DINGOFS_TEMP_MOUNTDIR=//p' | head -1 | xargs)
    if [[ -n "$temp_mountdir_host" ]]; then
        local temp_mountdir_name
        temp_mountdir_name=$(basename "$temp_mountdir_host")
        MOUNT="/data/${temp_mountdir_name}"
        echo "Smoke mount point updated to: $MOUNT"
    fi
    echo ""

    # ---- Tool 1: pjdtest -s all ----
    if ! is_excluded "pjdtest"; then
    echo "=============================================="
    echo "[1/6] Running pjdtest -s all"
    echo "=============================================="
    SCENARIO="all"
    OUTPUT="${smoke_base}/pjdtest"
    mkdir -p "$OUTPUT"
    set +e
    pjdtest_run
    pjdtest_exit=$?
    set -e
    echo "--- Parsing pjdtest results ---"
    parse_pjdtest_tap "${smoke_base}/pjdtest"
    if [[ $pjdtest_exit -ne 0 ]]; then
        echo "pjdtest completed with failures (exit: $pjdtest_exit) -- continuing to next tool"
        aggregate_exit=1
    else
        echo "pjdtest completed successfully (exit: 0)"
    fi
    else
        echo "--- Skipping pjdtest (excluded) ---"
        SMOKE_PJD_PASS=0; SMOKE_PJD_FAIL=0; SMOKE_PJD_SKIP=0; SMOKE_PJD_TOTAL=0
    fi
    echo ""

    # ---- Tool 2: mdtest -s all -n 8 ----
    if ! is_excluded "mdtest"; then
    echo "=============================================="
    echo "[2/6] Running mdtest -s all -n 8"
    echo "=============================================="
    SCENARIO="all"
    NP=8
    OUTPUT="${smoke_base}/mdtest"
    mkdir -p "$OUTPUT"
    set +e
    mdtest_run
    mdtest_exit=$?
    set -e
    echo "--- Validating mdtest results ---"
    validate_mdtest_smoke "${smoke_base}/mdtest" $mdtest_exit
    if [[ $mdtest_exit -ne 0 ]]; then
        echo "mdtest completed with failures (exit: $mdtest_exit) -- continuing to next tool"
        aggregate_exit=1
    else
        echo "mdtest completed successfully (exit: 0)"
    fi
    else
        echo "--- Skipping mdtest (excluded) ---"
        SMOKE_MDT_PASS=0
    fi
    echo ""

    # ---- Tool 3: ltp -s smoke ----
    if ! is_excluded "ltp"; then
    echo "=============================================="
    echo "[3/6] Running ltp -s smoke"
    echo "=============================================="
    SCENARIO="smoke"
    OUTPUT="${smoke_base}/ltp"
    mkdir -p "$OUTPUT"
    set +e
    ltp_run
    ltp_exit=$?
    set -e
    echo "--- Parsing ltp results ---"
    parse_ltp_output "${smoke_base}/ltp" $ltp_exit
    if [[ $ltp_exit -ne 0 ]]; then
        echo "ltp completed with failures (exit: $ltp_exit)"
        aggregate_exit=1
    else
        echo "ltp completed successfully (exit: 0)"
    fi
    else
        echo "--- Skipping ltp (excluded) ---"
        SMOKE_LTP_PASS=0; SMOKE_LTP_FAIL=0; SMOKE_LTP_SKIP=0; SMOKE_LTP_TOTAL=0
    fi
    echo ""

    # ---- Tool 4: int client ----
    if ! is_excluded "int_client"; then
    echo "=============================================="
    echo "[4/6] Running integration test: client"
    echo "=============================================="
    local int_client_output="${smoke_base}/int_client"
    mkdir -p "$int_client_output"
    local int_client_log="${int_client_output}/int_client.log"
    set +e
    (
        trap 'kill -INT $$' INT TERM
        cd "$INTEGRATION_DIR" && python3 run_tests.py client --run-level smoke --env "$INT_ENV" --reruns 5 2>&1 | tee "$int_client_log"
    )
    local int_client_exit=${PIPESTATUS[0]}
    set -e
    echo "--- Parsing int client results ---"
    parse_int_smoke_output "$int_client_log" "SMOKE_INT_CLIENT"
    if [[ $int_client_exit -ne 0 ]]; then
        echo "int client completed with failures (exit: $int_client_exit) -- continuing"
        aggregate_exit=1
    else
        echo "int client completed successfully (exit: 0)"
    fi
    else
        echo "--- Skipping int_client (excluded) ---"
        SMOKE_INT_CLIENT_PASS=0; SMOKE_INT_CLIENT_FAIL=0; SMOKE_INT_CLIENT_TOTAL=0
    fi
    echo ""

    # ---- Tool 5: int cache_node ----
    if ! is_excluded "int_cache_node"; then
    echo "=============================================="
    echo "[5/6] Running integration test: cache_node"
    echo "=============================================="
    local int_cachenode_output="${smoke_base}/int_cache_node"
    mkdir -p "$int_cachenode_output"
    local int_cachenode_log="${int_cachenode_output}/int_cache_node.log"
    set +e
    (
        trap 'kill -INT $$' INT TERM
        cd "$INTEGRATION_DIR" && python3 run_tests.py cache_node --run-level smoke --env "$INT_ENV" --reruns 5 2>&1 | tee "$int_cachenode_log"
    )
    local int_cachenode_exit=${PIPESTATUS[0]}
    set -e
    echo "--- Parsing int cache_node results ---"
    parse_int_smoke_output "$int_cachenode_log" "SMOKE_INT_CACHENODE"
    if [[ $int_cachenode_exit -ne 0 ]]; then
        echo "int cache_node completed with failures (exit: $int_cachenode_exit) -- continuing"
        aggregate_exit=1
    else
        echo "int cache_node completed successfully (exit: 0)"
    fi
    else
        echo "--- Skipping int_cache_node (excluded) ---"
        SMOKE_INT_CACHENODE_PASS=0; SMOKE_INT_CACHENODE_FAIL=0; SMOKE_INT_CACHENODE_TOTAL=0
    fi
    echo ""

    # ---- Tool 6: int quota ----
    if ! is_excluded "int_quota"; then
    echo "=============================================="
    echo "[6/6] Running integration test: quota"
    echo "=============================================="
    local int_quota_output="${smoke_base}/int_quota"
    mkdir -p "$int_quota_output"
    local int_quota_log="${int_quota_output}/int_quota.log"
    set +e
    (
        trap 'kill -INT $$' INT TERM
        cd "$INTEGRATION_DIR" && python3 run_tests.py quota --run-level smoke --env "$INT_ENV" --reruns 5 2>&1 | tee "$int_quota_log"
    )
    local int_quota_exit=${PIPESTATUS[0]}
    set -e
    echo "--- Parsing int quota results ---"
    parse_int_smoke_output "$int_quota_log" "SMOKE_INT_QUOTA"
    if [[ $int_quota_exit -ne 0 ]]; then
        echo "int quota completed with failures (exit: $int_quota_exit) -- continuing"
        aggregate_exit=1
    else
        echo "int quota completed successfully (exit: 0)"
    fi
    else
        echo "--- Skipping int_quota (excluded) ---"
        SMOKE_INT_QUOTA_PASS=0; SMOKE_INT_QUOTA_FAIL=0; SMOKE_INT_QUOTA_TOTAL=0
    fi
    echo ""

    # Restore original environment
    OUTPUT="$orig_output"
    SCENARIO="$orig_scenario"
    NP="$orig_np"
    unset SMOKE_MODE

    # Generate smoke summary reports
    generate_smoke_summary "$smoke_base" $aggregate_exit

    # Send combined notification (only fires if WECHAT/EMAIL env vars are set)
    send_smoke_notification "$smoke_base" $aggregate_exit $smoke_start_ts

    # Final summary with statistics
    echo "=============================================="
    echo "Smoke Test Suite Complete"
    echo "=============================================="
    echo "  pjdtest:     pass=$SMOKE_PJD_PASS fail=$SMOKE_PJD_FAIL skip=$SMOKE_PJD_SKIP total=$SMOKE_PJD_TOTAL (exit=$pjdtest_exit)"
    echo "  mdtest:      $( [[ $SMOKE_MDT_PASS -eq 1 ]] && echo 'PASS' || echo 'FAIL' ) (exit=$mdtest_exit)"
    echo "  ltp:         pass=$SMOKE_LTP_PASS fail=$SMOKE_LTP_FAIL skip=$SMOKE_LTP_SKIP total=$SMOKE_LTP_TOTAL (exit=$ltp_exit)"
    echo "  int_client:  pass=$SMOKE_INT_CLIENT_PASS fail=$SMOKE_INT_CLIENT_FAIL total=$SMOKE_INT_CLIENT_TOTAL (exit=$int_client_exit)"
    echo "  int_cache_node: pass=$SMOKE_INT_CACHENODE_PASS fail=$SMOKE_INT_CACHENODE_FAIL total=$SMOKE_INT_CACHENODE_TOTAL (exit=$int_cachenode_exit)"
    echo "  int_quota:   pass=$SMOKE_INT_QUOTA_PASS fail=$SMOKE_INT_QUOTA_FAIL total=$SMOKE_INT_QUOTA_TOTAL (exit=$int_quota_exit)"
    echo "  aggregate exit: $aggregate_exit"
    echo "  Output: $smoke_base"
    echo "  Reports: smoke_summary.json, smoke_summary.txt"
    echo "=============================================="

    return $aggregate_exit
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

    # Generate run timestamp for output directory
    RUN_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

    echo "=============================================="
    echo "DingoFS Storage Testsuite Tools"
    echo "=============================================="
    echo "Tool:     $TOOL"
    echo "Scenario: $SCENARIO"
    echo "Mount:    $MOUNT"
    echo "Output:   $OUTPUT"
    echo "Run Time: $RUN_TIMESTAMP"
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
