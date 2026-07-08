#!/bin/bash
#
# MD5 完整性循环测试
# 用法: ./md5_integrity_test.sh <目标路径>
#

set -e

if [[ $# -ne 1 ]]; then
    echo "用法: $0 <目标路径>"
    echo "示例: $0 /mnt/disk0/dingofs-autotest/client/test"
    exit 1
fi

TARGET_DIR="$1"
DATA_DIR="./data"
FILE_COUNT=100
ROUND=0

cleanup() {
    echo ""
    echo "已运行 $ROUND 轮，退出。"
}
trap cleanup EXIT

mkdir -p "$DATA_DIR"

generate_files() {
    rm -f "$DATA_DIR"/f*
    echo "生成 $FILE_COUNT 个文件 (50MB~500MB)..."
    for i in $(seq 1 "$FILE_COUNT"); do
        local size=$(( (RANDOM % 450) + 50 ))
        dd if=/dev/urandom of="$DATA_DIR/f$i" bs=1M count="$size" status=none
    done
    echo "  → 完成"
}

calc_md5() {
    local dir="$1"
    local result=""
    for i in $(seq 1 "$FILE_COUNT"); do
        result+=$(md5sum "$dir/f$i" | awk '{print $1}')
        result+=$'\n'
    done
    echo "$result"
}

notify_wechat() {
    local msg="MD5 完整性校验失败！已运行 $ROUND 轮。源路径: $DATA_DIR，目标路径: $TARGET_DIR"
    curl -s -X POST 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=9051ba90-dd37-4023-b49f-5db8ce78ac31' \
        -H 'Content-Type: application/json' \
        -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"$msg\"}}" \
        > /dev/null 2>&1
}

# 初始化：先生成一次
generate_files

while true; do
    ROUND=$((ROUND + 1))
    echo ""
    echo "===== 第 $ROUND 轮 ====="

    echo "[1/4] 计算源文件 MD5..."
    src_md5=$(calc_md5 "$DATA_DIR")
    echo "  → 完成"

    echo "[2/4] 拷贝文件到 $TARGET_DIR ..."
    mkdir -p "$TARGET_DIR"
    rm -f "$TARGET_DIR"/f*
    for i in $(seq 1 "$FILE_COUNT"); do
        cp "$DATA_DIR/f$i" "$TARGET_DIR/f$i"
    done
    echo "  → 拷贝完成"

    echo "[3/4] 计算目标文件 MD5..."
    dst_md5=$(calc_md5 "$TARGET_DIR")
    echo "  → 完成"

    echo "[4/4] 比较 MD5..."
    if [[ "$src_md5" == "$dst_md5" ]]; then
        echo "  → MD5 一致，重新生成文件进入下一轮..."
        generate_files
    else
        echo "  → MD5 不一致！"
        diff <(echo "$src_md5") <(echo "$dst_md5") | head -20
        notify_wechat
        echo "已发送企业微信通知，停止运行。"
        exit 1
    fi
done
