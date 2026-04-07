# DingoFS 存储性能测试工具

DingoFS 存储性能测试工具是一个 Docker 镜像，集成了 fio、vdbench、mdtest 三种存储性能测试工具，支持通过命令行参数快速执行存储性能测试。

## 构建镜像

```bash
docker build -t dingofs-benchmark-tools .
```

## 使用方法

```bash
docker run dingofs-benchmark-tools -t <tool> -s <scenario> -m <mount> -o <output>
```

## 选项说明

| 选项 | 说明 |
|------|------|
| `-t, --tool` | 测试工具: fio, vdbench, mdtest |
| `-s, --scenario` | 测试场景 |
| `-m, --mount` | 被测存储的挂载点 (例如: /mnt/test) |
| `-o, --output` | 测试结果输出目录 (例如: /output) |
| `--mode` | 运行模式: one-shot (默认) 或 long-running |

> **注意**: `-o` 指定的是容器内路径，需要通过 `-v` 将容器内目录映射到本机路径。

## 测试工具

| 工具 | 说明 |
|------|------|
| fio | Flexible I/O tester (存储性能测试) |
| vdbench | Oracle storage benchmark |
| mdtest | MPI filesystem metadata test |

## 运行模式

| 模式 | 说明 |
|------|------|
| one-shot | 容器启动 → 运行测试 → 测试完成后容器退出 (默认) |
| long-running | 容器启动 → 运行测试 → 容器保持运行，可用 docker exec 执行更多测试 |

## FIO 场景 (4 种类型，每种 24 个子场景)

| 场景 | 说明 |
|------|------|
| rand_read | Random read (24 variants: 2 direct × 3 block size × 4 numjobs) |
| rand_write | Random write |
| seq_read | Sequential read |
| seq_write | Sequential write |

### FIO 参数说明

| 参数 | 值 |
|------|-----|
| direct | 0 (buffered), 1 (direct I/O) |
| block size | 128k, 1m, 4m |
| numjobs | 1, 8, 16, 32 |
| iodepth | 1 (fixed) |
| size | 8G per job |

## MDTEST 场景 (4 种类型，每种 32 并行任务)

| 场景 | 说明 |
|------|------|
| mdtest_z0_n100 | z=0, n=100 (扁平目录, 3200 files) |
| mdtest_z5_b4_I1 | z=5, b=4, I=1 (多分支树, 32736 items) |
| mdtest_z6_b3_I1 | z=6, b=3, I=1 (中等深度树, 34976 items) |
| mdtest_z9_b2_I1 | z=9, b=2, I=1 (深层二叉树, 32736 items) |
| mdtest | 运行以上所有 4 个场景 |

## 使用示例

### FIO 测试

```bash
# 运行所有 rand_read 场景 (24 tests)
docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t fio -s rand_read -m /data -o /data

# 运行所有 seq_write 场景 (24 tests)
docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t fio -s seq_write -m /data -o /data

# 运行单个特定场景
docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t fio -s rand_read_0d_128k_1j -m /data -o /data
```

### VDBENCH 测试

```bash
docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t vdbench -s seq_rd -m /data -o /data
```

### MDTEST 测试

```bash
# 运行所有 4 个 mdtest 场景并汇总
docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t mdtest -s mdtest -m /data -o /data

# 运行单个 mdtest 场景
docker run --rm -v /tmp/test:/data dingofs-benchmark-tools -t mdtest -s mdtest_z0_n100 -m /data -o /data
```

### 长期运行模式

```bash
# 启动长期运行容器
docker run --detach -v /tmp/test:/data dingofs-benchmark-tools -t fio -s rand_read -m /data -o /data --mode long-running

# 在运行中的容器内执行更多测试
docker exec <container_id> entrypoint.sh -t fio -s seq_write -m /data -o /data
```

### 分离挂载点和输出目录

如果需要将测试结果保存到与挂载点不同的路径，可以分别挂载：

```bash
# -m 指定被测存储的挂载点
# -o 指定结果输出目录（需要额外挂载）
docker run --rm \
  -v /mnt/disk1/test:/data \
  -v /tmp/results:/output \
  dingofs-benchmark-tools \
  -t fio -s seq_read -m /data -o /output
```

## 输出说明

测试结果保存在输出目录中:

| 文件 | 说明 |
|------|------|
| fio.raw / fio.json | 原始输出和 JSON 格式 |
| vdbench.raw | vdbench 原始输出 |
| mdtest.raw | mdtest 原始输出 |
| report.html | HTML 可视化报告 |
| summary.md | Markdown 格式摘要 |

## 镜像信息

- **基础镜像**: ubuntu:24.04
- **工具版本**: fio (最新稳定版), vdbench 50406, mdtest (IOR 套件)
- **支持平台**: x86_64, ARM64
