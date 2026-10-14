"""Offline HTML and JSON reports for bounded storage performance runs.

Only successful measurement rounds contribute to arithmetic means. Preparation
results and absent/non-finite observations never become measurement samples.
"""
import html
import json
import math
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit


METRICS = (
    "bandwidth_mib_s", "read_mib_s", "write_mib_s", "iops",
    "latency_mean_us", "io_bytes", "elapsed_seconds",
)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def compute_statistics(rows: list) -> dict:
    """Return per-metric arithmetic statistics over successful rounds only."""
    successful = [row for row in rows if row.get("status") == "passed"]
    metrics = {}
    for key in METRICS:
        values = []
        for row in successful:
            value = row.get("elapsed_seconds") if key == "elapsed_seconds" else row.get("metrics", {}).get(key)
            if _number(value):
                values.append(value)
        metrics[key] = {
            "mean": math.fsum(value / len(values) for value in values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "samples": len(values),
        }
    return {"successful_rounds": len(successful), "completed_rounds": len(rows), "metrics": metrics}


def _finite_copy(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _finite_copy(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_finite_copy(item) for item in value]
    return value


def _escape(value):
    return html.escape(str(value), quote=True)


def _format(value):
    if not _number(value):
        return "—"
    return f"{value:,.2f}"


def _bytes(value):
    if not _number(value):
        return "—"
    human = float(value)
    unit = "B"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(human) < 1024 or unit == "PiB":
            break
        human /= 1024
    return f"{human:g} {unit} ({value} bytes)"


def _safe_artifact(path):
    """Accept local relative file paths; never emit navigation outside output."""
    if not isinstance(path, str) or not path or "%" in path or "\\" in path:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        return None
    try:
        parsed = urlsplit(path)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return None
    parts = PurePosixPath(unquote(path))
    if parts.is_absolute() or ".." in parts.parts or not parts.name or path.endswith("/"):
        return None
    return quote(path, safe="/._-")


def _artifact_links(artifacts):
    links = []
    for name, path in (artifacts or {}).items():
        safe = _safe_artifact(path)
        if safe is not None:
            links.append(f'<a href="{_escape(safe)}">{_escape(name)}</a>')
    return " · ".join(links) or "—"


def _status(status):
    labels = {"passed": ("通过", "passed"), "failed": ("失败", "failed"),
              "interrupted": ("中断", "interrupted")}
    label, css_class = labels.get(status, ("未完成", "interrupted"))
    return f'<span class="badge {css_class}">{label}</span>'


def _chart(rows):
    width = max(760, len(rows) * 70 + 100)
    height = 220
    values = [row.get("metrics", {}).get("bandwidth_mib_s") for row in rows]
    maximum = max([value for value in values if _number(value) and value > 0] or [1])
    lines = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="各轮带宽，单位 MiB/s">',
             '<line x1="45" y1="170" x2="{0}" y2="170" stroke="#cbd5e1"/>'.format(width - 20),
             '<text x="45" y="20" class="chart-label">MiB/s</text>']
    if not rows:
        lines.append('<text x="300" y="100" class="chart-label">暂无测量结果</text>')
    spacing = (width - 80) / max(1, len(rows))
    for index, (row, value) in enumerate(zip(rows, values)):
        x = 50 + index * spacing + (spacing - 36) / 2
        valid = _number(value) and value >= 0
        bar_height = value / maximum * 125 if valid else 0
        color = "#0d9488" if row.get("status") == "passed" else "#dc7667"
        label = _escape(row.get("round", index + 1))
        lines.append(f'<rect x="{x:.1f}" y="{170 - bar_height:.1f}" width="36" '
                     f'height="{bar_height:.1f}" rx="5" fill="{color}">'
                     f'<title>第 {label} 轮：{_format(value)} MiB/s</title></rect>')
        lines.append(f'<text x="{x + 18:.1f}" y="{max(36, 162 - bar_height):.1f}" '
                     f'text-anchor="middle" class="chart-value">{_format(value)}</text>')
        lines.append(f'<text x="{x + 18:.1f}" y="196" text-anchor="middle" '
                     f'class="chart-label">第 {label} 轮</text>')
    lines.append("</svg>")
    return "".join(lines)


_STYLE = """
:root{color-scheme:light;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;color:#172b3a;background:#f2f6f8}
*{box-sizing:border-box}body{margin:0}main{max-width:1280px;margin:0 auto;padding:36px 24px 48px}a{color:#087f8c;text-decoration:none}a:hover{text-decoration:underline}
header{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;margin-bottom:24px}.eyebrow{color:#087f8c;font-size:12px;font-weight:750;letter-spacing:.14em}h1{font-size:32px;letter-spacing:-.03em;margin:8px 0}h2{font-size:18px;margin:0 0 16px}p{line-height:1.7}.muted{color:#64748b;font-size:13px}.download{background:#fff;border:1px solid #d5e2e7;padding:10px 16px;border-radius:10px;white-space:nowrap;margin-top:8px}
.banner{display:flex;align-items:center;justify-content:space-between;gap:16px;border:1px solid #b5dfd4;background:#effbf6;border-radius:14px;padding:18px 22px;margin-bottom:22px}.banner.incomplete{background:#fff6ec;border-color:#f0d2af}.banner strong{font-size:19px}.banner p{margin:5px 0 0}.sample-count{font-size:26px;font-weight:750;white-space:nowrap}.badge{display:inline-block;font-size:12px;font-weight:650;border-radius:20px;padding:4px 10px;white-space:nowrap}.passed{background:#d5f4e8;color:#116b4a}.failed{background:#fee2df;color:#ae392b}.interrupted{background:#ffecd0;color:#905d17}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:22px}.card,.panel{background:#fff;border:1px solid #e0e8ed;border-radius:14px;box-shadow:0 3px 12px #24465904}.card{padding:20px}.card-name{font-size:13px;color:#64748b}.card-value{font-size:30px;font-weight:750;letter-spacing:-.03em;margin:8px 0}.unit{font-size:13px;font-weight:500;color:#64748b;margin-left:6px}.card-range{font-size:12px;color:#64748b;line-height:1.7}.panel{padding:22px;margin-bottom:22px}.panel-title{display:flex;justify-content:space-between;align-items:center;gap:14px}.parameters{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin:0}.parameters dt{font-size:12px;color:#64748b;margin-bottom:6px}.parameters dd{margin:0;font-size:14px;overflow-wrap:anywhere}.chart{overflow:auto}.chart svg{display:block;width:100%;min-width:760px}.chart-label{font-size:12px;fill:#64748b}.chart-value{font-size:12px;fill:#334155;font-weight:600}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;text-align:left;font-size:13px;white-space:nowrap}th{color:#64748b;background:#f8fafc;font-weight:550}th,td{padding:13px 12px;border-bottom:1px solid #e7edf1}td.number{text-align:right;font-variant-numeric:tabular-nums}tr[hidden]{display:none}.error-cell{white-space:normal;min-width:160px;max-width:280px;overflow-wrap:anywhere;color:#a33b2e}select{padding:7px 10px;border:1px solid #d4e1e6;border-radius:8px;background:#fff;color:#334155}.error{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff0ee;border-radius:8px;padding:14px;color:#963e31;font-size:13px}.notes{font-size:13px;color:#64748b;line-height:1.8}.notes p{margin:5px 0}footer{font-size:12px;color:#738394;text-align:center;padding:2px 0 16px}
@media(max-width:760px){main{padding:22px 14px}h1{font-size:26px}header{display:block}.download{display:inline-block}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.parameters{grid-template-columns:repeat(2,minmax(0,1fr))}.card{padding:15px}.card-value{font-size:25px}.panel{padding:16px}.banner{align-items:flex-start}.sample-count{font-size:21px}}
@media(max-width:430px){.cards,.parameters{grid-template-columns:1fr}.banner{display:block}.sample-count{margin-top:12px}}
@media print{body{background:white}main{padding:0}.download,select,label[for=status-filter]{display:none}.panel,.card{break-inside:avoid;box-shadow:none}.table-wrap{overflow:visible}tr[hidden]{display:table-row}}
"""


def _render(report):
    plan = report.get("plan", {})
    rows = report.get("rounds", [])
    stats = report["statistics"]
    complete = stats["complete"]
    status = report.get("status", "failed")
    heading = "测试完成" if complete else {"failed": "测试失败 · 未完成", "interrupted": "测试中断 · 未完成"}.get(status, "测试未完成")
    count = f'{stats["successful_rounds"]} / {stats["requested_rounds"]}'
    cards = []
    for name, title, unit in (("bandwidth_mib_s", "平均总带宽", "MiB/s"),
                              ("read_mib_s", "平均读带宽", "MiB/s"),
                              ("write_mib_s", "平均写带宽", "MiB/s"),
                              ("iops", "平均 IOPS", "IO/s"),
                              ("latency_mean_us", "平均延迟", "μs"),
                              ("elapsed_seconds", "平均单轮耗时", "s")):
        metric = stats["metrics"][name]
        cards.append(f'<article class="card"><div class="card-name">{title}</div>'
                     f'<div class="card-value">{_format(metric["mean"])}<span class="unit">{unit}</span></div>'
                     f'<div class="card-range">范围 {_format(metric["min"])} – {_format(metric["max"])}'
                     f'<br>有效样本 {metric["samples"]} 轮</div></article>')
    parameters = [
        ("测试工具", plan.get("tool", "—")), ("读写模式", plan.get("mode", "—")),
        ("Direct I/O", {1: "开启 (1)", 0: "关闭 (0)"}.get(plan.get("direct"), "—")),
        ("并发数", plan.get("concurrency", "—")), ("文件数量（总计）", plan.get("file_count", "—")),
        ("单文件大小", _bytes(plan.get("file_size_bytes"))), ("总数据量", _bytes(plan.get("total_size_bytes"))),
        ("I/O 块大小", _bytes(plan.get("block_size_bytes"))), ("计划轮数", plan.get("rounds", "—")),
        ("每个 worker 的 I/O 深度", plan.get("iodepth", "—")),
        ("目标读比例", str(plan["read_percent"]) + "%" if plan.get("read_percent") is not None else "—"),
        ("挂载点", plan.get("mount", "—")), ("测试数据目录", plan.get("data_dir", "—")),
        ("报告输出目录", plan.get("output_dir", "—")), ("工具版本", report.get("tool_version", "—")),
    ]
    parameter_html = "".join(f'<div><dt>{_escape(name)}</dt><dd>{_escape(value)}</dd></div>' for name, value in parameters)
    table_rows = []
    for index, row in enumerate(rows):
        metrics = row.get("metrics", {})
        safe_status = row.get("status") if row.get("status") in ("passed", "failed", "interrupted") else "interrupted"
        cells = "".join(f'<td class="number">{_format(metrics.get(key))}</td>' for key in METRICS[:5])
        table_rows.append(f'<tr data-status="{safe_status}"><td>{_escape(row.get("round", index + 1))}</td>'
                          f'<td>{_status(row.get("status"))}</td>{cells}'
                          f'<td class="number">{_format(row.get("elapsed_seconds"))}</td>'
                          f'<td>{_artifact_links(row.get("artifacts"))}</td>'
                          f'<td class="error-cell">{_escape(row.get("error") or "—")}</td></tr>')
    if not table_rows:
        table_rows.append('<tr><td colspan="10" class="muted">尚无测量结果</td></tr>')
    error = f'<div class="error">{_escape(report["error"])}</div>' if report.get("error") else ""
    preparation = ""
    if report.get("preparation"):
        prep = report["preparation"]
        preparation = (f'<section class="panel"><h2>读测试数据准备</h2><p>{_status(prep.get("status"))}'
                       f' · 耗时 {_format(prep.get("elapsed_seconds"))} s · {_artifact_links(prep.get("artifacts"))}</p>'
                       '<p class="muted">准备阶段单独记录，不计入性能均值。</p>'
                       + (f'<div class="error">{_escape(prep["error"])}</div>' if prep.get("error") else "") + '</section>')
    interpretation_notes = "".join(
        f'<p>{_escape(plan[key])}</p>' for key in ("cache_note", "metric_note") if plan.get(key)
    )
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>DingoFS 性能测试报告 · {_escape(plan.get("tool", ""))}</title><style>{_STYLE}</style></head>
<body><main><header><div><div class="eyebrow">DINGOFS / PERFORMANCE</div><h1>存储性能测试报告</h1>
<div class="muted">开始时间 {_escape(report.get("started_at", "—"))} · 总耗时 {_format(report.get("elapsed_seconds"))} s</div></div>
<a class="download" href="summary.json" download>下载 JSON 结果 ↓</a></header>
<section class="banner{'' if complete else ' incomplete'}"><div><strong>{heading}</strong>
<p class="muted">均值仅包含成功测量轮；失败、未执行及准备阶段不计入。</p>{error}</div>
<div><div class="sample-count">{count}</div><div class="muted">成功轮数 / 计划轮数</div></div></section>
<section class="cards" aria-label="成功测量轮的算术平均值">{''.join(cards)}</section>
<section class="panel"><h2>测试参数</h2><dl class="parameters">{parameter_html}</dl></section>
<section class="panel"><h2>各轮带宽</h2><div class="chart">{_chart(rows)}</div><p class="muted">绿色为成功轮，红色为未成功轮；未成功轮的观测值不参与均值。</p></section>
{preparation}<section class="panel"><div class="panel-title"><h2>逐轮结果</h2><div><label for="status-filter" class="muted">状态筛选 </label>
<select id="status-filter"><option value="all">全部</option><option value="passed">通过</option><option value="failed">失败</option><option value="interrupted">中断</option></select></div></div>
<div class="table-wrap"><table><thead><tr><th>轮次</th><th>状态</th><th>总带宽 MiB/s</th><th>读 MiB/s</th><th>写 MiB/s</th><th>IOPS</th><th>平均延迟 μs</th><th>耗时 s</th><th>原始文件</th><th>错误</th></tr></thead>
<tbody id="round-results">{''.join(table_rows)}</tbody></table></div></section>
<section class="panel notes"><h2>统计口径</h2>{interpretation_notes}<p>每个指标分别取成功轮的算术平均值，并展示最小值、最大值和有效样本数。缺失值显示为 —，不会按 0 参与平均。</p>
<p>延迟为各轮平均延迟的算术平均；不合并延迟分布，也不推算整体 P99。MiB/s 以 1 MiB = 1,048,576 bytes 计算。</p>
<p>未完成的报告只反映已成功轮次的观测结果，不能视为完整测试。原始命令、配置及工具输出可由逐轮链接查看。</p></section>
<footer>DingoFS 性能测试 · 离线报告 · 无外部依赖</footer></main>
<script>document.getElementById('status-filter').addEventListener('change',function(){{
var wanted=this.value;document.querySelectorAll('#round-results tr[data-status]').forEach(function(row){{row.hidden=wanted!=='all'&&row.dataset.status!==wanted;}});
}});</script></body></html>'''


def write_report(report: dict, output: Path) -> dict:
    """Write summary.json and self-contained index.html, returning enriched data.

    The input is not mutated. Non-finite JSON numbers become null. "complete"
    requires overall success and exactly the requested number of passed rounds.
    "completed_rounds" counts recorded attempts, including failed attempts.
    """
    result = _finite_copy(report)
    rows = result.get("rounds", [])
    statistics = compute_statistics(rows)
    requested = result.get("plan", {}).get("rounds", len(rows))
    statistics["requested_rounds"] = requested
    statistics["complete"] = (
        result.get("status") == "passed" and requested > 0
        and statistics["successful_rounds"] == requested and len(rows) == requested
    )
    result["statistics"] = statistics
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    (destination / "index.html").write_text(_render(result), encoding="utf-8")
    return result
