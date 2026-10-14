"""Normalize completed fio and elbencho results without hiding missing metrics."""

import json
import math
from pathlib import Path
import re


_MIB = 1024 ** 2
_MODE_DIRECTIONS = {
    "read": ("read",), "seq_read": ("read",),
    "randread": ("read",), "rand_read": ("read",),
    "write": ("write",), "seq_write": ("write",),
    "randwrite": ("write",), "rand_write": ("write",),
    "rw": ("read", "write"), "readwrite": ("read", "write"),
    "randrw": ("read", "write"), "seq_mixed": ("read", "write"),
    "rand_mixed": ("read", "write"), "mixed": ("read", "write"),
}


def _number(value, name, integer=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"invalid {name}: expected a nonnegative number")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"invalid {name}: expected a finite nonnegative number")
    if integer:
        try:
            exact = int(value)
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"invalid {name}: expected an integer") from exc
        if isinstance(value, float) and exact != value:
            raise ValueError(f"invalid {name}: expected an integer")
        return exact
    return number


def _mapping(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"invalid {name}: expected an object")
    return value


def _fio_components(document, directions):
    jobs = _mapping(document, "fio result").get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("fio result contains no jobs")
    components = []
    for job in jobs:
        job = _mapping(job, "fio job")
        if _number(job.get("error", 0), "fio job error", integer=True):
            raise ValueError("fio reported a job error")
        for direction in ("read", "write"):
            values = _mapping(job.get(direction, {}), "fio " + direction)
            count = _number(values.get("io_bytes", 0), "fio io_bytes", integer=True)
            for field in ("short_ios", "drop_ios"):
                if _number(values.get(field, 0), "fio " + field, integer=True):
                    raise ValueError("fio reported incomplete I/O")
            bandwidth = (_number(values["bw_bytes"], "fio bw_bytes")
                         if "bw_bytes" in values else
                         _number(values.get("bw", 0), "fio bw") * 1024)
            iops = _number(values.get("iops", 0), "fio iops")
            latency = None
            latency_count = None
            if "lat_ns" in values:
                latency_data = _mapping(values["lat_ns"], "fio latency")
                if "mean" in latency_data:
                    latency = _number(latency_data["mean"], "fio latency mean") / 1000
                if "N" in latency_data:
                    latency_count = _number(latency_data["N"], "fio latency count", integer=True)
            if "total_ios" in values:
                latency_count = _number(values["total_ios"], "fio total_ios", integer=True)
            if not count:
                if bandwidth or iops:
                    raise ValueError("fio has rates without completed bytes")
                continue
            if direction not in directions:
                raise ValueError("fio result contains an unexpected I/O direction")
            if not ("bw_bytes" in values or "bw" in values) or "iops" not in values:
                raise ValueError("fio result is missing bandwidth or IOPS")
            components.append((direction, count, bandwidth, iops, latency, latency_count))
    return components


def _elbencho_components(text, directions):
    phases = []
    for line in text.splitlines():
        if line.strip():
            value = json.loads(line)
            phases.extend(value if isinstance(value, list) else [value])
    matching = []
    mixed = len(directions) == 2
    for phase in phases:
        phase = _mapping(phase, "elbencho phase")
        phase_type = str(phase.get("phase_type", "")).upper()
        if ((mixed and re.fullmatch(r"RWMIX\d+", phase_type)) or
                (not mixed and phase_type == directions[0].upper())):
            matching.append(phase)
    if len(matching) != 1:
        raise ValueError("elbencho result must contain one completed matching data phase")
    phase = matching[0]
    values = _mapping(phase.get("last_done"), "elbencho last_done")
    config = _mapping(phase.get("config", {}), "elbencho config")
    block_size = _number(config.get("block_size", 0), "elbencho block_size", integer=True)
    latency_root = _mapping(values.get("latency", {}), "elbencho latency")
    latency_io = _mapping(latency_root.get("IO", {}), "elbencho IO latency")
    components = []
    for direction in directions:
        data = (_mapping(values.get("rwmix_read", {}), "elbencho mixed read")
                if mixed and direction == "read" else values)
        latency_data = (_mapping(latency_io.get("rwmix_read", {}), "elbencho read latency")
                        if mixed and direction == "read" else latency_io)
        count = _number(data.get("bytes", 0), "elbencho bytes", integer=True)
        bandwidth = _number(data.get("bytes/s", 0), "elbencho bytes/s")
        iops = _number(data.get("iops", 0), "elbencho iops")
        latency = (_number(latency_data["avg_us"], "elbencho latency avg_us")
                   if "avg_us" in latency_data else None)
        if not count:
            if bandwidth or iops:
                raise ValueError("elbencho has rates without completed bytes")
            continue
        if "bytes/s" not in data or "iops" not in data:
            raise ValueError("elbencho result is missing bandwidth or IOPS")
        # Fixed block size gives operation counts; absent it, the two directions
        # have the same time window, so their IOPS provide equivalent weights.
        weight = count / block_size if block_size else iops
        components.append((direction, count, bandwidth, iops, latency, weight))
    return components


def parse_metrics(tool, result_path, mode):
    """Return bytes, MiB/s, IOPS and operation-weighted mean latency in us.

    Result byte counts cover read + write for mixed workloads. Latency is None
    when any active component lacks a usable latency/count measurement.
    """
    directions = _MODE_DIRECTIONS.get(mode.replace("-", "_"))
    if directions is None:
        raise ValueError("unsupported performance mode: " + mode)
    text = Path(result_path).read_text()
    if tool == "fio":
        components = _fio_components(json.loads(text), directions)
    elif tool == "elbencho":
        components = _elbencho_components(text, directions)
    else:
        raise ValueError("unsupported performance tool: " + tool)
    if not components:
        raise ValueError("result contains no completed I/O")
    read_rate = math.fsum(c[2] for c in components if c[0] == "read") / _MIB
    write_rate = math.fsum(c[2] for c in components if c[0] == "write") / _MIB
    latency = None
    if all(c[4] is not None and c[5] for c in components):
        latency = math.fsum(c[4] * c[5] for c in components) / math.fsum(c[5] for c in components)
    result = {
        "io_bytes": sum(c[1] for c in components),
        "bandwidth_mib_s": read_rate + write_rate,
        "read_mib_s": read_rate,
        "write_mib_s": write_rate,
        "iops": math.fsum(c[3] for c in components),
        "latency_mean_us": latency,
    }
    for key, value in result.items():
        if value is not None:
            _number(value, key)
    return result
