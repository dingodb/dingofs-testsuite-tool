# Requirements: DingoFS Storage Benchmark Tools

**Defined:** 2026-04-03
**Core Value:** 让用户用最简单的方式执行存储性能测试 —— 一条命令即可完成测试

## v1 Requirements

### Docker镜像构建

- [ ] **DOCK-01**: Dockerfile基于ubuntu:24.04构建
- [ ] **DOCK-02**: 安装fio最新稳定版本
- [ ] **DOCK-03**: 安装vdbench最新稳定版本
- [ ] **DOCK-04**: 安装mdtest最新稳定版本
- [ ] **DOCK-05**: 镜像大小优化，清理不必要的依赖和缓存

### 参数输入

- [ ] **PARM-01**: 支持命令行参数传入工具名
- [ ] **PARM-02**: 支持命令行参数传入场景名
- [ ] **PARM-03**: 支持命令行参数传入文件系统挂载点路径
- [ ] **PARM-04**: 支持命令行参数传入日志输出路径
- [ ] **PARM-05**: 支持配置文件挂载方式传入所有参数
- [ ] **PARM-06**: 参数校验和错误提示

### 预设场景

- [x] **SCEN-01**: fio预设场景 - 顺序读写（seq_read, seq_write）
- [x] **SCEN-02**: fio预设场景 - 随机读写（rand_read, rand_write）
- [x] **SCEN-03**: fio预设场景 - 混合读写（randrw）
- [x] **SCEN-04**: vdbench预设场景 - 顺序读写
- [x] **SCEN-05**: vdbench预设场景 - 随机读写
- [x] **SCEN-06**: mdtest预设场景 - 元数据性能测试
- [x] **SCEN-07**: 支持用户自定义场景配置文件覆盖内置场景

### 输出格式

- [x] **OUTP-01**: 保留工具原始输出格式
- [x] **OUTP-02**: 输出结构化JSON格式报告
- [x] **OUTP-03**: 生成HTML可视化报告
- [x] **OUTP-04**: 输出文本摘要（关键指标）

### 运行模式

- [ ] **MODE-01**: 支持一次性运行模式（docker run执行测试后退出）
- [ ] **MODE-02**: 支持长期运行模式（容器保持运行）
- [ ] **MODE-03**: 长期运行模式下通过docker exec触发测试

### 入口脚本

- [ ] **ENTRY-01**: 提供统一的入口脚本(entrypoint.sh)
- [ ] **ENTRY-02**: 入口脚本解析参数并调用对应工具
- [x] **ENTRY-03**: 入口脚本生成多格式报告
- [ ] **ENTRY-04**: 提供帮助信息和使用示例

## v2 Requirements

### 扩展工具

- **TOOL-01**: 添加iozone工具支持
- **TOOL-02**: 添加iometer工具支持
- **TOOL-03**: 添加bonnie++工具支持

### 高级功能

- **ADVN-01**: REST API服务接口
- **ADVN-02**: 分布式多节点并行测试
- **ADVN-03**: 测试结果对比分析
- **ADVN-04**: 历史测试结果存储和查询

## Out of Scope

| Feature | Reason |
|---------|--------|
| GUI界面 | 命令行工具为主，GUI增加复杂度 |
| Windows容器支持 | 目标平台为Linux |
| 实时监控功能 | 专注于测试执行，监控由其他工具负责 |
| 分布式测试协调 | v1专注单节点，后续扩展 |

## v1.1 Requirements

### LTP 安装与构建

- [ ] **LTP-01**: 在 Docker 镜像中安装 LTP 工具集
- [ ] **LTP-02**: 使用 multi-stage build 优化镜像大小
- [ ] **LTP-03**: 支持 x86_64 和 ARM64 平台

### LTP 运行与集成

- [ ] **LTP-04**: 支持 `-t ltp` 命令行参数
- [ ] **LTP-05**: 创建 `ltp_run()` 函数执行测试
- [ ] **LTP-06**: 默认运行文件系统相关测试 (`-f fs`)

### LTP 运行时限制

- [ ] **LTP-07**: 使用 timeout 包装防止测试挂起
- [ ] **LTP-08**: 记录测试输出到用户指定目录
- [ ] **LTP-09**: 文档说明容器权限要求

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DOCK-01 | Phase 1 | Pending |
| DOCK-02 | Phase 1 | Pending |
| DOCK-03 | Phase 1 | Pending |
| DOCK-04 | Phase 1 | Pending |
| DOCK-05 | Phase 1 | Pending |
| PARM-01 | Phase 2 | Pending |
| PARM-02 | Phase 2 | Pending |
| PARM-03 | Phase 2 | Pending |
| PARM-04 | Phase 2 | Pending |
| PARM-05 | Phase 2 | Pending |
| PARM-06 | Phase 2 | Pending |
| SCEN-01 | Phase 2 | Complete |
| SCEN-02 | Phase 2 | Complete |
| SCEN-03 | Phase 2 | Complete |
| SCEN-04 | Phase 2 | Complete |
| SCEN-05 | Phase 2 | Complete |
| SCEN-06 | Phase 2 | Complete |
| SCEN-07 | Phase 2 | Complete |
| OUTP-01 | Phase 3 | Complete |
| OUTP-02 | Phase 3 | Complete |
| OUTP-03 | Phase 3 | Complete |
| OUTP-04 | Phase 3 | Complete |
| MODE-01 | Phase 2 | Pending |
| MODE-02 | Phase 2 | Pending |
| MODE-03 | Phase 2 | Pending |
| ENTRY-01 | Phase 2 | Pending |
| ENTRY-02 | Phase 2 | Pending |
| ENTRY-03 | Phase 3 | Complete |
| ENTRY-04 | Phase 2 | Pending |
| LTP-01 | Phase 5 | Pending |
| LTP-02 | Phase 5 | Pending |
| LTP-03 | Phase 5 | Pending |
| LTP-04 | Phase 6 | Pending |
| LTP-05 | Phase 6 | Pending |
| LTP-06 | Phase 6 | Pending |
| LTP-07 | Phase 7 | Pending |
| LTP-08 | Phase 7 | Pending |
| LTP-09 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 43 total (34 from v1.0 + 9 from v1.1)
- Mapped to phases: 43
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-03*
*Last updated: 2026-04-08 after roadmap creation for v1.1*
