"""Pure parsers never convert missing measurements into zero."""

from __future__ import annotations

import csv
import io
import re


def number(value: str) -> float | None:
    try:
        result = float(value.strip())
        return result if result >= 0 and result < float("inf") else None
    except (ValueError, TypeError):
        return None


def nvidia_csv(output: str) -> list[dict]:
    rows = []
    for cells in csv.reader(io.StringIO(output)):
        if not cells or all(not cell.strip() for cell in cells):
            continue
        if len(cells) != 9:
            raise ValueError("GPU response has an unexpected column count")
        name, driver, total, used, free, usage, temp, index, uuid = [c.strip() for c in cells]
        if not name or len(name) > 180 or not re.fullmatch(r"[0-9.]+", driver):
            raise ValueError("GPU identity is malformed")
        rows.append({"name": name, "driver": driver, "memory_total_mib": number(total),
                     "memory_used_mib": number(used), "memory_free_mib": number(free),
                     "utilization_percent": number(usage), "temperature_celsius": number(temp),
                     "index": int(index) if index.isdecimal() else None})
    return rows


def wsl_list(output: str) -> list[dict]:
    output = output.replace("\x00", "")
    rows = []
    for line in output.splitlines():
        match = re.match(r"^\s*(\*?)\s*(.+?)\s{2,}(\S+)\s+(\d+)\s*$", line)
        if match:
            rows.append({"name": match[2].strip()[:120], "state": match[3][:40],
                         "version": int(match[4]), "default": bool(match[1])})
    return rows
