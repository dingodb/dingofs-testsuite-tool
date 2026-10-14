# AI Storage 单客户端性能场景

面向各类文件存储系统，实现单客户端的数据供给、checkpoint 和权重读取场景。fio 与 elbencho 均支持小文件读、写。L02 多客户端和 X01 混合协调不在本次范围。

使用目标存储上已经挂载的独立性能测试目录。程序不会创建文件系统、执行挂载、修改 QoS、清除缓存或连接其他客户端。mdtest 的 MPI ranks 固定运行在 localhost。

## 入口与场景

镜像需要包含本次更新的 `/scripts/ai_storage_scenarios.py` 和 entrypoint；宿主机 `dtt` 包装脚本也需更新。已有 Dockerfile 会将 scripts 自动复制到镜像。也可以在安装了对应工具的测试机上直接运行 Python 脚本。

所有 AI Storage 调参使用 `--ai-storage-*` 前缀，避免与普通场景中“每 job 大小”“每线程文件数”的参数含义混淆。普通场景及 `-s all` 不会额外运行这些大数据量场景。

| 工具 | 场景名 | 默认工作集 | 测量操作 |
|---|---|---|---|
| fio | `ai-storage-b01-read` | 单客户端合计 256GiB，4 jobs 分摊 | 完整顺序读取 |
| fio | `ai-storage-b01-write` | 单客户端合计 256GiB，4 jobs 分摊 | 预填充后完整覆盖写 |
| fio | `ai-storage-t02-read` | 单客户端合计 256GiB，4 jobs 分摊 | 64KiB 随机读，预热 30 秒、测量 600 秒 |
| fio | `ai-storage-t03-read` | 每档 100,000 文件，默认遍历 19 种组合 | 完整读取已有文件 |
| fio | `ai-storage-t03-write` | 每档 100,000 文件，默认遍历 19 种组合 | 完整覆盖写已有文件 |
| elbencho | `ai-storage-t01-read` | 1TiB，1,024 个 1GiB shard | 完整顺序读取 |
| elbencho | `ai-storage-t03-read` | 每档 100,000 文件，默认遍历 19 种组合 | 打开、完整读取、关闭 |
| elbencho | `ai-storage-t03-write` | 每轮 每档 100,000 文件，默认遍历 19 种组合 | 新目录中创建、完整写入、关闭 |
| elbencho | `ai-storage-l01-read` | 64GiB，16 个 4GiB shard | 整个权重集完整读取 |
| mdtest | `ai-storage-t03` | 100,000 个空文件，默认 1 rank | 分别运行 create、stat、remove |
| fio | `ai-storage-c01` | 每轮合计 64GiB，4 jobs 分摊 | 三轮新 checkpoint：写入、回读、独立 CRC 校验 |

小文件场景不指定 `--ai-storage-file-size/--ai-storage-bs` 时，默认顺序运行下表全部 19 种组合。每个组合默认测量 3 轮。C01 固定三轮，其余可调整。有限数据集没有 time_based/ramp_time；T02 才使用持续随机读取。此版本不提供长稳、混合读写或 B01 持续覆盖模式。

## 先预览

```bash
dtt -t fio -s ai-storage-t03-read \
  -m /mnt/storage/performance -o /tmp/ai-storage-results \
  --ai-storage-file-size 256K --ai-storage-file-count 100000 \
  --ai-storage-bs 64K --ai-storage-jobs 4 --ai-storage-dry-run
```

预览输出完整命令、fio 配置、数据目录、总字节数、峰值逻辑占用和各阶段，不启动存储工具。删除 `--ai-storage-dry-run` 即执行。

不使用容器时，去掉参数前缀中的 `ai-storage-`：

```bash
python3 scripts/ai_storage_scenarios.py --tool fio --scenario ai-storage-t03-read \
  --mount /mnt/storage/performance --output /tmp/ai-storage-results \
  --file-size 256K --file-count 100000 --bs 64K --jobs 4 --dry-run
```

## fio 和 elbencho 小文件读写

默认一次运行全部 19 种组合（每组 3 轮）：

```bash
dtt -t fio -s ai-storage-t03-read
dtt -t fio -s ai-storage-t03-write
dtt -t elbencho -s ai-storage-t03-read
dtt -t elbencho -s ai-storage-t03-write
```

只跑 1MiB 文件的 5 个 block_size 档位：

```bash
dtt -t fio -s ai-storage-t03-read --ai-storage-file-size 1M
```

只跑 64KiB block_size 对应的 4 个文件大小：

```bash
dtt -t elbencho -s ai-storage-t03-write --ai-storage-bs 64K
```

例如先选 256KiB 文件、64KiB 请求作为代表组，以下四个命令分别测量：

```bash
dtt -t fio -s ai-storage-t03-read --ai-storage-file-size 256K --ai-storage-bs 64K --ai-storage-jobs 4
dtt -t fio -s ai-storage-t03-write --ai-storage-file-size 256K --ai-storage-bs 64K --ai-storage-jobs 4
dtt -t elbencho -s ai-storage-t03-read --ai-storage-file-size 256K --ai-storage-bs 64K --ai-storage-threads 4
dtt -t elbencho -s ai-storage-t03-write --ai-storage-file-size 256K --ai-storage-bs 64K --ai-storage-threads 4
```

这些命令使用 `dtt config` 中的挂载点和输出目录；也可以显式加 `-m/-o`。

默认遍历以下 19 种文件大小/block_size 组合；并发、队列深度、direct 固定，不展开其他参数维度。只指定 `--ai-storage-file-size` 时运行该大小的全部块档位；只指定 `--ai-storage-bs` 时运行支持该块大小的文件档位；同时指定两者时只运行一个组合：

| 单文件大小 | 请求块档位 | 100,000 文件的逻辑容量 |
|---|---|---|
| 4K | 4K | 0.381GiB |
| 64K | 4K、16K、64K | 6.10GiB |
| 256K | 4K、16K、64K、256K | 24.41GiB |
| 1M | 4K、16K、64K、256K、1M | 97.66GiB |
| 10M | 4K、16K、64K、256K、1M、2M | 976.56GiB |

文件数是十进制 100,000，必须能整除 fio jobs 或 elbencho threads。fio 每个 job 分配独立文件名，限制同时打开文件数为 1，按文件顺序完整访问。elbencho 每线程一个目录，单目录文件数为总文件数除以线程数。fio I/O 延迟不能当作完整文件加载延迟。

elbencho 创建写的每轮使用新目录，默认保留三轮数据；10MiB 档需要约 2.86TiB 逻辑空间。同时指定文件大小与块大小的单组合命令保留数据，重复启动会累积占用。默认矩阵或单参数筛选矩阵在成功完成组合后回收本次新建数据：读取/覆盖写在同一文件大小的最后一个块档位之后回收，elbencho 创建写在每个组合之后回收。失败时保留当前现场并停止。`prepare/measure` 模式保留数据。数据归档后按报告中的明确目录自行回收，不删除整个挂载点。

## 其他单客户端场景

```bash
# B01：总共 256GiB，不是每 job 256GiB；分别选择 read/write
dtt -t fio -s ai-storage-b01-read --ai-storage-dataset-size 256G --ai-storage-jobs 8 --ai-storage-bs 1M
dtt -t fio -s ai-storage-b01-write --ai-storage-dataset-size 256G --ai-storage-jobs 8 --ai-storage-bs 1M

# T02：固定 4 jobs 比较 depth 1、8、32，主测块大小 64K、256K、1M
dtt -t fio -s ai-storage-t02-read --ai-storage-jobs 4 --ai-storage-iodepth 8 \
  --ai-storage-bs 256K --ai-storage-runtime 600 --ai-storage-ramp-time 30

# T01：总共 1TiB；线程可选 1、4、8、16
dtt -t elbencho -s ai-storage-t01-read --ai-storage-threads 4 --ai-storage-bs 1M

# L01：权重集可选 16G、64G、256G；线程 1、4、8；direct 和 buffered 分组
dtt -t elbencho -s ai-storage-l01-read --ai-storage-dataset-size 64G \
  --ai-storage-threads 8 --ai-storage-direct 1 --ai-storage-bs 1M

# mdtest：总文件数不随 ranks 增长；比较 1、8、32 ranks 和两种目录布局
dtt -t mdtest -s ai-storage-t03 --ai-storage-jobs 8 --ai-storage-layout unique
dtt -t mdtest -s ai-storage-t03 --ai-storage-jobs 8 --ai-storage-layout shared

# C01：三轮独立目录，每轮 64GiB 或 256GiB，默认 buffered + end_fsync
dtt -t fio -s ai-storage-c01 --ai-storage-dataset-size 64G --ai-storage-jobs 4 --ai-storage-direct 0
```

mdtest 共享目录仍使用不同文件名，绝不使用共享同一文件的 `-S`。C01 的读回与 CRC 校验分开执行；写入需要生成 CRC 头，其 CPU 开销属于该负载。校验阶段不纳入性能统计。它验证合成文件内容，不证明训练状态可恢复。C01 保留三轮，对应 192GiB 或 768GiB。

## 分离预填充、复用读取数据

默认 `all` 先预填充再测量，准备结果不计入性能。准备阶段必须实际完成全量写入，随后检查文件数和大小；不会用 truncate 代替写入。大文件/小文件读取与 fio 覆盖写可以分两步运行：

```bash
DATA_ID="t03-$(date +%Y%m%d-%H%M%S)"
dtt -t fio -s ai-storage-t03-read --ai-storage-data-id "$DATA_ID" \
  --ai-storage-file-size 256K --ai-storage-bs 64K --ai-storage-jobs 4 --ai-storage-phase prepare

dtt -t fio -s ai-storage-t03-read --ai-storage-data-id "$DATA_ID" \
  --ai-storage-file-size 256K --ai-storage-bs 16K --ai-storage-jobs 4 --ai-storage-phase measure
```

矩阵模式也支持 `prepare/measure`：使用相同的基础 `--ai-storage-data-id` 和筛选参数即可。矩阵 prepare 每种文件大小仅准备一次；measure 按组合测量。矩阵子数据 ID 在基础 ID 后附加文件大小，见 matrix-plan.json；若改为同时指定大小和块的单组合命令，需要使用其中对应的子数据 ID。

挂载点、工具、数据量、文件数、文件大小和并发保持一致；读取块大小、direct 可以改变。只有本工具成功写入并生成 manifest 的数据才能复用，缺失文件会拒绝测量。`all/prepare` 遇到同名数据根目录会报错，不覆盖旧文件。C01、mdtest 和 elbencho 创建写必须使用 `all`。

## 输出与结果解释

矩阵运行额外生成 `ai-storage-matrix-<ID>/matrix-plan.json` 和 `matrix-summary.json/md`，记录各组合状态、通过/失败/未运行数量、总耗时与独立组合统计。每个组合生成独立的 `ai-storage-<ID>/` 报告目录：

- `plan.json`：数据量、文件布局、每轮命令和配置。
- `environment.json`：工具版本、主机、内存和挂载信息。
- 每阶段 `.log`、`.json`、`.fio`、`.command.json`：原始结果与参数。
- `summary.json`、`summary.md`：成功/失败、实际字节数、总耗时、各操作三轮中位数和范围。

工具返回非零、fio job error、结果缺失或有限读取/写入的实际字节数不足，均停止后续阶段并记录失败。mdtest 每个阶段必须包含对应统计。吞吐按实际完成字节数计算；不平均各 job 的 P99，原始 JSON 中保留 fio 的队列分布及延迟数据。

外部耗时包含进程启动、文件处理和最终同步；T02 的外部耗时还包含预热，正式测量窗口的带宽/延迟从 fio JSON 读取。预填充和校验不计入性能统计。

每轮读前会检查文件属性，这可能影响元数据缓存。默认明确标注缓存未完全控制，不自动宣称冷读，也不执行全机 drop_caches。可通过 `--ai-storage-cache-note` 记录实际采取的缓存控制措施。direct 不等于绕过存储端缓存。

启动新数据集前检查文件系统可用空间，要求覆盖该组逻辑数据量并留 5% 余量；它不能代替存储系统物理容量、快照和保护开销监控。按实际环境记录存储节点分布、访问协议、网卡、目录或卷配额、QoS、实际数据缩减比和随机数据生成 CPU 开销；使用 RDMA 或多路径时另行记录配置。

## 参数依据

- [fio 官方参数文档](https://fio.readthedocs.io/en/latest/fio_doc.html)
- [elbencho 官方完整参数](https://github.com/breuner/elbencho/blob/master/docs/usage/help-all.md)
- [mdtest 官方参数实现](https://github.com/hpc/ior/blob/main/src/mdtest.c)

执行时记录实际工具版本；elbencho 需要支持 `--jsonfile`、`--blockvarpct`、`--blockvaralgo` 和 `--sync`。版本不支持的参数会使该阶段失败，原始日志保留错误。
