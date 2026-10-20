"""Informasi kesehatan sistem lokal."""
from __future__ import annotations

import shutil
from pathlib import Path

GIB = 1024 ** 3


def disk_info(path: str | Path) -> dict[str, float]:
    """Return disk capacity information for the filesystem containing *path*."""
    usage = shutil.disk_usage(path)
    total_gb = usage.total / GIB
    free_gb = usage.free / GIB
    return {
        "total_gb": round(total_gb, 2),
        "used_gb": round(usage.used / GIB, 2),
        "free_gb": round(free_gb, 2),
        "used_percent": round((usage.used / usage.total) * 100, 1) if usage.total else 0.0,
    }


def disk_status(free_gb: float) -> str:
    if free_gb < 2.0:
        return "critical"
    if free_gb < 10.0:
        return "warning"
    return "ok"
