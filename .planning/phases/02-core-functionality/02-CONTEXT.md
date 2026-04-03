# Phase 2: Core Functionality - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

实现参数输入、预设场景、运行模式的核心功能。用户可通过命令行或配置文件执行存储性能测试。

**Requirements covered:** PARM-01~06, SCEN-01~07, MODE-01~03, ENTRY-01~02, ENTRY-04

</domain>

<decisions>
## Implementation Decisions

### 参数接口设计

- **D-07:** 命令行同时支持短选项和长选项
  - 短选项：`-t` (tool), `-s` (scenario), `-m` (mount), `-o` (output)
  - 长选项：`--tool`, `--scenario`, `--mount`, `--output`
- **D-08:** 使用 `--` 分隔Docker参数和应用参数

### 场景定义

- **D-09:** 不同工具的场景分开定义
  - `scenarios/fio/` - fio预设场景
  - `scenarios/vdbench/` - vdbench预设场景
  - `scenarios/mdtest/` - mdtest预设场景
- **D-10:** 场景文件格式为工具原生配置格式
  - fio: `.fio` 文件格式
  - vdbench: `.par` 参数文件格式
  - mdtest: 内置固定场景

### 预设场景

- **D-11:** fio预设场景（scenarios/fio/）：
  - `seq_read.fio` - 顺序读
  - `seq_write.fio` - 顺序写
  - `rand_read.fio` - 随机读
  - `rand_write.fio` - 随机写
  - `randrw.fio` - 混合读写

- **D-12:** vdbench预设场景（scenarios/vdbench/）：
  - `seq_rd.par` - 顺序读
  - `seq_wr.par` - 顺序写
  - `rand_rd.par` - 随机读
  - `rand_wr.par` - 随机写

- **D-13:** mdtest预设场景：
  - 元数据性能测试（固定，无需配置）

### 用户自定义场景

- **D-14:** 支持用户挂载自己的配置文件
  - 用户配置文件挂载到 `/custom/` 目录
  - 优先使用用户配置覆盖内置场景
- **D-15:** 支持通过命令行传递自定义参数
  - 环境变量或直接参数传递

### 运行模式

- **D-16:** 支持两种运行模式
  - 一次性运行：执行测试后容器退出
  - 长期运行：容器保持运行，通过 `docker exec` 触发测试
- **D-17:** 默认模式为一次性运行

### 入口脚本

- **D-18:** 提供统一的入口脚本 `entrypoint.sh`
- **D-19:** 入口脚本解析命令行参数并调用对应工具
- **D-20:** 提供 `-h/--help` 帮助信息

### Claude's Discretion

- 参数校验的具体实现细节
- 错误处理的具体方式
- 日志输出路径的默认处理

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目文档
- `.planning/PROJECT.md` — 项目整体上下文和约束条件
- `.planning/REQUIREMENTS.md` — 完整需求列表（PARM, SCEN, MODE, ENTRY系列）
- `.planning/ROADMAP.md` — 阶段定义和成功标准

### Phase 1 上下文
- `.planning/phases/01-docker-image-construction/01-CONTEXT.md` — Phase 1 决策（工具安装）

</canonical_refs>

<code_context>
## Existing Code Insights

### Phase 1 工件
- Dockerfile 已存在，基于 ubuntu:24.04
- 工具已安装：fio, vdbench, mdtest

### 目录结构
- 镜像内工具路径：fio (系统), vdbench (/opt/vdbench/vdbench), mdtest (/usr/local/bin/mdtest)
- 工作目录：/data

</code_context>

<specifics>
## Specific Ideas

- 使用 bash 脚本作为入口（entrypoint.sh）
- 配置文件挂载点：/custom/
- 场景配置文件在容器内：/scenarios/

</specifics>

<deferred>
## Deferred Ideas

(None — 讨论保持在阶段范围内)

</deferred>

---

*Phase: 02-core-functionality*
*Context gathered: 2026-04-03*
