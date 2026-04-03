# Phase 2: Core Functionality - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-03
**Phase:** 02-core-functionality
**Areas discussed:** 参数接口设计, 场景定义, 运行模式, 自定义场景

---

## 参数接口设计

| Option | Description | Selected |
|--------|-------------|----------|
| 短选项如 -t -s | 简洁，但记忆成本高 | |
| 长选项如 --tool --scenario | 更清晰，但较长 | ✓ |
| 位置参数 | 最简洁，但灵活性差 | |

**User's choice:** 长选项 + 短选项都支持

---

## 场景定义

| Option | Description | Selected |
|--------|-------------|----------|
| 独立配置文件 | 每个场景一个文件 | |
| 单一配置文件中 | 所有场景在一个文件，用section区分 | |
| 内置固定场景 | 通过名称引用，不能自定义 | |

**User's choice:** 不同工具各自定义场景（分开目录）

---

## 运行模式

| Option | Description | Selected |
|--------|-------------|----------|
| 一次性运行 | 执行单个测试，容器退出 | ✓ |
| 长期运行模式 | 容器启动后等待命令 | ✓ |
| 两者都要 | 支持两种模式 | ✓ |

**User's choice:** 两者都要

---

## 工具场景分开

| Option | Description | Selected |
|--------|-------------|----------|
| 是的，fio vdbench各自定义 | 分开目录管理 | ✓ |
| 统一管理 | 全部放一起 | |

**User's choice:** 是的，fio vdbench各自定义各自的，mdtest只做元数据性能测试

---

## 自定义场景支持

| Option | Description | Selected |
|--------|-------------|----------|
| 用户配置文件挂载 | 用户挂载自己的配置文件 | ✓ |
| 命令行传递参数 | 通过环境变量或命令行传入 | ✓ |
| 两者都要 | 两种方式都支持 | ✓ |

**User's choice:** 两者都要

---

## Claude's Discretion

- 参数校验的具体实现细节
- 错误处理的具体方式
- 日志输出路径的默认处理

## Deferred Ideas

(None — 讨论保持在阶段范围内)
