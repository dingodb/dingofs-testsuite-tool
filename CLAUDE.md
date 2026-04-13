<!-- GSD:project-start source:PROJECT.md -->
## Project

**DingoFS Storage Testsuite Tools**

一个存储性能测试工具镜像，内置fio、vdbench、mdtest三种测试工具，支持用户通过命令行参数或配置文件快速执行存储性能测试。镜像提供预设测试场景（顺序读写、随机读写、混合读写），同时支持用户自定义场景配置，输出多种格式的测试报告。

**Core Value:** 让用户用最简单的方式执行存储性能测试 —— 一条命令即可完成测试，无需关注工具安装和配置细节。

### Constraints

- **基础镜像**: ubuntu:24.04 — 用户指定
- **工具版本**: 使用各工具的最新稳定版本
- **镜像大小**: 尽量精简，避免不必要的依赖
- **兼容性**: 需要在x86_64和ARM64平台运行
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
