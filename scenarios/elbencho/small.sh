#!/bin/bash

# 检查参数
if [ $# -ne 1 ]; then
    echo "用法: $0 <测试目录>"
    echo "示例: $0 /mnt/disk5/dingo_autotest/client/test1"
    exit 1
fi

TEST_PATH="$1"
OUT_DIR="${2:-/output}"

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
ROOT_DIR="$OUT_DIR/elbencho_small_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$ROOT_DIR/raw_logs" || { echo "错误: 无法创建输出目录"; exit 1; }
RAW_LOG_DIR="$ROOT_DIR/raw_logs"

# 结果 CSV 文件
RESULT_FILE="$ROOT_DIR/result.csv"
echo "测试类型,并发度,吞吐量(MiB/s),平均延迟(ms),最大延迟(ms),原始日志文件" > "$RESULT_FILE"

# 固定测试参数
FILE_SIZE="4m"
BLOCK_SIZE="4m"
DIRS_PER_THREAD=1
FILES_PER_DIR=256

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

    # 记录结果
    echo "$op,$threads,$throughput,$avg_lat,$max_lat,$raw_log" >> "$RESULT_FILE"
    echo "结果: $op, $threads, 吞吐量=$throughput MiB/s, 平均延迟=$avg_lat ms, 最大延迟=$max_lat ms"
    echo "原始输出已保存至: $raw_log"
}

# 主循环
for threads in 1 2 4 8 16 32; do
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

echo "所有测试完成！结果已保存到: $RESULT_FILE"
echo "原始日志目录: $RAW_LOG_DIR"
cat "$RESULT_FILE"
