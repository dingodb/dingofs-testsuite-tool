# DingoFS 存储性能测试工具

DingoFS 存储性能测试工具是一个 Docker 镜像，集成了 fio、mdtest、ltp、mlperf登多种存储性能测试工具，支持通过命令行参数快速执行存储性能测试。

## 快速开始 (dingofs-testsuite-tool)

推荐使用 `dingofs-testsuite-tool` 外壳脚本，它封装了 docker 命令的复杂参数，让测试更简单。

```bash
# 1. 首次配置：设置测试目录、输出目录和镜像
dingofs-testsuite-tool config set testdir /mnt/test
dingofs-testsuite-tool config set output /tmp/results
dingofs-testsuite-tool config set image localhost/dingofs-testsuite-tools:latest

# 2. 查看当前配置
dingofs-testsuite-tool config show

# 3. 运行测试（无需指定 -m -o，使用配置的值）
dingofs-testsuite-tool -t fio -s seq_write
dingofs-testsuite-tool -t mdtest -s mdtest
dingofs-testsuite-tool -t vdbench -s vdbench
dingofs-testsuite-tool -t pjdtest -s pjdtest

# 4. 进入镜像调试
dingofs-testsuite-tool debug

# 5. 显示帮助
dingofs-testsuite-tool help
```

### dingofs-testsuite-tool 命令 (dtt)

| 命令 | 说明 |
|------|------|
| `config set testdir <dir>` | 设置测试目录（挂载点） |
| `config set output <dir>` | 设置输出目录 |
| `config set image <name>` | 设置 Docker 镜像 |
| `config show` | 显示当前配置 |
| `-t -s [-n]` | 运行测试（testdir/output 从配置读取） |
| `debug` | 进入镜像交互式调试 |
| `help` | 显示帮助信息 |

> 快捷命令：`dtt` 是 `dingofs-testsuite-tool` 的别名，两者功能相同。

> 如尚未安装 dingofs-testsuite-tool，也可直接使用 docker run 命令（见下文）。

## 安装

使用 `install.sh` 一键安装（构建镜像 + 配置环境变量 + 设置默认镜像）：

```bash
./install.sh
```

或者分步进行：

```bash
# 1. 构建镜像
docker build -t dingofs-testsuite-tools .

# 2. 将 dingofs-testsuite-tool 加入 PATH
export PATH="$PATH:/path/to/dingofs-storage-testsuite-tools"

# 3. 设置镜像
dingofs-testsuite-tool config set image localhost/dingofs-testsuite-tools:latest
```

> install.sh 参数：
> - `-n, --no-build`: 跳过镜像构建，只配置环境变量和设置镜像

## 卸载

```bash
./uninstall.sh           # 卸载并删除镜像
./uninstall.sh --keep-image  # 卸载但保留镜像
```

# 需要代理的网络环境
docker build -t dingofs-testsuite-tools \
  --build-arg http_proxy=http://10.220.69.222:1088 \
  --build-arg https_proxy=http://10.220.69.222:1088 \
  .
```

## 使用方法

```bash
docker run dingofs-testsuite-tools -t <tool> -s <scenario> -m <mount> -o <output>
```

### 容器运行模式

```bash
# 一次性测试：容器运行完测试后自动删除
docker run --rm dingofs-testsuite-tools -t mdtest -s mdtest -m /data -o /data

# 后台运行：容器在后台运行，测试结果在容器内，通过 docker stop 停止
docker run -d dingofs-testsuite-tools -t mdtest -s mdtest -m /data -o /data
docker stop <container_id>

# 交互式测试：进入容器内部，可手动执行测试命令
docker run --rm -it dingofs-testsuite-tools /bin/bash
```

### 查看帮助

```bash
# 查看所有选项和示例
docker run --rm dingofs-testsuite-tools --help
```

## 选项说明

| 选项 | 说明 |
|------|------|
| `-t, --tool` | 测试工具: fio, vdbench, mdtest |
| `-s, --scenario` | 测试场景 |
| `-m, --mount` | 被测存储的挂载点 (例如: /mnt/test) |
| `-o, --output` | 测试结果输出目录 (例如: /output) |
| `-n, --np` | mdtest MPI 进程数 (默认: 16) |
| `--mode` | 运行模式: one-shot (默认) 或 long-running |

> **注意**: `-o` 指定的是容器内路径，需要通过 `-v` 将容器内目录映射到本机路径。

## 测试工具

| 工具 | 说明 |
|------|------|
| fio | Flexible I/O tester (存储性能测试) |
| vdbench | Oracle storage testsuite |
| mdtest | MPI filesystem metadata test |
| pjdtest | POSIX 文件系统测试套件 |
| ltp | Linux Test Project (内核测试套件) |

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

## MDTEST 场景 (4 种类型，可配置并行任务数)

| 场景 | 说明 |
|------|------|
| mdtest_z0_n100 | z=0, n=100 (扁平目录, 3200 files) |
| mdtest_z5_b4_I1 | z=5, b=4, I=1 (多分支树, 32736 items) |
| mdtest_z6_b3_I1 | z=6, b=3, I=1 (中等深度树, 34976 items) |
| mdtest_z9_b2_I1 | z=9, b=2, I=1 (深层二叉树, 32736 items) |
| mdtest | 运行以上所有 4 个场景 |

> **默认进程数**: 16，可用 `-n` 或 `--np` 参数调整

## PJDTEST

pjdtest 是 POSIX 文件系统测试套件，用于验证文件系统对 POSIX 标准的兼容性。

```bash
# 运行 pjdtest 测试
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t pjdtest -s pjdtest -m /data -o /data
```

## LTP

LTP (Linux Test Project) 是 Linux 内核测试套件，用于验证内核和系统调用的正确性、稳定性和可靠性。

**注意**: LTP 测试需要 `--privileged` 标志运行，以访问 `/dev/kmsg` 等设备。

### LTP 场景

| 场景 | 说明 | 对应测试套件 |
|------|------|-------------|
| ltp | 默认运行文件系统测试 | fs |
| ltp_fs | 文件系统测试 | fs |
| ltp_dio | Direct I/O 测试 | dio |
| ltp_mm | 内存管理测试 | mm |

### 运行 LTP 测试

```bash
# 运行 LTP 文件系统测试 (需要 --privileged)
docker run --rm --privileged -v /mnt/disk0/daigy/tmp/:/data dingofs-testsuite-tools -t ltp -s ltp -m /data -o /data

# 运行特定 LTP 测试场景
docker run --rm --privileged -v /tmp/test:/data dingofs-testsuite-tools -t ltp -s ltp_fs -m /data -o /data
```

### LTP 测试限制

在容器中运行 LTP 时，部分测试会失败或报错（如 `/dev/kmsg`、`/proc/sys` 等内核接口），这是预期行为。LTP 设计用于在裸机上运行以获得完整测试结果。

## 使用示例

### FIO 测试

```bash
# 运行所有 rand_read 场景 (24 tests)
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t fio -s rand_read -m /data -o /data

# 运行所有 seq_write 场景 (24 tests)
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t fio -s seq_write -m /data -o /data

# 运行单个特定场景
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t fio -s rand_read_0d_128k_1j -m /data -o /data
```

### VDBENCH 测试

```bash
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t vdbench -s seq_rd -m /data -o /data
```

### MDTEST 测试

```bash
# 运行所有 4 个 mdtest 场景并汇总
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t mdtest -s mdtest -m /data -o /data

# 运行单个 mdtest 场景
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t mdtest -s mdtest_z0_n100 -m /data -o /data

# 自定义进程数测试 (默认 16)
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t mdtest -s mdtest -m /data -o /data -n 32
```

### PJDTEST 测试

```bash
# 运行 pjdtest 测试
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t pjdtest -s pjdtest -m /data -o /data
```

### LTP 测试

```bash
# 运行 LTP 文件系统测试 (需要 --privileged)
docker run --rm --privileged -v /tmp/test:/data dingofs-testsuite-tools -t ltp -s ltp -m /data -o /data
```

### 长期运行模式

```bash
# 启动长期运行容器
docker run --detach -v /tmp/test:/data dingofs-testsuite-tools -t fio -s rand_read -m /data -o /data --mode long-running

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
  dingofs-testsuite-tools \
  -t fio -s seq_read -m /data -o /output
```

## 输出说明

测试结果保存在输出目录中:

| 文件 | 说明 |
|------|------|
| fio.raw / fio.json | 原始输出和 JSON 格式 |
| vdbench.raw | vdbench 原始输出 |
| mdtest.raw | mdtest 原始输出 |
| pjdtest_YYYYMMDD_HHMMSS | pjdtest 测试结果 |
| ltp_YYYYMMDD_HHMMSS.log | LTP 测试日志 |
| report.html | HTML 可视化报告 |
| summary.md | Markdown 格式摘要 |
| running_result.log | 测试执行结果汇总 |

## 镜像信息

- **基础镜像**: ubuntu:24.04
- **工具版本**: fio (最新稳定版), vdbench 50406, mdtest (IOR 套件)
- **支持平台**: x86_64, ARM64
