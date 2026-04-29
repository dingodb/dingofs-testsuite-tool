# Phase 16: MLPerf 容器执行与数据集成 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-29
**Phase:** 16-mlperf-exec
**Areas discussed:** 镜像来源, 运行模式, 权限

---

## 镜像来源

| Option | Description | Selected |
|--------|-------------|----------|
| 集成到现有项目镜像 | mlperf-storage 安装到 dtt Docker 镜像内，通过 entrypoint.sh mlperf_run() 调用 | ✓ |
| 独立容器 | 启动单独的 mlperf-storage:latest 容器 | |

**User's choice:** 集成到现有的项目镜像中
**Notes:** 与 fio/vdbench/mdtest 等工具一致的集成方式。Dockerfile 需要更新，entrypoint.sh 需要新增 mlperf_run()

---

## 运行模式

| Option | Description | Selected |
|--------|-------------|----------|
| 交互式 (-it --rm) | 实时显示输出，退出后自动清理 | ✓ |
| daemon (-d) | 后台运行，需手动检查日志 | |

**User's choice:** 交互
**Notes:** 与现有 run_testsuite 和其他 debug shell 模式一致

---

## 权限

| Option | Description | Selected |
|--------|-------------|----------|
| --privileged | 完整特权模式 | ✓ |
| cap-add | 仅添加必要 capabilities | |

**User's choice:** 需要 --privileged
**Notes:** 与 dtt 其他工具保持一致

---

## Claude's Discretion

- mlperf_run() 函数的具体实现细节
- Dockerfile 中 Python 依赖的精确版本
- run_model.sh 逻辑是否需要重写

## Deferred Ideas

(None)
