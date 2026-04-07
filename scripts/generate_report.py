#!/usr/bin/env python3
"""
DingoFS Storage Benchmark Tools - Report Generation Script
Parses fio JSON, vdbench text, and mdtest text outputs to generate HTML and text reports.
"""

import argparse
import json
import os
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
    return parser.parse_args()


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
    mdtest_path = os.path.join(output_dir, "mdtest.txt")

    if not os.path.exists(mdtest_path):
        return None, f"mdtest.txt not found in {output_dir}"

    with open(mdtest_path, "r") as f:
        raw_text = f.read()

    info = {
        "raw_output": raw_text,
        "metrics": parse_mdtest_metrics(raw_text),
    }

    return info, None


def parse_mdtest_metrics(text):
    """Extract metrics from mdtest output text."""
    metrics = {
        "create_rate": [],
        "remove_rate": [],
        "tree_ops": [],
    }

    lines = text.split("\n")
    for line in lines:
        line = line.strip()

        # Look for mdtest summary lines with rates
        # Typical format: "   1        0.012583       0.010192       1.23 ..." or items/sec
        if "items" in line.lower() and ("sec" in line.lower() or "/s" in line):
            parts = line.split()
            for part in parts:
                if part.replace(".", "").replace("e", "").replace("-", "").isdigit():
                    try:
                        val = float(part)
                        if val > 0:
                            metrics["create_rate"].append(val)
                    except ValueError:
                        pass

        # Look for remove/stat rates
        if "remove" in line.lower() or "stat" in line.lower():
            parts = line.split()
            for part in parts:
                if part.replace(".", "").replace("e", "").replace("-", "").isdigit():
                    try:
                        val = float(part)
                        if val > 0:
                            metrics["remove_rate"].append(val)
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
# HTML Report Generator
# ==============================================================================

def generate_html_report(tool, output_dir, data, scenario, mount):
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
                <li><code>{escape(output_dir)}/summary.txt</code> - Text summary</li>
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
    """Generate text summary report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    summary = []
    summary.append("=" * 60)
    summary.append("DingoFS Storage Benchmark - Test Summary")
    summary.append("=" * 60)
    summary.append(f"Tool:     {tool.upper()}")
    summary.append(f"Scenario: {scenario or 'N/A'}")
    summary.append(f"Mount:    {mount}")
    summary.append(f"Output:   {output_dir}")
    summary.append(f"Generated: {timestamp}")
    summary.append("")

    summary.append("-" * 60)
    summary.append("TEST CONFIGURATION")
    summary.append("-" * 60)
    summary.append(f"  Tool:           {tool.upper()}")
    summary.append(f"  Scenario:       {scenario or 'N/A'}")
    summary.append(f"  Mount Point:    {mount}")
    summary.append(f"  Output Dir:     {output_dir}")
    summary.append("")

    summary.append("-" * 60)
    summary.append("KEY PERFORMANCE METRICS")
    summary.append("-" * 60)

    if tool == "fio":
        generate_fio_text_metrics(summary, data)
    elif tool == "vdbench":
        generate_vdbench_text_metrics(summary, data)
    elif tool == "mdtest":
        generate_mdtest_text_metrics(summary, data)

    summary.append("")
    summary.append("-" * 60)
    summary.append("RAW OUTPUT REFERENCE")
    summary.append("-" * 60)
    summary.append(f"  JSON Output:  {output_dir}/{tool}.json")
    summary.append(f"  Raw Output:   {output_dir}/{tool}.raw")
    summary.append(f"  This Summary: {output_dir}/summary.txt")
    summary.append("")
    summary.append("=" * 60)
    summary.append("End of Report")
    summary.append("=" * 60)

    return "\n".join(summary)


def generate_fio_text_metrics(summary, data):
    """Add fio metrics to text summary."""
    if not data or "jobs" not in data:
        summary.append("  No fio data available")
        return

    for job in data["jobs"]:
        job_name = job.get("name", "unknown")
        summary.append(f"\n  Job: {job_name}")
        summary.append("")

        read_data = job.get("read", {})
        write_data = job.get("write", {})

        if read_data:
            summary.append("  READ:")
            bw = read_data.get("bandwidth", "-")
            summary.append(f"    Bandwidth:    {bw}")
            iops = read_data.get("IOPS", "-")
            if isinstance(iops, (int, float)):
                iops = f"{iops:,.2f}"
            summary.append(f"    IOPS:         {iops}")
            lat = read_data.get("latency", {})
            lat_mean = lat.get('mean', '-')
            lat_min = lat.get('min', '-')
            lat_max = lat.get('max', '-')
            if isinstance(lat_mean, float):
                lat_mean = f"{lat_mean:.2f}"
            if isinstance(lat_min, float):
                lat_min = f"{lat_min:.2f}"
            if isinstance(lat_max, float):
                lat_max = f"{lat_max:.2f}"
            summary.append(f"    Latency Mean: {lat_mean} us")
            summary.append(f"    Latency Min:  {lat_min} us")
            summary.append(f"    Latency Max:  {lat_max} us")

        if write_data:
            summary.append("  WRITE:")
            bw = write_data.get("bandwidth", "-")
            summary.append(f"    Bandwidth:    {bw}")
            iops = write_data.get("IOPS", "-")
            if isinstance(iops, (int, float)):
                iops = f"{iops:,.2f}"
            summary.append(f"    IOPS:         {iops}")
            lat = write_data.get("latency", {})
            lat_mean = lat.get('mean', '-')
            lat_min = lat.get('min', '-')
            lat_max = lat.get('max', '-')
            if isinstance(lat_mean, float):
                lat_mean = f"{lat_mean:.2f}"
            if isinstance(lat_min, float):
                lat_min = f"{lat_min:.2f}"
            if isinstance(lat_max, float):
                lat_max = f"{lat_max:.2f}"
            summary.append(f"    Latency Mean: {lat_mean} us")
            summary.append(f"    Latency Min:  {lat_min} us")
            summary.append(f"    Latency Max:  {lat_max} us")


def generate_vdbench_text_metrics(summary, data):
    """Add vdbench metrics to text summary."""
    metrics = data.get("metrics", {}) if data else {}

    if not metrics:
        summary.append("  No vdbench metrics extracted")
        return

    for key in ["throughput", "IOPS", "response_time"]:
        avg_key = f"{key}_avg"
        if avg_key in metrics:
            summary.append(f"  {key.capitalize()}:")
            summary.append(f"    Average: {metrics[avg_key]:.2f}")
            summary.append(f"    Min:      {metrics.get(f'{key}_min', '-'):.2f}")
            summary.append(f"    Max:      {metrics.get(f'{key}_max', '-'):.2f}")


def generate_mdtest_text_metrics(summary, data):
    """Add mdtest metrics to text summary."""
    metrics = data.get("metrics", {}) if data else {}

    if not metrics:
        summary.append("  No mdtest metrics extracted")
        return

    for key in ["create_rate", "remove_rate"]:
        avg_key = f"{key}_avg"
        if avg_key in metrics:
            summary.append(f"  {key.replace('_', ' ').capitalize()}:")
            summary.append(f"    Average: {metrics[avg_key]:.2f} items/sec")
            summary.append(f"    Min:      {metrics.get(f'{key}_min', '-'):.2f}")
            summary.append(f"    Max:      {metrics.get(f'{key}_max', '-'):.2f}")


# ==============================================================================
# Main
# ==============================================================================

def main():
    args = parse_args()

    output_dir = args.output_dir
    tool = args.tool
    scenario = args.scenario
    mount = args.mount

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

    # Generate HTML report
    html_report = generate_html_report(tool, output_dir, data, scenario, mount)
    html_path = os.path.join(output_dir, "report.html")
    with open(html_path, "w") as f:
        f.write(html_report)
    print(f"HTML report generated: {html_path}")

    # Generate text summary
    text_summary = generate_text_summary(tool, output_dir, data, scenario, mount)
    txt_path = os.path.join(output_dir, "summary.txt")
    with open(txt_path, "w") as f:
        f.write(text_summary)
    print(f"Text summary generated: {txt_path}")

    print("\nReport generation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
