#!/bin/bash
# elbencho 多线程综合测试（单节点版）
# 参数: <测试目录> [输出目录]
# 测试: 大文件(4M/8G) + 小文件(4K/8G), 1-64线程, 写/读/删除

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "用法: $0 <测试目录> [输出目录]"
    echo "示例: $0 /data"
    exit 1
fi

TESTDIR="$1"
OUT_DIR="${2:-/output}"
ELBENCHO=/usr/local/bin/elbencho

mkdir -p "$TESTDIR"

for THREADS in 1 4 16 64; do
    FILES=1

    echo "=== 并发=$THREADS, 大文件 4M 测试 ==="

    # 大文件写入 (4M block, 8G per file)
    $ELBENCHO --direct -w -d -t $THREADS -n 1 -N $FILES -s 8G -b 4m --lat "$TESTDIR"
    # 大文件读取
    $ELBENCHO --direct -r    -t $THREADS -n 1 -N $FILES -s 8G -b 4m --lat "$TESTDIR"
    # 删除测试数据
    $ELBENCHO -F -D -t $THREADS -n 1 -N $FILES "$TESTDIR"

    echo "=== 并发=$THREADS, 小文件 4K 测试 ==="

    # 小文件写入 (4K block, 8G/thread)
    $ELBENCHO --direct -w -d -t $THREADS -n 4 -N $FILES -s 8G -b 4k --lat "$TESTDIR"
    # 小文件读取
    $ELBENCHO --direct -r    -t $THREADS -n 4 -N $FILES -s 8G -b 4k --lat "$TESTDIR"
    # 删除测试数据
    $ELBENCHO -F -D -t $THREADS -n 4 -N $FILES "$TESTDIR"
done

echo "=== 全部测试完成 ==="
