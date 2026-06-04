"""Host system telemetry: memory, disk, network, uptime, load, fans, processes.

All from psutil/stdlib and published as their own Home Assistant entities.
Anything unavailable on a host (no fan sensor, an unreadable mount, no load
average on non-POSIX) is simply omitted rather than faked — the same
"validated or absent" rule the CPU/GPU/Pi components follow.
"""

from __future__ import annotations

import datetime
import os
import platform
import re
import socket
import time
from typing import Dict, List, Optional, Tuple

import psutil

_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024


def disk_label(path: str) -> str:
    """A stable HA-safe id for a mount path: '/' -> 'root', '/mnt/data' -> 'mnt_data'."""
    p = path.strip().rstrip("/")
    return "root" if p == "" else re.sub(r"[^a-z0-9]+", "_", p.strip("/").lower())


def proc_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower())


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def _fan_rpm() -> Optional[int]:
    """Highest non-zero fan reading (rpm), or None where no fan sensor exists."""
    try:
        for entries in (psutil.sensors_fans() or {}).values():
            for e in entries:
                if e.current and e.current > 0:
                    return int(e.current)
    except Exception:
        pass
    return None


def _boot_iso() -> str:
    try:
        return datetime.datetime.fromtimestamp(psutil.boot_time()).astimezone().isoformat()
    except Exception:
        return ""


class SystemMonitor:
    """Gather host telemetry. Network/disk-IO are rates, so call ``read``
    periodically; the first call seeds the baseline (no rate yet)."""

    def __init__(self, disk_paths: Optional[List[str]] = None,
                 watch_processes: Optional[List[str]] = None):
        self.disks: List[Tuple[str, str]] = [
            (disk_label(p), p) for p in (disk_paths or ["/"]) if p.strip()]
        self.watch: List[str] = [p.strip() for p in (watch_processes or []) if p.strip()]
        self._net: Optional[Tuple[float, int, int]] = None
        self._io: Optional[Tuple[float, int, int]] = None
        self._has_fan = _fan_rpm() is not None

    @property
    def has_fan(self) -> bool:
        return self._has_fan

    def info(self) -> dict:
        """Static host info (published once)."""
        return {
            "os": f"{platform.system()} {platform.release()}".strip(),
            "architecture": platform.machine(),
            "cpu_cores": psutil.cpu_count(logical=True) or 0,
        }

    def read(self) -> dict:
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        out: dict = {
            "ram_percent": round(vm.percent, 1),
            "ram_used_mb": round(vm.used / _MB),
            "ram_total_mb": round(vm.total / _MB),
            "swap_percent": round(sw.percent, 1),
            "uptime": _boot_iso(),
            "cpu_cores": psutil.cpu_count(logical=True) or 0,
        }
        try:
            l1, l5, l15 = os.getloadavg()
            out["load_1"], out["load_5"], out["load_15"] = round(l1, 2), round(l5, 2), round(l15, 2)
        except (OSError, AttributeError):
            pass

        disk: Dict[str, dict] = {}
        for label, path in self.disks:
            try:
                u = psutil.disk_usage(path)
                disk[label] = {"percent": round(u.percent, 1),
                               "free_gb": round(u.free / _GB, 1),
                               "total_gb": round(u.total / _GB, 1)}
            except OSError:
                continue
        if disk:
            out["disk"] = disk

        now = time.time()
        try:
            n = psutil.net_io_counters()
            if self._net and now > self._net[0]:
                dt = now - self._net[0]
                out["net_tx_kbps"] = round((n.bytes_sent - self._net[1]) / dt / 1024, 1)
                out["net_rx_kbps"] = round((n.bytes_recv - self._net[2]) / dt / 1024, 1)
            self._net = (now, n.bytes_sent, n.bytes_recv)
        except Exception:
            pass
        try:
            d = psutil.disk_io_counters()
            if d:
                if self._io and now > self._io[0]:
                    dt = now - self._io[0]
                    out["disk_read_kbps"] = round((d.read_bytes - self._io[1]) / dt / 1024, 1)
                    out["disk_write_kbps"] = round((d.write_bytes - self._io[2]) / dt / 1024, 1)
                self._io = (now, d.read_bytes, d.write_bytes)
        except Exception:
            pass

        ip = _local_ip()
        if ip:
            out["local_ip"] = ip
        if self._has_fan:
            rpm = _fan_rpm()
            if rpm is not None:
                out["fan_rpm"] = rpm
        return out

    def processes(self) -> Dict[str, bool]:
        """For each watched name, whether a matching process is running
        (substring match against process name + cmdline)."""
        if not self.watch:
            return {}
        haystacks: List[str] = []
        for p in psutil.process_iter(["name", "cmdline"]):
            try:
                name = p.info.get("name") or ""
                cmd = " ".join(p.info.get("cmdline") or [])
                haystacks.append(f"{name} {cmd}".lower())
            except Exception:
                continue
        return {w: any(w.lower() in h for h in haystacks) for w in self.watch}
