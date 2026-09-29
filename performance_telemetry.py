"""Telemetria local e leve de desempenho do MKT.

O arquivo gerado contem apenas uso de recursos e duracoes agregadas. Nenhuma
imagem, key, item, preco ou coordenada e registrada.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from collections import defaultdict
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Any


class _FileTime(ctypes.Structure):
    _fields_ = (("low", ctypes.c_uint32), ("high", ctypes.c_uint32))

    @property
    def value(self) -> int:
        return (int(self.high) << 32) | int(self.low)


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = (
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    )


def _system_times() -> tuple[int, int] | None:
    if os.name != "nt":
        return None
    idle = _FileTime()
    kernel = _FileTime()
    user = _FileTime()
    if not ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        return None
    return idle.value, kernel.value + user.value


def _working_set_mb() -> float | None:
    if os.name != "nt":
        return None
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    handle = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(
        handle, ctypes.byref(counters), counters.cb
    ):
        return None
    return round(counters.WorkingSetSize / (1024 * 1024), 2)


class PerformanceTelemetry:
    """Agrega metricas no caminho critico e grava uma amostra por intervalo."""

    def __init__(self, log_dir: str | os.PathLike[str], interval: float = 5.0):
        self.log_dir = Path(log_dir)
        self.interval = max(0.05, float(interval))
        self.started_at = datetime.now()
        self.path = self.log_dir / f"desempenho-{self.started_at:%Y-%m-%d-%H%M%S}.log"
        self._lock = threading.Lock()
        self._stages: dict[str, dict[str, float]] = defaultdict(
            lambda: {"count": 0.0, "total_ms": 0.0, "max_ms": 0.0}
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_wall = time.perf_counter()
        self._last_process_cpu = time.process_time()
        self._last_system = _system_times()
        self._logical_cpus = max(1, os.cpu_count() or 1)

    def start(self) -> Path:
        if self._thread and self._thread.is_alive():
            return self.path
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._append(
            {
                "type": "session_start",
                "timestamp": self.started_at.isoformat(timespec="milliseconds"),
                "pid": os.getpid(),
                "python": sys.version.split()[0],
                "logical_cpus": self._logical_cpus,
                "interval_seconds": self.interval,
            }
        )
        self._thread = threading.Thread(
            target=self._run,
            name="mkt-performance-telemetry",
            daemon=True,
        )
        self._thread.start()
        return self.path

    def observe(self, stage: str, duration_seconds: float) -> None:
        duration_ms = max(0.0, float(duration_seconds) * 1000.0)
        with self._lock:
            metric = self._stages[str(stage)]
            metric["count"] += 1
            metric["total_ms"] += duration_ms
            metric["max_ms"] = max(metric["max_ms"], duration_ms)

    def sample(self) -> dict[str, Any]:
        now_wall = time.perf_counter()
        now_process = time.process_time()
        elapsed = max(1e-6, now_wall - self._last_wall)
        process_delta = max(0.0, now_process - self._last_process_cpu)
        process_cpu = process_delta / elapsed / self._logical_cpus * 100.0
        self._last_wall = now_wall
        self._last_process_cpu = now_process

        system_cpu: float | None = None
        current_system = _system_times()
        if self._last_system and current_system:
            idle_delta = max(0, current_system[0] - self._last_system[0])
            total_delta = max(0, current_system[1] - self._last_system[1])
            if total_delta:
                system_cpu = (1.0 - idle_delta / total_delta) * 100.0
        self._last_system = current_system

        with self._lock:
            stages = self._stages
            self._stages = defaultdict(
                lambda: {"count": 0.0, "total_ms": 0.0, "max_ms": 0.0}
            )
        summarized = {
            name: {
                "count": int(metric["count"]),
                "average_ms": round(
                    metric["total_ms"] / max(1.0, metric["count"]), 2
                ),
                "max_ms": round(metric["max_ms"], 2),
            }
            for name, metric in stages.items()
        }
        return {
            "type": "sample",
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "process_cpu_percent": round(max(0.0, process_cpu), 2),
            "system_cpu_percent": (
                round(min(100.0, max(0.0, system_cpu)), 2)
                if system_cpu is not None
                else None
            ),
            "working_set_mb": _working_set_mb(),
            "python_threads": threading.active_count(),
            "stages": summarized,
        }

    def stop(self, timeout: float = 1.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(0.0, timeout))

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._append(self.sample())

    def _append(self, payload: dict[str, Any]) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
        except OSError:
            # Diagnostico jamais pode interferir na automacao.
            return


_active_monitor: PerformanceTelemetry | None = None


def start_performance_telemetry(log_dir: str | os.PathLike[str]) -> Path:
    global _active_monitor
    if _active_monitor is None:
        _active_monitor = PerformanceTelemetry(log_dir)
        return _active_monitor.start()
    return _active_monitor.path


def observe_performance(stage: str, duration_seconds: float) -> None:
    monitor = _active_monitor
    if monitor is not None:
        monitor.observe(stage, duration_seconds)
