# Phase 3: Output Formats - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

实现多种格式的测试报告输出：原始输出、JSON格式、HTML可视化报告、文本摘要。

**Requirements covered:** OUTP-01, OUTP-02, OUTP-03, OUTP-04, ENTRY-03

</domain>

<decisions>
## Implementation Decisions

### 输出格式

- **D-21:** 原始输出直接保存到文件
  - fio/vdbench/mdtest的原始输出保存到 `$OUTPUT/{tool}.raw`
- **D-22:** JSON格式使用工具原生输出
  - fio原生支持JSON：`--output-format=json`
  - vdbench原生支持HTML输出
  - mdtest输出需解析
- **D-23:** HTML报告使用Python脚本生成
  - 解析JSON/文本输出
  - 使用Jinja2或纯HTML+JS生成图表
- **D-24:** 文本摘要包含完整信息
  - 测试配置参数
  - 关键性能指标（IOPS、吞吐量、延迟）
  - 工具原始输出引用

### 报告生成时机

- **D-25:** 在entrypoint.sh中集成报告生成
  - 测试完成后自动调用报告生成脚本
- **D-26:** 输出目录结构：
  ```
  /data/results/
  ├── fio.raw
  ├── fio.json
  ├── summary.txt
  ├── report.html
  ├── vdbench.raw
  └── mdtest.raw
  ```

### Claude's Discretion

- HTML图表的具体实现（可使用简单CSS/JS或引入轻量库）
- Python脚本的依赖管理

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目文档
- `.planning/PROJECT.md` — 项目整体上下文
- `.planning/REQUIREMENTS.md` — 输出格式需求（OUTP系列）
- `.planning/ROADMAP.md` — 阶段定义

### Phase 2 上下文
- `.planning/phases/02-core-functionality/02-CONTEXT.md` — entrypoint.sh结构

### 工具文档
- fio JSON输出格式：fio --output-format=json
- vdbench HTML输出：vdbench -o选项

</canonical_refs>

<specifics>
## Specific Ideas

- Python脚本生成HTML报告
- 使用Python内置库减少依赖
- 报告生成作为entrypoint.sh的一部分

</specifics>

<deferred>
## Deferred Ideas

(None)

</deferred>

---

*Phase: 03-output-formats*
*Context gathered: 2026-04-03*
