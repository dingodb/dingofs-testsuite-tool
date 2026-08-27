#!/bin/bash

# 检查参数
if [ $# -lt 1 ]; then
    echo "用法: $0 <测试目录> [输出目录] [--file-size <大小>] [--file-count <数量>] [--block-size <大小>] [--threads <列表>]"
    echo "示例: $0 /data /output --file-size 10m --file-count 100 --block-size 1m --threads 1,4,8,16"
    exit 1
fi

TEST_PATH="$1"
shift
OUT_DIR="/output"
if [ $# -gt 0 ] && [[ "$1" != --* ]]; then
    OUT_DIR="$1"
    shift
fi

# 默认测试参数
FILE_SIZE="4m"
BLOCK_SIZE="4m"
DIRS_PER_THREAD=1
FILES_PER_DIR=256
THREADS="1,2,4,8,16,32"

while [ $# -gt 0 ]; do
    if [ $# -lt 2 ] || [ -z "$2" ] || [[ "$2" == --* ]]; then
        echo "错误: $1 需要一个值"
        exit 1
    fi
    case "$1" in
        --file-size)
            FILE_SIZE="$2"
            ;;
        --file-count)
            FILES_PER_DIR="$2"
            ;;
        --block-size)
            BLOCK_SIZE="$2"
            ;;
        --threads)
            THREADS="$2"
            ;;
        *)
            echo "错误: 未知参数 $1"
            exit 1
            ;;
    esac
    shift 2
done

if [[ ! "$FILE_SIZE" =~ ^[1-9][0-9]*([KkMmGgTtPpEe]([iI]?[Bb])?)?$ ]]; then
    echo "错误: --file-size 必须是正数大小，当前值: $FILE_SIZE"
    exit 1
fi
if [[ ! "$BLOCK_SIZE" =~ ^[1-9][0-9]*([KkMmGgTtPpEe]([iI]?[Bb])?)?$ ]]; then
    echo "错误: --block-size 必须是正数大小，当前值: $BLOCK_SIZE"
    exit 1
fi
if [[ ! "$FILES_PER_DIR" =~ ^[1-9][0-9]*$ ]]; then
    echo "错误: --file-count 必须是正整数，当前值: $FILES_PER_DIR"
    exit 1
fi
if [[ ! "$THREADS" =~ ^[1-9][0-9]*(,[1-9][0-9]*)*$ ]]; then
    echo "错误: --threads 必须是逗号分隔的正整数，当前值: $THREADS"
    exit 1
fi
IFS=',' read -r -a THREAD_VALUES <<< "$THREADS"

# 检查目录是否存在，不存在则创建
if [ ! -d "$TEST_PATH" ]; then
    mkdir -p "$TEST_PATH" || { echo "无法创建目录 $TEST_PATH"; exit 1; }
fi

# 检查 elbencho 是否可用
if ! command -v elbencho &> /dev/null; then
    echo "错误: 未找到 elbencho 命令，请先安装。"
    exit 1
fi

# 创建本次测试的根目录（带时间戳，放到 output 目录下避免 FUSE 权限问题）
RUN_ID=$(date +%Y%m%d_%H%M%S)
ROOT_DIR="$OUT_DIR/elbencho_small_${RUN_ID}"
mkdir -p "$ROOT_DIR/raw_logs" || { echo "错误: 无法创建输出目录"; exit 1; }
RAW_LOG_DIR="$ROOT_DIR/raw_logs"
REPORT_FILE="$ROOT_DIR/elbencho_small_summary_${RUN_ID}.md"

# 结果 CSV 文件
RESULT_FILE="$ROOT_DIR/result.csv"
echo "测试类型,并发度,吞吐量(MiB/s),平均延迟(ms),最大延迟(ms),原始日志文件" > "$RESULT_FILE"

OVERALL_EXIT=0
declare -a COMMAND_LABELS=()
declare -a COMMAND_VALUES=()
declare -a WRITE_RESULTS=()
declare -a READ_RESULTS=()

# 清空测试目录（保留顶层目录）
cleanup_test_dir() {
    rm -rf "$TEST_PATH"/*
}

# 执行测试并提取结果
run_test() {
    local op="$1"
    local threads="$2"
    local raw_log="${RAW_LOG_DIR}/raw_${op}_t${threads}.log"
    local cmd

    if [ "$op" == "write" ]; then
        cmd="elbencho $TEST_PATH -w -t $threads -n $DIRS_PER_THREAD -N $FILES_PER_DIR -s $FILE_SIZE -b $BLOCK_SIZE --direct --lat -d"
    else
        cmd="elbencho $TEST_PATH -r -t $threads -n $DIRS_PER_THREAD -N $FILES_PER_DIR -s $FILE_SIZE -b $BLOCK_SIZE --direct --lat -d"
    fi

    echo "运行: $cmd"
    # 确保目录存在
    mkdir -p "$(dirname "$raw_log")"
    mkdir -p "$(dirname "$RESULT_FILE")"
    # 执行并保存输出
    $cmd 2>&1 | tee "$raw_log"
    local cmd_exit=${PIPESTATUS[0]}
    local status="PASS"
    if [ "$cmd_exit" -ne 0 ]; then
        status="FAIL"
        OVERALL_EXIT=1
    fi

    # ---- 解析结果 ----
    # 1. 吞吐量：从 "Throughput MiB/s" 行提取
    local throughput="N/A"
    local tp_line=$(grep -i "Throughput MiB" "$raw_log" | head -1)
    if [ -n "$tp_line" ]; then
        throughput=$(echo "$tp_line" | grep -oE '[0-9]+(\.[0-9]+)?' | head -1)
    fi

    # 2. 延迟：从 "Files latency" 行提取
    local avg_lat="N/A"
    local max_lat="N/A"
    local lat_line=$(grep -i "Files latency" "$raw_log" | head -1)
    if [ -n "$lat_line" ]; then
        avg_lat=$(echo "$lat_line" | grep -oP 'avg=\K[0-9.]+')
        max_lat=$(echo "$lat_line" | grep -oP 'max=\K[0-9.]+')
    fi

    local op_label="读"
    [ "$op" == "write" ] && op_label="写"
    COMMAND_LABELS+=("${op_label}测试（并发度 ${threads}）")
    COMMAND_VALUES+=("$cmd")
    local result_row="| $threads | $status | $cmd_exit | $throughput | $avg_lat | $max_lat | \`$raw_log\` |"
    if [ "$op" == "write" ]; then
        WRITE_RESULTS+=("$result_row")
    else
        READ_RESULTS+=("$result_row")
    fi

    # 记录结果
    echo "$op,$threads,$throughput,$avg_lat,$max_lat,$raw_log" >> "$RESULT_FILE"
    echo "结果: $op, $threads, 状态=$status, exit_code=$cmd_exit, 吞吐量=$throughput MiB/s, 平均延迟=$avg_lat ms, 最大延迟=$max_lat ms"
    echo "原始输出已保存至: $raw_log"
}

generate_markdown_report() {
    {
        echo "# Elbencho Small 测试报告"
        echo
        echo "## 测试配置"
        echo
        echo "| 参数 | 值 |"
        echo "|---|---|"
        echo "| 测试目录 | \`$TEST_PATH\` |"
        echo "| 文件大小 | $FILE_SIZE |"
        echo "| 块大小 | $BLOCK_SIZE |"
        echo "| 每线程目录数 | $DIRS_PER_THREAD |"
        echo "| 每目录文件数 | $FILES_PER_DIR |"
        echo "| 并发度 | $THREADS |"
        echo "| 生成时间 | $(date '+%Y-%m-%d %H:%M:%S') |"
        echo
        echo "## 实际执行命令"
        echo
        local index
        for index in "${!COMMAND_VALUES[@]}"; do
            echo "### $((index + 1)). ${COMMAND_LABELS[$index]}"
            echo
            echo '```bash'
            echo "${COMMAND_VALUES[$index]}"
            echo '```'
            echo
        done
        echo "## 写测试结果"
        echo
        echo "| 并发度 | 状态 | Exit Code | 吞吐量 (MiB/s) | 平均延迟 (ms) | 最大延迟 (ms) | 原始日志 |"
        echo "|---:|---|---:|---:|---:|---:|---|"
        printf '%s\n' "${WRITE_RESULTS[@]}"
        echo
        echo "## 读测试结果"
        echo
        echo "| 并发度 | 状态 | Exit Code | 吞吐量 (MiB/s) | 平均延迟 (ms) | 最大延迟 (ms) | 原始日志 |"
        echo "|---:|---|---:|---:|---:|---:|---|"
        printf '%s\n' "${READ_RESULTS[@]}"
        echo
        echo "---"
        echo "*由 DingoFS 存储性能测试工具生成*"
    } > "$REPORT_FILE"
}

# 主循环
for threads in "${THREAD_VALUES[@]}"; do
    echo "==================== 并发度 = $threads ===================="

    # ---- 顺序写 ----
    echo "--- 顺序写测试 ---"
    cleanup_test_dir
    run_test "write" "$threads"

    # ---- 顺序读（使用刚写入的文件） ----
    echo "--- 顺序读测试 ---"
    run_test "read" "$threads"

    echo ""
done

generate_markdown_report

echo "所有测试完成！结果已保存到: $RESULT_FILE"
echo "原始日志目录: $RAW_LOG_DIR"
echo "Markdown 报告: $REPORT_FILE"
cat "$RESULT_FILE"
exit "$OVERALL_EXIT"
