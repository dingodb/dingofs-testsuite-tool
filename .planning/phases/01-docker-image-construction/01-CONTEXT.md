# Phase 1: Docker Image Construction - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

构建包含fio、vdbench、mdtest三种存储测试工具的Docker基础镜像。镜像基于ubuntu:24.04，用户可以验证所有工具已正确安装并可用。

**Requirements covered:** DOCK-01 ~ DOCK-05

</domain>

<decisions>
## Implementation Decisions

### 工具安装方式

- **D-01:** fio通过apt安装 — 简单直接，版本由Ubuntu仓库决定
- **D-02:** vdbench通过下载预编译jar包安装 — 需要Java运行时环境
- **D-03:** 安装JRE only（非完整JDK）— 仅运行vdbench，镜像更小
- **D-04:** mdtest通过apt安装 — 简单直接

### 镜像优化策略

- **D-05:** 使用单阶段构建 — 简单直接，构建和运行在同一镜像
- **D-06:** 镜像构建后清理apt缓存 — `apt clean && rm -rf /var/lib/apt/lists/*`

### Claude's Discretion

- 多平台支持（x86_64/ARM64）的具体实现方式 — 可在规划阶段决定

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目文档
- `.planning/PROJECT.md` — 项目整体上下文和约束条件
- `.planning/REQUIREMENTS.md` — 完整需求列表（DOCK-01 ~ DOCK-05）
- `.planning/ROADMAP.md` — 阶段定义和成功标准

### 工具文档（参考）
- fio: https://fio.readthedocs.io/ — 安装和使用说明
- vdbench: Oracle官方文档 — 需要Java运行时
- mdtest: https://github.com/hpc/ior — 元数据测试工具

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
(None — 这是greenfield项目)

### Established Patterns
(None — 这是greenfield项目)

### Integration Points
(None — 这是基础镜像构建阶段)

</code_context>

<specifics>
## Specific Ideas

- 基础镜像明确为 ubuntu:24.04（用户指定）
- 目标平台：x86_64 和 ARM64
- 镜像大小应尽量精简

</specifics>

<deferred>
## Deferred Ideas

(None — 讨论保持在阶段范围内)

</deferred>

---

*Phase: 01-docker-image-construction*
*Context gathered: 2026-04-03*
