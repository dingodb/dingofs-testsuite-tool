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

## Superpowers Workflow Enforcement

This project uses the **superpowers** plugin for all development work. Always follow the superpowers workflow without needing the user to explicitly request it.

### Core Skills (load automatically when relevant)

- **brainstorming** — Structured brainstorming before implementation
- **subagent-driven-development** — Dispatch subagents for implementation with built-in code review
- **systematic-debugging** — Structured debugging process
- **test-driven-development** — Red/green TDD
- **writing-plans** — Write implementation plans before coding
- **executing-plans** — Execute plans with task tracking
- **requesting-code-review** / **receiving-code-review** — Code review workflow
- **verification-before-completion** — Verify work before marking complete
- **using-git-worktrees** — Isolate work in git worktrees

### Default Behavior

- Before any non-trivial code change, **brainstorm** and **write a plan** first
- For implementation, use **subagent-driven-development** with code review
- For bug fixing, use **systematic-debugging**
- Always **verify before completion**



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
