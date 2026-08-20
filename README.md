# DingoFS 存储性能测试工具

DingoFS 存储性能测试工具是一个 Docker 镜像，集成了 fio、vdbench、mdtest、pjdtest、ltp、mlperf 等多种存储性能测试工具，支持通过命令行参数快速执行存储性能测试。

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
dingofs-testsuite-tool -t vdbench -s seq_rd
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
| `config set custom <dir>` | 设置自定义场景目录 |
| `config show` | 显示当前配置 |
| `-t <tool> -s <scenario>` | 运行指定工具和场景 |
| `daily [选项]` | 每日集成测试（10+ 模块） |
| `smoke [选项]` | 冒烟测试 |
| `debug` | 进入镜像交互式调试 |
| `help` | 显示帮助信息 |

> 快捷命令：`dtt` 是 `dingofs-testsuite-tool` 的别名，两者功能相同。

## 测试工具总览

`dtt -t` 支持以下 7 种测试工具：

| 工具 | 说明 | 必填参数 | 可选参数 |
|------|------|---------|---------|
| `fio` | Flexible I/O 存储性能测试 | `-s <场景>` | `--bs_size` |
| `vdbench` | Oracle 存储性能测试 | `-s <场景>` | — |
| `mdtest` | MPI 文件系统元数据测试 | `-n <进程数>` | `-s <场景>`（默认 all） |
| `pjdtest` | POSIX 文件系统一致性测试 | `-s <场景>` | — |
| `ltp` | Linux Test Project 内核测试 | `-s <场景>` | — |
| `int` | DingoFS 集成测试 | `-s <场景>` | — |
| `mlperf` | MLPerf Storage 基准测试 | `-s <场景>` | `--scale`, `--gpu_count`, `--file_count` |

### 通用可选参数

| 参数 | 说明 |
|------|------|
| `--debug` | 调试模式，保留容器不删除 |
| `--wechat` | 启用企业微信通知 |
| `--email <地址>` | 邮件通知地址 |
| `--bs_size <类型>` | fio 块大小类型: normal (128K/1M/4M), small (128B-8K) |
| `--test_times <次数>` | fio perf 重复次数 |

---

## 1. FIO — 存储 I/O 性能测试

FIO (Flexible I/O Tester) 是最常用的存储性能基准测试工具，支持多种 I/O 模式、块大小和并发配置。

### 场景

| 场景 | 说明 |
|------|------|
| `seq_read` | 顺序读（24 个子场景） |
| `seq_write` | 顺序写（24 个子场景） |
| `rand_read` | 随机读（24 个子场景） |
| `rand_write` | 随机写（24 个子场景） |
| `all` | 运行以上所有场景 |
| `custom` | 从 `config custom` 目录加载自定义 `.fio` 文件 |

### 场景命名规则

单个场景命名格式: `<模式>_<direct>_<块大小>_<并发数>`，例如 `rand_read_0d_128k_1j`。

| 参数 | 值 |
|------|-----|
| direct | 0d (buffered), 1d (direct I/O) |
| block size | 128k, 1m, 4m |
| numjobs | 1j, 8j, 16j, 32j |
| iodepth | 1 (固定) |
| size | 8G per job |

### 使用示例

```bash
# 运行顺序写（使用 dtt 配置的 testdir/output）
dtt -t fio -s seq_write

# 运行所有 fio 场景（使用小块大小 128B-8K）
dtt -t fio -s all --bs_size small

# 运行单个场景
dtt -t fio -s rand_read_0d_128k_1j

# 自定义场景（从 ~/my_scenarios/ 加载）
dtt config set custom ~/my_scenarios
dtt -t fio -s my_test       # → /custom/my_test.fio

# 直接 docker 运行
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t fio -s seq_write -m /data -o /data
```

---

## 2. VDBENCH — Oracle 存储性能测试

VDBench 是 Oracle 的存储性能测试工具，支持多种 I/O 模式和配置。

### 场景

| 场景 | 说明 |
|------|------|
| `seq_rd` | 顺序读 (.par 参数文件) |
| `seq_wr` | 顺序写 |
| `rand_rd` | 随机读 |
| `rand_wr` | 随机写 |
| `custom` | 从 `config custom` 目录加载自定义 `.vdbench` 文件 |

### 使用示例

```bash
# 运行顺序读
dtt -t vdbench -s seq_rd

# 运行随机写
dtt -t vdbench -s rand_wr

# 自定义场景
dtt -t vdbench -s custom

# 直接 docker 运行
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t vdbench -s seq_rd -m /data -o /data
```

---

## 3. MDTEST — 元数据性能测试

MDTEST 是 MPI 并行文件系统元数据性能测试工具，用于测量文件和目录的创建、删除、stat 等元数据操作的性能。

### 场景

| 场景 | 说明 |
|------|------|
| `mdtest_z0_n100` | z=0, n=100 (扁平目录, 3200 files) |
| `mdtest_z5_b4_I1` | z=5, b=4, I=1 (多分支树, 32736 items) |
| `mdtest_z6_b3_I1` | z=6, b=3, I=1 (中等深度树, 34976 items) |
| `mdtest_z9_b2_I1` | z=9, b=2, I=1 (深层二叉树, 32736 items) |
| `mdtest` / `all` | 运行以上所有 4 个场景（默认） |

### 使用示例

```bash
# 运行所有场景（16 进程，默认）
dtt -t mdtest -n 16

# 运行所有场景（自定义进程数）
dtt -t mdtest -s all -n 32

# 运行单个场景
dtt -t mdtest -s mdtest_z0_n100 -n 8

# 直接 docker 运行
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t mdtest -s mdtest -m /data -o /data -n 16
```

---

## 4. PJDTEST — POSIX 文件系统测试

PJDTEST 是 POSIX 文件系统一致性测试套件，用于验证文件系统对 POSIX 标准的兼容性。

### 使用示例

```bash
# 运行 pjdtest
dtt -t pjdtest -s pjdtest

# 直接 docker 运行
docker run --rm -v /tmp/test:/data dingofs-testsuite-tools -t pjdtest -s pjdtest -m /data -o /data
```

---

## 5. LTP — Linux Test Project

LTP (Linux Test Project) 是 Linux 内核测试套件，用于验证内核和系统调用的正确性、稳定性和可靠性。

**注意**: LTP 需要 `--privileged`，部分测试需要 `/dev/kmsg` 等内核接口。容器内运行 LTP 时部分测试会失败，这是预期行为。LTP 设计用于在裸机上运行以获得完整测试结果。

### 场景

| 场景 | 说明 | 对应测试套件 |
|------|------|-------------|
| `ltp` | 默认文件系统测试 | fs |
| `ltp_fs` | 文件系统测试 | fs |
| `ltp_dio` | Direct I/O 测试 | dio |
| `ltp_mm` | 内存管理测试 | mm |

### 使用示例

```bash
# 运行 LTP 文件系统测试
dtt -t ltp -s ltp

# 运行 Direct I/O 测试
dtt -t ltp -s ltp_dio

# 直接 docker 运行
docker run --rm --privileged -v /tmp/test:/data dingofs-testsuite-tools -t ltp -s ltp -m /data -o /data
```

---

## 6. INT — DingoFS 集成测试

通过集成测试框架 `run_tests.py` 运行单个模块的测试用例。使用 `config set int_env` 指定环境名，然后通过 `-s` 指定模块名。

### 选项

| 选项 | 说明 |
|------|------|
| `--env <环境名>` | 测试环境（**必填**，对应 `conf/env/<name>.yaml`） |
| `--int-report-port <端口>` | Allure 报告 HTTP 服务端口（默认: 8800） |

### 报告

每次运行后 Allure 报告自动保存到 output/int_allure_report/，结构：

```
int_allure_report/
├── index.html                    # 报告索引页
├── allure-report-latest/         # 最新报告
├── allure-report-history/        # 历史报告
└── allure-results/               # 原始结果
```

完成后自动在指定端口启动 HTTP 服务，可直接访问报告。

### 使用示例

```bash
# 指定环境和模块
dtt -t int -s quota --env env_126_quota
dtt -t int -s mds_manage --env env_126_mds_manage

# 自定义报告端口
dtt -t int -s quota --env env_126_quota --int-report-port 8890

# 可用的模块：quota, client, cache_node, fault, mount_subdir,
#             basic_file_operation, metadata_consistency, trash,
#             dirstat, mds_manage, hot_upgrade, warmup, xattr
```

---

## 7. MLPERF — MLPerf Storage 基准测试

MLPerf Storage 是 ML 训练场景的存储基准测试，模拟真实 ML 工作负载的 I/O 模式。

### 场景

| 场景 | 说明 |
|------|------|
| `resnet50` | ResNet-50 图像分类模型 |
| `unet3d` | 3D U-Net 医学图像分割模型 |
| `cosmoflow` | CosmoFlow 宇宙学模拟模型 |
| `checkpointing` | 检查点读写测试 |
| `all` | 运行以上所有场景 |

### 专用参数

| 参数 | 说明 | 可选值 |
|------|------|-------|
| `--scale <规模>` | 测试规模 | small (32 files/5 epochs), medium (256 files/10 epochs), large (1024 files/20 epochs) |
| `--gpu_count <数量>` | 并发 GPU 数量 | 正整数（默认: 1） |
| `--file_count <数量>` | 自定义生成测试文件数量 | 正整数 |

### 使用示例

```bash
# 运行所有 mlperf 场景（默认 small/1 GPU）
dtt -t mlperf -s all

# 运行指定场景
dtt -t mlperf -s resnet50

# 指定规模和 GPU 数量
dtt -t mlperf -s unet3d --scale medium --gpu_count 4

# 自定义文件数量
dtt -t mlperf -s cosmoflow --file_count 500

# 运行 checkpointing
dtt -t mlperf -s checkpointing --scale small

# 显示 mlperf 详细帮助
dtt -t mlperf --help
```

### 注意事项

- mlperf 已集成到 dtt 主镜像中，与其他工具共用同一个容器
- 自动设置 `--shm-size=8g` 和 `-it` 模式
- 测试结果保存在 output 目录的 `mlperf_<timestamp>/` 子目录中

---

## 8. XFSTESTS — 文件系统回归测试

xfstests 是 Linux 文件系统回归测试套件。容器内通过 mount helper 自动挂载 DingoFS，无需预先挂载。

### 模式

| 模式 | 说明 | 配置 |
|------|------|------|
| 本地模式 | 零依赖，自动创建文件系统，数据存储在容器内 | 默认，无需配置 |
| MDS 模式 | 连接到 DingoFS 集群，数据存储在远端 | 配置 `xfstest_mds_template` |

### MDS 模式配置

```bash
# 1. 先在集群上创建两个文件系统（一次性）
dingo fs create xftest --mdsaddr <MDS_ADDR> ...
dingo fs create xfscratch --mdsaddr <MDS_ADDR> ...

# 2. 配置 MDS 模板
dtt config set xfstest_mds_template 'mds://<MDS_ADDR>/{fsname}'

# 3. 运行测试
dtt -t xfstest -s generic/001
```

> `{fsname}` 会被自动替换为 `xftest` 或 `xfscratch`。

### 测试组

| 组 | 用例数 | 说明 |
|----|--------|------|
| `generic` | 1599 | POSIX 通用文件系统测试（DingoFS 主要测试组） |
| `xfs` | 1623 | XFS 专项（不适用 FUSE） |
| `btrfs` | 700 | Btrfs 专项（不适用 FUSE） |
| `overlay` | 212 | Overlay 文件系统测试 |
| `ext4` | 145 | Ext4 专项（不适用 FUSE） |
| `f2fs` | 50 | F2FS 专项（不适用 FUSE） |
| `selftest` | 16 | 框架自检测试 |
| `perf` | 2 | 性能测试 |
| `ceph` | 12 | Ceph 专项 |
| `nfs/cifs/ocfs2/tmpfs/udf` | <10 | 其他专项 |

### 场景

| 场景 | 说明 |
|------|------|
| `auto` / `all` | 运行 auto 组（文件系统自检测试，默认） |
| `quick` | 快速冒烟测试 |
| `generic/NNN` | 运行指定编号的 generic 测试 |
| `<group>/NNN` | 运行指定测试组中的测试 |

### 指定外部 dingo-client

默认使用镜像内置的 dingo-client。如需测试自编译版本：

```bash
dtt -t xfstest -s generic/001 --dingo-client /path/to/dingo-client
```

### 使用示例

```bash
# 本地模式（默认）
dtt -t xfstest -s auto                    # 运行全部
dtt -t xfstest -s quick                   # 快速冒烟
dtt -t xfstest -s generic/001             # 单个测试
dtt -t xfstest -s generic/001 --dingo-client ./build/bin/dingo-client

# MDS 模式
dtt config set xfstest_mds_template 'mds://172.30.14.126:6900/{fsname}'
dtt -t xfstest -s generic/001
```

### 结果

测试结果保存在 output 目录的 `xfstest_<timestamp>/` 子目录中：

| 文件/目录 | 说明 |
|-----------|------|
| `check.log` | 完整测试执行日志 |
| `generic/` | 各测试用例输出（`.out` 预期、`.bad` 差异） |

---

## daily — 每日集成测试

`dtt daily` 在容器内执行 `run_tests.py`，依次运行 12 个测试模块，每个失败用例重试 2 次，完成后生成 Allure 报告并发送邮件/微信通知。

### 模块列表

| # | 模块 | 环境（默认 env=126） |
|---|------|----------------------|
| 1 | `quota` | `env_126_quota` |
| 2 | `basic_file_operation` | `env_126_smoke` |
| 3 | `mount_subdir` | `env_126_mount_subdir` |
| 4 | `trash` | `env_126_trash` |
| 5 | `dirstat` | `env_126_dirstat` |
| 6 | `hot_upgrade` | `env_126_hotupgrade_multi` |
| 7 | `xattr` | `env_126_xattr` |
| 8 | `warmup` | `env_126_warmup` |
| 9 | `client` | `env_40_dingofs` |
| 10 | `cache_node` | `env_40_dingofs` |
| 11 | `fault` | `env_79_dingofs` |
| 12 | `mds_manage` | `env_126_mds_manage` |

> 调试模式 (`--debug`) 仅运行 `client` 模块。
>
> `fault` 会启用 external chaos 和高风险故障，并将宿主机 `$HOME/.ssh/rocky_70` 只读挂载到容器；执行前必须确保该私钥文件存在。

### 使用示例

```bash
# 默认环境 126，不发送通知
dtt daily

# 发送邮件和微信通知
dtt daily --email daigy@zetyun.com --wechat

# 每日模式：报告存入 daily 历史目录，指定报告端口
dtt daily --daily --report-port 8889

# 指定报告输出路径
dtt daily --report-path /mnt/disk5/daigy/tmp/output

# 调试模式（仅跑 client 模块，保留容器）
dtt daily --debug

# 多个邮件收件人
dtt daily --email daigy@zetyun.com,sunxiao@zetyun.com --wechat
```

### 选项

| 选项 | 说明 |
|------|------|
| `--env <编号>` | 环境编号（默认: 126） |
| `--email <地址>` | 邮件收件人，逗号分隔多个 |
| `--wechat` | 启用企业微信通知 |
| `--daily` | 每日模式（Allure 报告存入 `allure-daily-report-*`） |
| `--report-port <端口>` | Allure 报告 HTTP 服务端口 |
| `--report-path <路径>` | Allure 报告及日志输出路径 |
| `--debug` | 调试模式（仅跑 client，保留容器） |

### 报告访问

测试完成后，通过 HTTP 访问 Allure 报告：

```
http://<宿主机IP>:<report-port>/allure-daily-report-latest/index.html
```

日志文件保存在 output 目录下（通过 `dtt config set output` 配置）。

---

## smoke — 冒烟测试

快速验证基本功能是否正常。

```bash
# 运行完整冒烟测试
dtt config set xfstest_mds_template 'mds://<MDS_ADDR>/{fsname}'
dtt smoke

# 排除指定工具
dtt smoke --exclude int
dtt smoke --exclude pjdtest,xfstest
dtt smoke --exclude xfstest
```

启用 pjdtest、LTP、xfstest 中任一工具测试时，`dtt smoke` 会先执行
`dtt --setup-env env_126_tool`，并使用生成后写回配置的 `testdir` 运行
pjdtest all、LTP smoketest 和 xfstest quick；setup 失败时不会启动 smoke
容器。三个工具均被排除时不会执行该 setup。xfstest 仍使用
`xfstest_mds_template` 指向的 DingoFS TEST/SCRATCH 文件系统；未配置时该项
明确失败，不会回退到本地文件模式。

随后按 fail-continue 模式执行以下集成测试，所有调用均使用 `--reruns 2`：

| 模块 | 范围 | 环境 |
|---|---|---|
| quota | 仅 `verify_fs_capacity.yaml`、`verify_fs_quota.yaml` | `env_126_quota` |
| basic_file_operation | 全部用例 | `env_126_smoke` |
| client | `--run-level smoke` | `env_40_dingofs` |
| cache_node | `--run-level smoke` | `env_40_dingofs` |
| dirstat | `testcases/dirstat_test_cases/smoke` | `env_126_dirstat` |
| hot_upgrade | `testcases/hot_upgrade_test_cases/smoke` | `env_126_hotupgrade_multi` |
| mds_manage | `testcases/mds_manage_test_cases/smoke` | `env_126_mds_manage` |
| mount_subdir | 仅 `verify_mount_subdir.yaml` | `env_126_mount_subdir` |
| trash | `testcases/trash_test_cases/smoke` | `env_126_trash` |
| warmup | `testcases/warmup_test_cases/smoke` | `env_126_warmup` |
| xattr | `testcases/xattr_test_cases/smoke` | `env_126_xattr` |

任一阶段失败不会阻止后续阶段，最终 JSON、文本和通知汇总会包含全部阶段。
`--exclude int` 可排除全部集成测试，也可以用 `int_<模块名>` 排除单个模块。

---

## deploy — 部署运维工具

`dtt deploy bin_tool` 将内嵌的运维脚本部署到目标用户的 `~/bin/` 目录，方便在集群节点上直接使用。

### 用法

```bash
dtt deploy bin_tool --user <用户> --mds <MDS地址> --dingo-path <dingo路径>
```

### 参数

| 参数 | 说明 |
|------|------|
| `--user <用户>` | 目标用户（必填），脚本部署到 `/home/<用户>/bin/` |
| `--mds <地址>` | MDS 地址（必填），支持逗号分隔多个 |
| `--dingo-path <路径>` | dingo 二进制路径（必填） |

### 示例

```bash
dtt deploy bin_tool --user dingofs --mds 100.64.0.5:16920 --dingo-path /usr/local/bin/dingo
```

### 部署的工具列表（18 个）

部署后需将工具目录加入 PATH：`export PATH="/home/<用户>/bin:$PATH"`

---

#### 文件系统管理

**`mdscreatefs`** — 创建文件系统（支持 rados/s3 存储后端，回收站参数）

```bash
mdscreatefs <fs_name> [trash_days] [immediate_trash_quota] [enable_dir_stats] [store_type]
mdscreatefs trash-test-1                              # 全部默认 (rados, trash_days=1)
mdscreatefs trash-test-1 7 false                       # trash_days=7, quota=false
mdscreatefs trash-test-1 1 true false s3               # S3 后端, 关闭 dir_stats
```

**`deletefs`** — 删除指定文件系统

```bash
deletefs <fsname>
deletefs trash-test-1
```

**`deletefsall`** — 删除所有文件系统（支持按名称过滤）

```bash
deletefsall [filter]
deletefsall                                # 删除全部
deletefsall trash                          # 只删除名称含 "trash" 的
```

**`listfs`** — 列出所有文件系统（名称 + 状态 + ID）

```bash
listfs
```

**`mountfs`** — 挂载文件系统到客户端目录

```bash
mountfs <fsname> <父目录> [cachename]
mountfs trash-test-1 /mnt/disk0/dingofs-autotest/client              # 无缓存挂载
mountfs trash-test-1 /mnt/disk0/dingofs-autotest/client mlperf_cache  # 指定缓存组
```

**`umountall`** — 卸载指定目录下的所有 DingoFS 挂载

```bash
umountall <目录>
umountall /mnt/disk0/dingofs-autotest/client
```

---

#### 缓存管理

**`createcache`** — 创建远程缓存节点组

```bash
createcache <cachename> <cachesize_mb> [cache_eviction]
createcache mlperf_cache 102400                        # 100GB 缓存
createcache mlperf_cache 102400 2random                # 2-random 驱逐策略
```

**`deletecache`** — 删除所有远程缓存节点组（按名称前缀过滤）

```bash
deletecache [filter]
deletecache                                # 删除全部
deletecache mlperf                         # 只删除名称含 "mlperf" 的
```

**`listcache`** — 列出所有远程缓存节点组

```bash
listcache
```

**`listgroup`** — 列出所有集群组信息

```bash
listgroup
```

**`killcache`** — 终止所有远程缓存节点进程

```bash
killcache
```

---

#### 配额管理

**`quotaget`** — 查询文件系统/目录配额

```bash
quotaget <fsname> [path]
quotaget trash-test-1          # 列出所有配额
quotaget trash-test-1 /        # 查询根目录配额
```

**`quotaset`** — 设置文件系统/目录配额

```bash
quotaset <fsname> <path> [capacity] [inodes]
quotaset trash-test-1 /                # 默认: capacity=10GiB, inodes=10
quotaset trash-test-1 / 5GiB           # capacity=5GiB, inodes=10
quotaset trash-test-1 / 5GiB 200       # capacity=5GiB, inodes=200
```

---

#### 目录统计（dirstat）

**`dirstat`** — 目录统计信息管理（info / enable / sync / summary）

```bash
# 查询目录统计
dirstat info <fs_name> <path> [--recursive] [--raw] [--strict]
dirstat info trash-test-1 /                          # 查询根目录
dirstat info trash-test-1 /subdir --recursive        # 递归查询

# 启用/禁用目录统计
dirstat enable <fs_name> <true|false>
dirstat enable trash-test-1 true

# 同步统计信息
dirstat sync <fs_name> <path> [--recursive] [--repair]
dirstat sync trash-test-1 / --recursive

# 汇总输出
dirstat summary <fs_name> <path> [--depth N] [--entries N] [--strict]
```

---

#### 回收站

**`edittrashdays`** — 修改文件系统回收站保留天数

```bash
edittrashdays <fsname> <trash_days>
edittrashdays trash-test-1 7
```

**`restoretrash`** — 从回收站恢复文件（按小时 bucket）

```bash
restoretrash <fs_name> <hours_bucket> <put_back>
restoretrash test1 2026-06-17-02 false
```

---

#### 运维工具

**`killclient`** — 终止指定文件系统对应的客户端进程

```bash
killclient <fsname>
killclient trash-test-1
```

**`updatebin`** — 从容器中更新 dingo 二进制文件到当前节点

```bash
updatebin <容器ID>
updatebin c14c794c5bbf
```

---

## cluster — 集群管理

`dtt cluster` 管理 DingoFS 集群的更新和状态查询。

### 用法

```bash
dtt cluster <update|status> <参数...>
```

### 子命令

| 子命令 | 说明 |
|--------|------|
| `status` | 查看集群状态 |
| `update` | 更新集群到最新 DingoFS 镜像 |

---

### cluster status — 查看集群状态

```bash
dtt cluster status <cluster_id> <user>
```

| 参数 | 说明 |
|------|------|
| `cluster_id` | 集群 ID（当前仅支持 29） |
| `user` | 部署用户（root 或其他） |

```bash
dtt cluster status 29 root
```

---

### cluster update — 更新集群

从 Docker Hub 拉取最新（或指定）镜像，更新 topology 配置，提交配置，执行 cluster stop → clean → deploy 完成滚动更新。

```bash
dtt cluster update <cluster_id> <user> [image_tag] [-f <topology_file>]
```

| 参数 | 说明 |
|------|------|
| `cluster_id` | 集群 ID（当前仅支持 29） |
| `user` | 部署用户，用于定位 topology 文件路径 |
| `image_tag` | （可选）指定镜像 tag，不传则自动获取 latest |
| `-f, --file` | （可选）覆盖 topology YAML 文件路径 |

**更新流程（6 步）：**

1. 获取镜像 tag（自动获取 latest 或使用指定的 tag）
2. 备份 topology YAML，更新 `container_image`
3. 提交集群配置 (`config commit`)
4. 停止所有服务 (`cluster stop`)
5. 清理旧数据 (`cluster clean`)
6. 部署新服务 (`cluster deploy`)

> 如果 latest 镜像拉取失败（630001 错误），自动回退到 previous 镜像重试一次。

**使用示例：**

```bash
# 更新到最新镜像（自动获取 tag）
dtt cluster update 29 root

# 指定镜像 tag
dtt cluster update 29 root 8120cfb

# 指定 topology 文件
dtt cluster update 29 root -f /custom/topology.yaml
```

---

## 安装

使用 `install.sh` 一键安装（构建镜像 + 配置环境变量 + 设置默认镜像）：

```bash
./install.sh
```

或者分步进行：

```bash
# 1. 构建本地镜像（构建前自动覆盖同步 dingofs-chaos-tool）
DINGOFS_CHAOS_TOOL_SRC=/home/jenkins/dgy/github/dingofs-chaos-tool ./build.sh --debug

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

## 需要代理的网络环境

```bash
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

# 查看特定工具帮助
dtt -t mlperf --help
dtt -t fio --help
```

## 选项说明

| 选项 | 说明 |
|------|------|
| `-t, --tool` | 测试工具: fio, vdbench, mdtest, pjdtest, ltp, int, mlperf |
| `-s, --scenario` | 测试场景 |
| `-m, --mount` | 被测存储的挂载点 (例如: /mnt/test) |
| `-o, --output` | 测试结果输出目录 (例如: /output) |
| `-n, --np` | mdtest MPI 进程数 (默认: 16) |

---

## 输出说明

测试结果保存在输出目录中:

| 文件 | 说明 |
|------|------|
| fio.raw / fio.json | 原始输出和 JSON 格式 |
| vdbench.raw | vdbench 原始输出 |
| mdtest.raw | mdtest 原始输出 |
| pjdtest_YYYYMMDD_HHMMSS | pjdtest 测试结果 |
| ltp_YYYYMMDD_HHMMSS.log | LTP 测试日志 |
| allure-report-latest/ | Allure HTML 报告（集成测试） |
| index.html | 报告索引页 |
| running_result.log | 测试执行结果汇总 |

## 镜像信息

- **基础镜像**: ubuntu:24.04
- **工具版本**: fio (最新稳定版), vdbench 50406, mdtest (IOR 套件), allure 2.32.0
- **支持平台**: x86_64, ARM64
