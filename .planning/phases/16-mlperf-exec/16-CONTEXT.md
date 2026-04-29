# Phase 16: MLPerf 容器执行与数据集成 - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning

<domain>
## Phase Boundary

替换 Phase 15 的占位输出，实现 mlperf-storage 工具集成到 dtt Docker 镜像中。用户通过 `dtt -t mlperf` 在 dtt 容器内执行 MLPerf 存储基准测试，参数从 dtt CLI 传入 entrypoint.sh 的 `mlperf_run()` 函数。

This phase delivers: Dockerfile 更新 + entrypoint.sh 新增 mlperf_run() + dtt wrapper 替换占位代码。
</domain>

<decisions>
## Implementation Decisions

### 集成方式
- **D-01:** mlperf-storage 安装到 dtt Docker 镜像内，作为 dtt 容器的内置工具（与 fio/vdbench/mdtest 一致），不启动独立容器
- **D-02:** 用户在容器内直接调用 `mlpstorage training datagen/run` 等命令，通过 entrypoint.sh 的 `mlperf_run()` 函数编排

### 容器运行参数
- **D-03:** 运行模式：`-it --rm`（交互式，退出后自动删除）
- **D-04:** 权限：`--privileged`（与 dtt 其他工具一致）
- **D-05:** 共享内存：`--shm-size=8g`（PyTorch DataLoader 多进程数据加载需要）

### 参数映射（dtt CLI → mlperf 环境变量）
- **D-06:** `-s` → `MODELS`（resnet50/unet3d/cosmoflow/checkpointing，或 all 展开为逗号分隔列表）
- **D-07:** `--scale` → `SCALE`（small/medium/large，默认 small）
- **D-08:** `--file_count` → 直接传递为 `num_files_train` 参数（优先级高于 scale 的文件数默认值）
- **D-09:** `--gpu_count` → `NUM_ACCELERATORS`（默认 1）

### 挂载映射
- **D-10:** dtt config testdir → `/data`（mlperf 测试数据目录）
- **D-11:** dtt config output → `/output`（与 dtt 其他工具共用输出挂载点）

### Dockerfile 变更
- **D-12:** 参考 `/mnt/disk0/daigy/jl_mlperf/mlperf/mlperf/Dockerfile` 的构建步骤：
  - Python 3.12 venv at `/opt/mlpstorage-env`
  - dlio-benchmark + mlpstorage Python 包（`--no-deps` 安装避免拉取 GPU 库）
  - CPU-only PyTorch + TensorFlow
  - 源码补丁（TensorFlow/TF-IO 可选导入）

### entrypoint.sh 变更
- **D-13:** 新增 `mlperf_run()` 函数，编排 datagen → run → report 生命周期
- **D-14:** 参数通过环境变量传入（由 dtt wrapper 设置 `-e`）

### Claude's Discretion
- mlperf_run() 的具体实现细节（错误处理、日志格式）
- Dockerfile 中 Python 依赖的精确版本锁定
- run_model.sh 是否需要直接复制还是重写逻辑
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### MLPerf 上游工具
- `/mnt/disk0/daigy/jl_mlperf/mlperf/mlperf/Dockerfile` — mlperf-storage 镜像构建步骤、Python 依赖、源码补丁
- `/mnt/disk0/daigy/jl_mlperf/mlperf/mlperf/entrypoint.sh` — mlperf 容器入口点、环境变量列表、MODELS 解析
- `/mnt/disk0/daigy/jl_mlperf/mlperf/mlperf/run_model.sh` — 单模型生命周期：datagen → run → report

### dtt 项目现有代码
- `Dockerfile` — dtt 镜像当前构建步骤、已安装工具
- `entrypoint.sh` — 现有 7 个 run 函数（fio_run, vdbench_run, mdtest_run, pjdtest_run, ltp_run, integration_run）的模式参考
- `dingofs-testsuite-tool` — dtt wrapper 脚本，Phase 15 已添加参数解析（$scenario, $scale, $file_count, $gpu_count），需替换第 564-574 行的占位退出

### 项目上下文
- `.planning/PROJECT.md` — 项目核心价值和约束
- `.planning/REQUIREMENTS.md` — v1.4 需求（EXEC-01~03, DATA-01~03）
- `.planning/ROADMAP.md` — Phase 16 成功标准
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `run_testsuite()` 函数（dingofs-testsuite-tool 第 431 行）：已有 docker run 命令构建模式，包含 -v 挂载、-e 环境变量、--privileged
- `run_debug_shell()` 函数（第 370 行）：已有 -it --rm --privileged 容器启动模式

### Established Patterns
- Dockerfile 已使用多阶段构建（LTP 阶段），mlperf 可以添加为新的构建阶段
- entrypoint.sh 的 run 函数模式：参数解析 → 命令构建 → 执行 → log_result
- dtt wrapper 与容器内 entrypoint.sh 通过环境变量 + 命令行参数传递配置

### Integration Points
- dtt wrapper `run_testsuite()` 第 564-574 行：替换 mlperf 的占位退出为真正的 docker run
- dtt wrapper 第 523-575 行：mlperf 参数验证后需要传递给容器
- entrypoint.sh：需要新增 mlperf 在 run 函数路由中的分支
- Dockerfile：新增加 mlperf-storage 构建阶段
</code_context>

<specifics>
## Specific Ideas

- mlperf_run() 应直接调用 `mlpstorage` CLI（`mlpstorage training datagen`, `mlpstorage training run`, `mlpstorage reports reportgen`），不需要 run_model.sh 包装层
- 支持多 workload 顺序执行（`MODELS=resnet50,unet3d` 时逐个执行并汇总结果）
- 结果显示实时输出（-it 模式），方便观察进度
- 因为集成到 dtt 镜像，mlperf 可以和 fio/vdbench 一样在同一个 pod/容器中运行
</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope
</deferred>

---

*Phase: 16-mlperf-exec*
*Context gathered: 2026-04-29*
