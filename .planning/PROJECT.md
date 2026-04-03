# DingoFS Storage Benchmark Tools

## What This Is

一个存储性能测试工具镜像，内置fio、vdbench、mdtest三种测试工具，支持用户通过命令行参数或配置文件快速执行存储性能测试。镜像提供预设测试场景（顺序读写、随机读写、混合读写），同时支持用户自定义场景配置，输出多种格式的测试报告。

## Core Value

让用户用最简单的方式执行存储性能测试 —— 一条命令即可完成测试，无需关注工具安装和配置细节。

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Dockerfile基于ubuntu:24.04构建
- [ ] 内置fio、vdbench、mdtest三种存储测试工具
- [ ] 支持命令行参数传入：工具名、场景名、挂载点路径、日志输出路径
- [ ] 支持配置文件挂载方式传入参数
- [ ] 内置基础预设场景：顺序读写、随机读写、混合读写
- [ ] 支持用户自定义场景配置覆盖内置场景
- [ ] 输出多种格式报告：原始输出、结构化JSON、HTML报告、文本摘要
- [ ] 支持一次性运行模式（测试完成后退出）
- [ ] 支持长期运行模式（通过docker exec触发测试）

### Out of Scope

- 分布式多节点并行测试 — 后续版本考虑
- REST API服务接口 — v2考虑
- 其他测试工具（iozone、iometer等）— 后续版本扩展
- GUI界面 — 不在规划内

## Context

- 目标用户：存储系统开发/测试人员
- 主要用途：DingoFS或其他分布式存储系统的性能测试
- 运行环境：Docker容器
- 工具特性：
  - fio: 灵活的I/O测试工具，支持多种I/O引擎和场景
  - vdbench: Oracle出品，适合块设备和文件系统测试
  - mdtest: 元数据性能测试工具，测试文件系统元数据操作

## Constraints

- **基础镜像**: ubuntu:24.04 — 用户指定
- **工具版本**: 使用各工具的最新稳定版本
- **镜像大小**: 尽量精简，避免不必要的依赖
- **兼容性**: 需要在x86_64和ARM64平台运行

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| ubuntu:24.04作为基础镜像 | 用户熟悉，包管理完善，工具兼容性好 | — Pending |
| 内置预设场景 + 支持自定义 | 兼顾易用性和灵活性 | — Pending |
| 命令行参数 + 配置文件双模式 | 适应不同使用场景 | — Pending |
| docker exec触发测试 | 简单直接，无需额外服务 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-03 after initialization*
