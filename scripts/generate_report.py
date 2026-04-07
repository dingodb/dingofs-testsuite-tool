#!/usr/bin/env python3
"""
DingoFS Storage Benchmark Tools - Report Generation Script
Parses fio JSON, vdbench text, and mdtest text outputs to generate HTML and text reports.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from html import escape
from pathlib import Path


# ==============================================================================
# Argument Parsing
# ==============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate performance test reports from storage benchmark tools"
    )
    parser.add_argument(
        "--tool",
        required=True,
        choices=["fio", "vdbench", "mdtest"],
        help="Storage testing tool used"
    )
    parser.add_argument(
        "--output-dir",
        default="/data/results",
        help="Directory containing tool output files (default: /data/results)"
    )
    parser.add_argument(
        "--scenario",
        default="",
        help="Test scenario name for display"
    )
    parser.add_argument(
        "--mount",
        default="/data",
        help="Filesystem mount point (default: /data)"
    )
    parser.add_argument(
        "--combined",
        action="store_true",
        help="Generate combined summary from multiple sub-scenarios"
    )
    return parser.parse_args()


# ==============================================================================
# FIO Scenario Name Parser
# ==============================================================================

def parse_fio_scenario_name(scenario_name):
    """Parse fio scenario name to extract parameters.

    Naming convention: {rw}_{direct}d_{bs}_{numjobs}j
    Example: seq_read_1d_4m_32j -> rw=seq_read, direct=1, bs=4m, numjobs=32
    """
    # Pattern: rw_directd_bs_numjsj (e.g., seq_read_1d_4m_32j, seq_read_1d_128k_1j)
    pattern = r'^(.+?)_(\d)d_(\d+[km])_(\d+)j$'
    match = re.match(pattern, scenario_name)
    if match:
        return {
            "rw": match.group(1),
            "direct": int(match.group(2)),
            "bs": match.group(3),
            "numjobs": int(match.group(4))
        }
    return None


def aggregate_fio_results(output_dir):
    """Aggregate fio results from all subdirectories into summary tables.

    Returns two dictionaries (direct=0 and direct=1), each containing
    aggregated data grouped by (bs, numjobs).
    """
    direct_0 = {}  # direct=0 results
    direct_1 = {}  # direct=1 results

    if not os.path.isdir(output_dir):
        return direct_0, direct_1

    # Scan subdirectories
    for subdir in os.listdir(output_dir):
        subdir_path = os.path.join(output_dir, subdir)
        if not os.path.isdir(subdir_path):
            continue

        fio_json_path = os.path.join(subdir_path, "fio.json")
        if not os.path.exists(fio_json_path):
            continue

        # Parse scenario name to get parameters
        params = parse_fio_scenario_name(subdir)
        if not params:
            continue

        # Read and parse fio JSON
        try:
            with open(fio_json_path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        # Extract metrics from jobs
        jobs = data.get("jobs", [])
        if not jobs:
            continue

        # Determine if read or write based on scenario name
        is_read = params["rw"] in ("seq_read", "rand_read")
        job = jobs[0]

        if is_read:
            metrics = job.get("read", {})
        else:
            metrics = job.get("write", {})

        if not metrics:
            continue

        # Get bandwidth (KiB/s) and latency mean (ns)
        bw_kib = metrics.get("bw", 0)
        latency_ns_mean = metrics.get("lat_ns", {}).get("mean", 0)

        key = (params["bs"], params["numjobs"])

        if params["direct"] == 0:
            direct_0[key] = {
                "bandwidth_kib": bw_kib,
                "latency_ns_mean": latency_ns_mean
            }
        else:
            direct_1[key] = {
                "bandwidth_kib": bw_kib,
                "latency_ns_mean": latency_ns_mean
            }

    return direct_0, direct_1


# ==============================================================================
# FIO JSON Parser
# ==============================================================================

def parse_fio_json(output_dir):
    """Parse fio JSON output and extract key metrics."""
    fio_json_path = os.path.join(output_dir, "fio.json")

    if not os.path.exists(fio_json_path):
        return None, f"fio.json not found in {output_dir}"

    try:
        with open(fio_json_path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return None, f"Failed to parse fio JSON: {e}"

    # Extract global info
    info = {
        "timestamp": data.get("timestamp", ""),
        "fio_version": data.get("fio version", ""),
        "jobs": []
    }

    # Parse each job in the jobs array
    jobs = data.get("jobs", [])
    for job in jobs:
        job_result = {
            "name": job.get("jobname", "unknown"),
            "read": {},
            "write": {}
        }

        # Read metrics
        read_data = job.get("read", {})
        if read_data:
            # bw is in KiB/s, bw_bytes is in bytes
            bw_kib = read_data.get("bw", 0)
            bw_mib = bw_kib / 1024 if bw_kib else 0
            job_result["read"] = {
                "IOPS": read_data.get("iops", 0),
                "bandwidth_bytes": read_data.get("bw_bytes", 0),
                "bandwidth": f"{bw_mib:.2f} MiB/s",
                "latency_ns": {
                    "min": read_data.get("lat_ns", {}).get("min", 0),
                    "max": read_data.get("lat_ns", {}).get("max", 0),
                    "mean": read_data.get("lat_ns", {}).get("mean", 0),
                    "stddev": read_data.get("lat_ns", {}).get("stddev", 0),
                },
                "latency": {
                    "min": read_data.get("lat_ns", {}).get("min", 0) / 1000,  # ns to us
                    "max": read_data.get("lat_ns", {}).get("max", 0) / 1000,  # ns to us
                    "mean": read_data.get("lat_ns", {}).get("mean", 0) / 1000,  # ns to us
                    "stddev": read_data.get("lat_ns", {}).get("stddev", 0) / 1000,  # ns to us
                },
                "clat_ns": read_data.get("clat_ns", {}),
                "percentiles": parse_percentiles(read_data.get("clat_ns", {}).get("percentile", {})),
            }

        # Write metrics
        write_data = job.get("write", {})
        if write_data:
            # bw is in KiB/s, bw_bytes is in bytes
            bw_kib = write_data.get("bw", 0)
            bw_mib = bw_kib / 1024 if bw_kib else 0
            job_result["write"] = {
                "IOPS": write_data.get("iops", 0),
                "bandwidth_bytes": write_data.get("bw_bytes", 0),
                "bandwidth": f"{bw_mib:.2f} MiB/s",
                "latency_ns": {
                    "min": write_data.get("lat_ns", {}).get("min", 0),
                    "max": write_data.get("lat_ns", {}).get("max", 0),
                    "mean": write_data.get("lat_ns", {}).get("mean", 0),
                    "stddev": write_data.get("lat_ns", {}).get("stddev", 0),
                },
                "latency": {
                    "min": write_data.get("lat_ns", {}).get("min", 0) / 1000,  # ns to us
                    "max": write_data.get("lat_ns", {}).get("max", 0) / 1000,  # ns to us
                    "mean": write_data.get("lat_ns", {}).get("mean", 0) / 1000,  # ns to us
                    "stddev": write_data.get("lat_ns", {}).get("stddev", 0) / 1000,  # ns to us
                },
                "clat_ns": write_data.get("clat_ns", {}),
                "percentiles": parse_percentiles(write_data.get("clat_ns", {}).get("percentile", {})),
            }

        # CPU utilization
        job_result["cpu_util"] = job.get("usr_cpu", 0), job.get("sys_cpu", 0)

        # Submission latency
        job_result["submit_latency"] = job.get("latency", {}).get("submit", {})
        # Completion latency
        job_result["complete_latency"] = job.get("latency", {}).get("complete", {})
        # Queue depth
        job_result["queue_depth"] = job.get("latency", {}).get("queue_depth", 0)

        info["jobs"].append(job_result)

    return info, None


def parse_percentiles(percentile_data):
    """Parse and format percentile data."""
    if not percentile_data:
        return {}
    result = {}
    for p, val in percentile_data.items():
        # p is like "50.000000" for 50th percentile
        try:
            p_formatted = f"p{float(p):.0f}"
            result[p_formatted] = val
        except (ValueError, TypeError):
            continue
    return result


# ==============================================================================
# VDBENCH Text Parser
# ==============================================================================

def parse_vdbench_output(output_dir):
    """Parse vdbench output and extract key metrics."""
    # Try multiple possible locations for vdbench output
    vdbench_paths = [
        os.path.join(output_dir, "vdbench.raw"),
        os.path.join(output_dir, "vdbench.txt"),
        os.path.join(output_dir, "Vdbench_output.txt"),
    ]

    raw_text = None
    for path in vdbench_paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                raw_text = f.read()
            break

    if raw_text is None:
        return None, f"vdbench output not found in {output_dir}"

    info = {
        "raw_output": raw_text,
        "metrics": parse_vdbench_metrics(raw_text),
    }

    return info, None


def parse_vdbench_metrics(text):
    """Extract metrics from vdbench output text."""
    metrics = {
        "throughput": [],
        "IOPS": [],
        "response_time": [],
    }

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        # Look for standard vdbench output lines
        # Typical format: "avg_2" or "avg_4" response time and transaction rates
        if "avg_" in line and "response time" in line.lower():
            parts = line.split()
            # Format: "avg_2" response time ... N response time ...
            for i, part in enumerate(parts):
                if part.startswith("avg_") or (part.replace(".", "").isdigit() and "." in part):
                    try:
                        val = float(part)
                        if val > 0 and val < 1000000:
                            metrics["response_time"].append(val)
                    except ValueError:
                        pass
        # Look for throughput (MB/s or GB/s)
        if "mb/s" in line.lower() or "gb/s" in line.lower():
            parts = line.split()
            for i, part in enumerate(parts):
                if part.replace(".", "").replace("e", "").replace("-", "").isdigit():
                    try:
                        val = float(part)
                        if val > 0:
                            metrics["throughput"].append(val)
                    except ValueError:
                        pass
        # Look for I/O rates
        if "i/o rate" in line.lower():
            parts = line.split()
            for part in parts:
                if part.replace(".", "").isdigit():
                    try:
                        val = float(part)
                        if val > 0:
                            metrics["IOPS"].append(val)
                    except ValueError:
                        pass

    # Calculate averages if we have data
    result = {}
    for key, vals in metrics.items():
        if vals:
            result[f"{key}_avg"] = sum(vals) / len(vals)
            result[f"{key}_max"] = max(vals)
            result[f"{key}_min"] = min(vals)

    return result


# ==============================================================================
# MDTEST Text Parser
# ==============================================================================

def parse_mdtest_output(output_dir):
    """Parse mdtest output and extract key metrics."""
    # Try multiple possible locations
    mdtest_paths = [
        os.path.join(output_dir, "mdtest.raw"),
        os.path.join(output_dir, "mdtest.txt"),
    ]

    raw_text = None
    for path in mdtest_paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                raw_text = f.read()
            break

    if raw_text is None:
        return None, f"mdtest output not found in {output_dir}"

    info = {
        "raw_output": raw_text,
        "metrics": parse_mdtest_metrics(raw_text),
        "summary": parse_mdtest_summary(raw_text),
    }

    return info, None


def parse_mdtest_summary(text):
    """Parse mdtest summary statistics.

    mdtest output format:
       Operation                     Max            Min           Mean        Std Dev
       ---------                     ---            ---           ----        -------
       File creation               26100.313      26100.313      26100.313          0.000
    """
    summary = {
        "operations": []
    }

    lines = text.split("\n")
    in_summary_section = False

    for line in lines:
        # Look for the SUMMARY rate header
        if "SUMMARY rate" in line or "SUMMARY" in line.upper():
            in_summary_section = True
            continue

        # Skip header lines
        if in_summary_section:
            if "---" in line or "Operation" in line or not line.strip():
                continue

            # Parse operation line - fixed width format
            # Format: "Operation Name             Number         Number         Number         Number"
            stripped = line.strip()
            if not stripped:
                continue

            # Extract operation name (everything before the first number)
            parts = stripped.split()
            if len(parts) < 5:
                continue

            # Find where numbers start - they come after the operation name
            # The numbers are at fixed positions but we can identify them by being numeric
            nums = []
            op_name_parts = []

            for part in parts:
                try:
                    val = float(part)
                    nums.append(val)
                except ValueError:
                    op_name_parts.append(part)

            if len(nums) >= 4:
                op_name = " ".join(op_name_parts).replace("_", " ")
                summary["operations"].append({
                    "name": op_name,
                    "max": nums[0],
                    "min": nums[1],
                    "mean": nums[2],
                    "stddev": nums[3] if len(nums) > 3 else 0,
                })

    return summary


def parse_mdtest_metrics(text):
    """Extract metrics from mdtest output text."""
    metrics = {
        "create_rate": [],
        "remove_rate": [],
    }

    lines = text.split("\n")
    for line in lines:
        line = line.strip()

        # Look for mdtest summary lines with rates
        if "items" in line.lower() and ("sec" in line.lower() or "/s" in line):
            parts = line.split()
            for part in parts:
                try:
                    val = float(part)
                    if val > 0:
                        metrics["create_rate"].append(val)
                except ValueError:
                    pass

    # Calculate averages
    result = {}
    for key, vals in metrics.items():
        if vals:
            result[f"{key}_avg"] = sum(vals) / len(vals)
            result[f"{key}_max"] = max(vals)
            result[f"{key}_min"] = min(vals)

    return result


# ==============================================================================
# MDTEST Combined Report Generator
# ==============================================================================

def aggregate_mdtest_results(output_dir):
    """Aggregate mdtest results from all scenario subdirectories."""
    scenarios = []

    if not os.path.isdir(output_dir):
        return scenarios

    # Find all scenario directories
    for subdir in sorted(os.listdir(output_dir)):
        subdir_path = os.path.join(output_dir, subdir)
        if not os.path.isdir(subdir_path):
            continue

        # Skip non-mdtest directories
        if not subdir.startswith("mdtest_"):
            continue

        mdtest_raw_path = os.path.join(subdir_path, "mdtest.raw")
        if not os.path.exists(mdtest_raw_path):
            continue

        # Parse scenario name to extract z, b, I parameters
        # Pattern: mdtest_z0_n100, mdtest_z5_b4_I1, etc.
        params = parse_mdtest_scenario_name(subdir)
        if not params:
            continue

        # Read and parse mdtest output
        try:
            with open(mdtest_raw_path, "r") as f:
                raw_text = f.read()
        except IOError:
            continue

        summary = parse_mdtest_summary(raw_text)
        file_count = extract_mdtest_file_count(raw_text)

        scenarios.append({
            "name": subdir,
            "params": params,
            "file_count": file_count,
            "operations": summary.get("operations", []),
            "raw_output": raw_text,
        })

    return scenarios


def parse_mdtest_scenario_name(scenario_name):
    """Parse mdtest scenario name to extract parameters.

    Pattern: mdtest_z{z}_n{n} or mdtest_z{z}_b{b}_I{I}
    Examples:
      mdtest_z0_n100 -> z=0, n=100
      mdtest_z5_b4_I1 -> z=5, b=4, I=1
    """
    import re

    # Pattern 1: mdtest_z0_n100
    match = re.match(r'^mdtest_z(\d+)_n(\d+)$', scenario_name)
    if match:
        return {"z": int(match.group(1)), "n": int(match.group(2)), "b": None, "I": None}

    # Pattern 2: mdtest_z5_b4_I1
    match = re.match(r'^mdtest_z(\d+)_b(\d+)_I(\d+)$', scenario_name)
    if match:
        return {"z": int(match.group(1)), "b": int(match.group(2)), "I": int(match.group(3)), "n": None}

    return None


def extract_mdtest_file_count(text):
    """Extract total file/directory count from mdtest output."""
    # Look for line like "32 tasks, 3200 files"
    import re
    match = re.search(r'(\d+)\s+files', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 0


def generate_mdtest_combined_markdown(output_dir, scenarios, mount):
    """Generate combined markdown report for all mdtest scenarios."""
    timestamp = datetime.now().strftime("%Y-%m-%d")

    lines = []
    lines.append("# DingoFS 元数据性能测试报告")
    lines.append("")
    lines.append("## 测试环境")
    lines.append("")
    lines.append(f"- **测试工具**: mdtest")
    lines.append(f"- **进程数**: 32 tasks")
    lines.append(f"- **节点数**: 1 node")
    lines.append(f"- **测试路径**: {mount}")
    lines.append(f"- **测试日期**: {timestamp}")
    lines.append("")

    # Summary table
    lines.append("## 测试结果汇总")
    lines.append("")
    lines.append("| 测试场景 | 深度(z) | 分支(b) | 每目录项数(I) | 文件/目录数 | 状态 |")
    lines.append("|---------|---------|---------|---------------|-------------|------|")

    for sc in scenarios:
        params = sc["params"]
        if params["b"] is not None:
            # z5_b4_I1 format
            z = params["z"]
            b = params["b"]
            I = params["I"]
            n = "-"
        else:
            # z0_n100 format
            z = params["z"]
            b = "-"
            I = "-"
            n = params["n"]

        status = "成功" if sc["file_count"] > 0 else "失败"
        lines.append(f"| {sc['name']} | {z} | {b} | {I} | {sc['file_count']} | {status} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 详细性能数据")
    lines.append("")

    # Detailed data for each scenario
    for sc in scenarios:
        params = sc["params"]
        if params["b"] is not None:
            cmd = f"mdtest -z {params['z']} -b {params['b']} -I {params['I']} -d ./"
        else:
            cmd = f"mdtest -d ./test -z {params['z']} -F -n {params['n']}"

        lines.append(f"### {sc['name']}")
        lines.append(f"**命令**: `{cmd}`")
        lines.append(f"**文件/目录数**: {sc['file_count']}")
        lines.append("")
        lines.append("| 操作 | Max (ops/s) | Min (ops/s) | Mean (ops/s) | Std Dev |")
        lines.append("|------|-------------|-------------|--------------|---------|")

        for op in sc["operations"]:
            lines.append(f"| {op['name'].capitalize()} | {op['max']:.3f} | {op['min']:.3f} | {op['mean']:.3f} | {op['stddev']:.3f} |")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ==============================================================================
# HTML Report Generator
# ==============================================================================

def generate_html_report(tool, output_dir, data, scenario, mount, txt_filename):
    """Generate HTML report with embedded CSS and JS."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DingoFS Benchmark Report - {escape(tool.upper())}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .header h1 {{ font-size: 2em; margin-bottom: 10px; }}
        .header .meta {{ opacity: 0.9; font-size: 0.9em; }}
        .card {{ background: white; border-radius: 10px; padding: 25px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .card h2 {{ color: #667eea; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #eee; }}
        .card h3 {{ color: #764ba2; margin: 15px 0 10px; }}
        .config-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }}
        .config-item {{ background: #f8f9fa; padding: 15px; border-radius: 8px; }}
        .config-item .label {{ font-weight: bold; color: #667eea; font-size: 0.85em; text-transform: uppercase; }}
        .config-item .value {{ font-size: 1.2em; color: #333; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #667eea; color: white; font-weight: 600; }}
        tr:hover {{ background: #f8f9fa; }}
        .metric-value {{ font-weight: bold; color: #764ba2; font-size: 1.1em; }}
        .metric-unit {{ color: #888; font-size: 0.85em; }}
        .chart-container {{ margin: 20px 0; }}
        .chart-placeholder {{ background: #f8f9fa; border-radius: 8px; padding: 40px; text-align: center; color: #888; }}
        .footer {{ text-align: center; padding: 20px; color: #888; font-size: 0.85em; }}
        .raw-output {{ background: #1e1e1e; color: #d4d4d4; padding: 20px; border-radius: 8px; overflow-x: auto; font-family: 'Courier New', monospace; font-size: 0.85em; max-height: 400px; overflow-y: auto; white-space: pre-wrap; }}
        .tag {{ display: inline-block; background: #667eea; color: white; padding: 3px 10px; border-radius: 20px; font-size: 0.8em; margin-right: 5px; }}
        .tag.success {{ background: #28a745; }}
        .tag.info {{ background: #17a2b8; }}
        @media (max-width: 768px) {{ .header h1 {{ font-size: 1.5em; }} table {{ font-size: 0.9em; }}}}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>DingoFS Storage Benchmark Report</h1>
            <div class="meta">
                <span class="tag success">{escape(tool.upper())}</span>
                <span class="tag info">{escape(scenario or "N/A")}</span>
                <br>
                <span>Generated: {escape(timestamp)}</span>
            </div>
        </div>

        <div class="card">
            <h2>Test Configuration</h2>
            <div class="config-grid">
                <div class="config-item">
                    <div class="label">Tool</div>
                    <div class="value">{escape(tool.upper())}</div>
                </div>
                <div class="config-item">
                    <div class="label">Scenario</div>
                    <div class="value">{escape(scenario or "N/A")}</div>
                </div>
                <div class="config-item">
                    <div class="label">Mount Point</div>
                    <div class="value">{escape(mount)}</div>
                </div>
                <div class="config-item">
                    <div class="label">Output Directory</div>
                    <div class="value">{escape(output_dir)}</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>Key Performance Metrics</h2>
"""

    # Tool-specific content
    if tool == "fio":
        html += generate_fio_metrics_html(data)
    elif tool == "vdbench":
        html += generate_vdbench_metrics_html(data)
    elif tool == "mdtest":
        html += generate_mdtest_metrics_html(data)

    html += f"""
        </div>

        <div class="card">
            <h2>Performance Summary</h2>
            <div class="chart-placeholder">
                <p>Charts would render here with Chart.js integration</p>
                <p style="font-size:0.8em;margin-top:10px;">Install chart.js or use CDN version for interactive charts</p>
            </div>
        </div>

        <div class="card">
            <h2>Raw Output Reference</h2>
            <p style="margin-bottom:15px;">Full output files are available at:</p>
            <ul style="margin-left:20px;">
                <li><code>{escape(output_dir)}/{escape(tool)}.json</code> - Structured data</li>
                <li><code>{escape(output_dir)}/{escape(tool)}.raw</code> - Raw tool output</li>
                <li><code>{escape(txt_filename)}</code> - Markdown summary</li>
            </ul>
        </div>

        <div class="footer">
            <p>DingoFS Storage Benchmark Tools &bull; Generated {escape(timestamp)}</p>
        </div>
    </div>
</body>
</html>"""

    return html


def generate_fio_metrics_html(data):
    """Generate HTML for fio metrics."""
    html = ""

    if not data or "jobs" not in data:
        return "<p>No fio data available</p>"

    for job in data["jobs"]:
        job_name = escape(job.get("name", "unknown"))

        html += f"<h3>Job: {job_name}</h3>"
        html += "<table><thead><tr><th>Metric</th><th>Read</th><th>Write</th></tr></thead><tbody>"

        # Bandwidth
        read_bw = job.get("read", {}).get("bandwidth", "-")
        write_bw = job.get("write", {}).get("bandwidth", "-")
        html += f"<tr><td>Bandwidth</td><td class='metric-value'>{read_bw}</td><td class='metric-value'>{write_bw}</td></tr>"

        # IOPS
        read_iops = job.get("read", {}).get("IOPS", "-")
        write_iops = job.get("write", {}).get("IOPS", "-")
        if isinstance(read_iops, (int, float)):
            read_iops = f"{read_iops:,.0f}"
        if isinstance(write_iops, (int, float)):
            write_iops = f"{write_iops:,.0f}"
        html += f"<tr><td>IOPS</td><td class='metric-value'>{read_iops}</td><td class='metric-value'>{write_iops}</td></tr>"

        # Latency (mean)
        read_lat = job.get("read", {}).get("latency", {}).get("mean", "-")
        write_lat = job.get("write", {}).get("latency", {}).get("mean", "-")
        if isinstance(read_lat, (int, float)):
            read_lat = f"{read_lat:.2f} us"
        if isinstance(write_lat, (int, float)):
            write_lat = f"{write_lat:.2f} us"
        html += f"<tr><td>Latency (mean)</td><td class='metric-value'>{read_lat}</td><td class='metric-value'>{write_lat}</td></tr>"

        # Latency (min)
        read_lat_min = job.get("read", {}).get("latency", {}).get("min", "-")
        write_lat_min = job.get("write", {}).get("latency", {}).get("min", "-")
        if isinstance(read_lat_min, (int, float)):
            read_lat_min = f"{read_lat_min:.2f} us"
        if isinstance(write_lat_min, (int, float)):
            write_lat_min = f"{write_lat_min:.2f} us"
        html += f"<tr><td>Latency (min)</td><td class='metric-value'>{read_lat_min}</td><td class='metric-value'>{write_lat_min}</td></tr>"

        # Latency (max)
        read_lat_max = job.get("read", {}).get("latency", {}).get("max", "-")
        write_lat_max = job.get("write", {}).get("latency", {}).get("max", "-")
        if isinstance(read_lat_max, (int, float)):
            read_lat_max = f"{read_lat_max:.2f} us"
        if isinstance(write_lat_max, (int, float)):
            write_lat_max = f"{write_lat_max:.2f} us"
        html += f"<tr><td>Latency (max)</td><td class='metric-value'>{read_lat_max}</td><td class='metric-value'>{write_lat_max}</td></tr>"

        html += "</tbody></table>"

        # Percentiles
        percentiles = job.get("read", {}).get("percentiles", {})
        if percentiles:
            html += "<h4>Completion Latency Percentiles (Read)</h4>"
            html += "<table><thead><tr><th>Percentile</th><th>Value (ns)</th></tr></thead><tbody>"
            for p, val in sorted(percentiles.items()):
                html += f"<tr><td>{escape(p)}</td><td class='metric-value'>{val:,.0f}</td></tr>"
            html += "</tbody></table>"

    return html


def generate_vdbench_metrics_html(data):
    """Generate HTML for vdbench metrics."""
    html = ""
    metrics = data.get("metrics", {}) if data else {}

    if not metrics:
        return "<p>No vdbench metrics extracted</p>"

    html += "<table><thead><tr><th>Metric</th><th>Average</th><th>Min</th><th>Max</th></tr></thead><tbody>"

    for key in ["throughput", "IOPS", "response_time"]:
        avg_key = f"{key}_avg"
        min_key = f"{key}_min"
        max_key = f"{key}_max"

        if avg_key in metrics:
            avg_val = metrics.get(avg_key, "-")
            min_val = metrics.get(min_key, "-")
            max_val = metrics.get(max_key, "-")

            if isinstance(avg_val, (int, float)):
                avg_val = f"{avg_val:.2f}"
            if isinstance(min_val, (int, float)):
                min_val = f"{min_val:.2f}"
            if isinstance(max_val, (int, float)):
                max_val = f"{max_val:.2f}"

            html += f"<tr><td>{escape(key.capitalize())}</td><td class='metric-value'>{avg_val}</td><td>{min_val}</td><td>{max_val}</td></tr>"

    html += "</tbody></table>"
    return html


def generate_mdtest_metrics_html(data):
    """Generate HTML for mdtest metrics."""
    html = ""
    metrics = data.get("metrics", {}) if data else {}

    if not metrics:
        return "<p>No mdtest metrics extracted</p>"

    html += "<table><thead><tr><th>Metric</th><th>Average</th><th>Min</th><th>Max</th></tr></thead><tbody>"

    for key in ["create_rate", "remove_rate"]:
        avg_key = f"{key}_avg"
        min_key = f"{key}_min"
        max_key = f"{key}_max"

        if avg_key in metrics:
            avg_val = metrics.get(avg_key, "-")
            min_val = metrics.get(min_key, "-")
            max_val = metrics.get(max_key, "-")

            if isinstance(avg_val, (int, float)):
                avg_val = f"{avg_val:.2f}"
            if isinstance(min_val, (int, float)):
                min_val = f"{min_val:.2f}"
            if isinstance(max_val, (int, float)):
                max_val = f"{max_val:.2f}"

            html += f"<tr><td>{escape(key.replace('_', ' ').capitalize())}</td><td class='metric-value'>{avg_val}</td><td>{min_val}</td><td>{max_val}</td></tr>"

    html += "</tbody></table>"
    return html


# ==============================================================================
# Text Summary Generator
# ==============================================================================

def generate_text_summary(tool, output_dir, data, scenario, mount):
    """Generate markdown summary report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    summary = []
    summary.append("# DingoFS 存储性能测试报告")
    summary.append("")
    summary.append("## 测试配置")
    summary.append("")
    summary.append(f"| 参数 | 值 |")
    summary.append(f"|------|----|")
    summary.append(f"| 工具 | {tool.upper()} |")
    summary.append(f"| 场景 | {scenario or 'N/A'} |")
    summary.append(f"| 挂载点 | {mount} |")
    summary.append(f"| 输出目录 | {output_dir} |")
    summary.append(f"| 生成时间 | {timestamp} |")
    summary.append("")

    summary.append("## 关键性能指标")
    summary.append("")

    if tool == "fio":
        generate_fio_markdown_metrics(summary, data)
    elif tool == "vdbench":
        generate_vdbench_markdown_metrics(summary, data)
    elif tool == "mdtest":
        generate_mdtest_markdown_metrics(summary, data)

    summary.append("")
    summary.append("## 原始数据参考")
    summary.append("")
    summary.append(f"- JSON 输出: `{output_dir}/{tool}.json`")
    summary.append(f"- 原始输出: `{output_dir}/{tool}.raw`")
    summary.append(f"- 本报告: `{txt_filename}`")
    summary.append("")
    summary.append("---")
    summary.append("*由 DingoFS 存储性能测试工具生成*")

    return "\n".join(summary)


def generate_fio_markdown_metrics(summary, data):
    """Add fio metrics to markdown summary."""
    if not data or "jobs" not in data:
        summary.append("*无 fio 数据*")
        return

    for job in data["jobs"]:
        job_name = job.get("name", "unknown")
        summary.append(f"### 任务: {job_name}")
        summary.append("")

        read_data = job.get("read", {})
        write_data = job.get("write", {})

        if read_data:
            summary.append("| 指标 | 读 |")
            summary.append("|----|---|")
            bw = read_data.get("bandwidth", "-")
            summary.append(f"| 带宽 | {bw} |")
            iops = read_data.get("IOPS", "-")
            if isinstance(iops, (int, float)):
                iops = f"{iops:,.2f}"
            summary.append(f"| IOPS | {iops} |")
            lat = read_data.get("latency", {})
            lat_mean = lat.get('mean', '-')
            lat_min = lat.get('min', '-')
            lat_max = lat.get('max', '-')
            if isinstance(lat_mean, float):
                lat_mean = f"{lat_mean:.2f} us"
            if isinstance(lat_min, float):
                lat_min = f"{lat_min:.2f} us"
            if isinstance(lat_max, float):
                lat_max = f"{lat_max:.2f} us"
            summary.append(f"| 延迟 (平均) | {lat_mean} |")
            summary.append(f"| 延迟 (最小) | {lat_min} |")
            summary.append(f"| 延迟 (最大) | {lat_max} |")
            summary.append("")

        if write_data:
            summary.append("| 指标 | 写 |")
            summary.append("|----|---|")
            bw = write_data.get("bandwidth", "-")
            summary.append(f"| 带宽 | {bw} |")
            iops = write_data.get("IOPS", "-")
            if isinstance(iops, (int, float)):
                iops = f"{iops:,.2f}"
            summary.append(f"| IOPS | {iops} |")
            lat = write_data.get("latency", {})
            lat_mean = lat.get('mean', '-')
            lat_min = lat.get('min', '-')
            lat_max = lat.get('max', '-')
            if isinstance(lat_mean, float):
                lat_mean = f"{lat_mean:.2f} us"
            if isinstance(lat_min, float):
                lat_min = f"{lat_min:.2f} us"
            if isinstance(lat_max, float):
                lat_max = f"{lat_max:.2f} us"
            summary.append(f"| 延迟 (平均) | {lat_mean} |")
            summary.append(f"| 延迟 (最小) | {lat_min} |")
            summary.append(f"| 延迟 (最大) | {lat_max} |")
            summary.append("")


def generate_vdbench_markdown_metrics(summary, data):
    """Add vdbench metrics to markdown summary."""
    metrics = data.get("metrics", {}) if data else {}

    if not metrics:
        summary.append("*无 vdbench 指标数据*")
        return

    summary.append("| 指标 | 平均 | 最小 | 最大 |")
    summary.append("|-----|------|------|------|")
    for key in ["throughput", "IOPS", "response_time"]:
        avg_key = f"{key}_avg"
        if avg_key in metrics:
            avg = f"{metrics[avg_key]:.2f}"
            min_val = f"{metrics.get(f'{key}_min', '-'):.2f}"
            max_val = f"{metrics.get(f'{key}_max', '-'):.2f}"
            label = {"throughput": "吞吐量", "IOPS": "IOPS", "response_time": "响应时间"}[key]
            summary.append(f"| {label} | {avg} | {min_val} | {max_val} |")


def generate_mdtest_markdown_metrics(summary, data):
    """Add mdtest metrics to markdown summary."""
    metrics = data.get("metrics", {}) if data else {}

    if not metrics:
        summary.append("*无 mdtest 指标数据*")
        return

    summary.append("| Metric | Average | Min | Max |")
    summary.append("|--------|---------|-----|-----|")
    for key in ["create_rate", "remove_rate"]:
        avg_key = f"{key}_avg"
        if avg_key in metrics:
            avg = f"{metrics[avg_key]:.2f} items/sec"
            min_val = f"{metrics.get(f'{key}_min', '-'):.2f}"
            max_val = f"{metrics.get(f'{key}_max', '-'):.2f}"
            summary.append(f"| {key.replace('_', ' ').capitalize()} | {avg} | {min_val} | {max_val} |")


# ==============================================================================
# FIO Combined Summary Generator
# ==============================================================================

def generate_fio_summary_tables_html(direct_0, direct_1, rw_type):
    """Generate HTML summary tables for combined fio results."""
    html = ""

    # Determine column header based on rw_type
    if rw_type in ("seq_read", "rand_read"):
        bw_label = "READ_BANDWIDTH"
    else:
        bw_label = "WRITE_BANDWIDTH"

    # Define row order: bs (128k, 1m, 4m) x numjobs (1, 8, 16, 32)
    bs_order = ["128k", "1m", "4m"]
    numjobs_order = [1, 8, 16, 32]

    # direct=0 table
    html += "<div style='margin-bottom: 30px;'>"
    html += "<h3>Summary Table (direct=0, Buffered I/O)</h3>"
    html += "<table><thead><tr><th>Block Size</th><th>Num Jobs</th><th>BANDWIDTH (MiB/s)</th><th>Latency (us)</th></tr></thead><tbody>"

    for bs in bs_order:
        for numjobs in numjobs_order:
            key = (bs, numjobs)
            if key in direct_0:
                data = direct_0[key]
                bw_mib = data["bandwidth_kib"] / 1024 if data["bandwidth_kib"] else 0
                lat_us = data["latency_ns_mean"] / 1000 if data["latency_ns_mean"] else 0
                html += f"<tr><td>{bs}</td><td>{numjobs}</td><td class='metric-value'>{bw_mib:.2f}</td><td>{lat_us:.2f}</td></tr>"
            else:
                html += f"<tr><td>{bs}</td><td>{numjobs}</td><td>-</td><td>-</td></tr>"
    html += "</tbody></table></div>"

    # direct=1 table
    html += "<div style='margin-bottom: 30px;'>"
    html += "<h3>Summary Table (direct=1, Direct I/O)</h3>"
    html += "<table><thead><tr><th>Block Size</th><th>Num Jobs</th><th>BANDWIDTH (MiB/s)</th><th>Latency (us)</th></tr></thead><tbody>"

    for bs in bs_order:
        for numjobs in numjobs_order:
            key = (bs, numjobs)
            if key in direct_1:
                data = direct_1[key]
                bw_mib = data["bandwidth_kib"] / 1024 if data["bandwidth_kib"] else 0
                lat_us = data["latency_ns_mean"] / 1000 if data["latency_ns_mean"] else 0
                html += f"<tr><td>{bs}</td><td>{numjobs}</td><td class='metric-value'>{bw_mib:.2f}</td><td>{lat_us:.2f}</td></tr>"
            else:
                html += f"<tr><td>{bs}</td><td>{numjobs}</td><td>-</td><td>-</td></tr>"
    html += "</tbody></table></div>"

    return html


def generate_fio_summary_tables_text(direct_0, direct_1, rw_type):
    """Generate markdown summary tables for combined fio results."""
    lines = []

    # Determine column header based on rw_type
    if rw_type in ("seq_read", "rand_read"):
        bw_label = "读带宽 (MiB/s)"
    else:
        bw_label = "写带宽 (MiB/s)"

    # Define row order
    bs_order = ["128k", "1m", "4m"]
    numjobs_order = [1, 8, 16, 32]

    # direct=0 table
    lines.append("")
    lines.append("## 汇总表 (direct=0, 缓存 I/O)")
    lines.append("")
    lines.append(f"| 块大小 | 任务数 | {bw_label} | 延迟 (us) |")
    lines.append(f"|--------|--------|------------------|------------|")

    for bs in bs_order:
        for numjobs in numjobs_order:
            key = (bs, numjobs)
            if key in direct_0:
                data = direct_0[key]
                bw_mib = data["bandwidth_kib"] / 1024 if data["bandwidth_kib"] else 0
                lat_us = data["latency_ns_mean"] / 1000 if data["latency_ns_mean"] else 0
                lines.append(f"| {bs} | {numjobs} | {bw_mib:.2f} | {lat_us:.2f} |")
            else:
                lines.append(f"| {bs} | {numjobs} | - | - |")

    # direct=1 table
    lines.append("")
    lines.append("## 汇总表 (direct=1, 直接 I/O)")
    lines.append("")
    lines.append(f"| 块大小 | 任务数 | {bw_label} | 延迟 (us) |")
    lines.append(f"|--------|--------|------------------|------------|")

    for bs in bs_order:
        for numjobs in numjobs_order:
            key = (bs, numjobs)
            if key in direct_1:
                data = direct_1[key]
                bw_mib = data["bandwidth_kib"] / 1024 if data["bandwidth_kib"] else 0
                lat_us = data["latency_ns_mean"] / 1000 if data["latency_ns_mean"] else 0
                lines.append(f"| {bs} | {numjobs} | {bw_mib:.2f} | {lat_us:.2f} |")
            else:
                lines.append(f"| {bs} | {numjobs} | - | - |")

    return "\n".join(lines)


# ==============================================================================
# Main
# ==============================================================================

def main():
    args = parse_args()

    output_dir = args.output_dir
    tool = args.tool
    scenario = args.scenario
    mount = args.mount
    is_combined = args.combined

    # Parse tool-specific output
    data = None
    error = None

    if tool == "fio":
        data, error = parse_fio_json(output_dir)
    elif tool == "vdbench":
        data, error = parse_vdbench_output(output_dir)
    elif tool == "mdtest":
        data, error = parse_mdtest_output(output_dir)

    if error:
        print(f"Warning: {error}", file=sys.stderr)

    # Generate text summary with timestamped filename first
    text_summary = generate_text_summary(tool, output_dir, data, scenario, mount)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    scenario_str = scenario if scenario else tool
    txt_filename = f"{tool}_{scenario_str}_summary_{timestamp}.md"
    txt_path = os.path.join(output_dir, txt_filename)
    with open(txt_path, "w") as f:
        f.write(text_summary)
    print(f"Text summary generated: {txt_path}")

    # Generate HTML report
    html_report = generate_html_report(tool, output_dir, data, scenario, mount, txt_filename)
    html_path = os.path.join(output_dir, "report.html")
    with open(html_path, "w") as f:
        f.write(html_report)
    print(f"HTML report generated: {html_path}")

    # Generate combined summary tables if requested
    if is_combined and tool == "fio":
        direct_0, direct_1 = aggregate_fio_results(output_dir)

        # Determine rw_type from scenario name
        rw_type = "seq_read"  # default
        if scenario:
            params = parse_fio_scenario_name(scenario)
            if params:
                rw_type = params["rw"]

        # Generate and append summary tables to HTML report
        summary_html = generate_fio_summary_tables_html(direct_0, direct_1, rw_type)

        # Read existing HTML and insert summary before the footer
        with open(html_path, "r") as f:
            html_content = f.read()

        # Insert summary tables before </div> in the metrics card
        summary_html = """
        <div class="card">
            <h2>Combined Summary (All Sub-Scenarios)</h2>
        """ + summary_html + "</div>"

        # Find the last </div> before <div class="footer"> and insert before it
        footer_pos = html_content.find('<div class="footer">')
        if footer_pos > 0:
            html_content = html_content[:footer_pos] + summary_html + "\n" + html_content[footer_pos:]

        with open(html_path, "w") as f:
            f.write(html_content)
        print(f"Combined summary HTML appended: {html_path}")

        # Generate and append summary tables to text summary
        summary_text = generate_fio_summary_tables_text(direct_0, direct_1, rw_type)

        with open(txt_path, "a") as f:
            f.write("\n" + summary_text)
        print(f"Combined summary text appended: {txt_path}")

    # Generate combined mdtest report if requested
    if is_combined and tool == "mdtest":
        scenarios = aggregate_mdtest_results(output_dir)
        if scenarios:
            mdtest_combined = generate_mdtest_combined_markdown(output_dir, scenarios, mount)
            with open(txt_path, "w") as f:
                f.write(mdtest_combined)
            print(f"Combined mdtest report generated: {txt_path}")

    print("\nReport generation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
