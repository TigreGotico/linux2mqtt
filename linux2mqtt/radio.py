"""WiFi / Bluetooth scanning — RF environment, presence, and a geolocation
fingerprint for downstream consumers (e.g. ingeo).

- Connected WiFi (SSID + signal) is cheap and read every cycle.
- WiFi and Bluetooth *scans* are expensive and briefly disrupt the radio, so
  they run on a slow cadence (``RADIO_SCAN_INTERVAL``, default 300 s). The full
  AP / device lists are published as JSON (HA sensor attributes + dedicated
  topics) so a geolocation service can turn the BSSID/RSSI fingerprint into a
  position.
- Watched Bluetooth MACs become presence binary sensors (phone near = home).

Backends: ``nmcli`` (WiFi) and ``bluetoothctl`` (Bluetooth). Inactive — no
entities — on a host with no radio or tooling (e.g. a wired server).
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from shutil import which
from typing import Callable, Dict, List, Optional

_log = logging.getLogger(__name__)

_UNESCAPED_COLON = re.compile(r"(?<!\\):")
_BT_DEVICE = re.compile(r"Device\s+([0-9A-Fa-f:]{17})\s+(.*)")


def _run(cmd, timeout=12) -> Optional[str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _nmcli_fields(line: str) -> List[str]:
    """Split an ``nmcli -t`` line on unescaped colons and unescape values
    (BSSIDs contain ``\\:``-escaped colons)."""
    return [f.replace("\\:", ":").replace("\\\\", "\\")
            for f in _UNESCAPED_COLON.split(line)]


def _wifi_available() -> bool:
    if not which("nmcli"):
        return False
    out = _run(["nmcli", "-t", "-f", "TYPE", "device"], timeout=5) or ""
    return any(t.strip() == "wifi" for t in out.splitlines())


def _bt_available() -> bool:
    return bool(which("bluetoothctl")) and bool(_run(["bluetoothctl", "list"], timeout=5))


def _wifi_connected() -> dict:
    out = _run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"], timeout=5)
    for line in (out or "").splitlines():
        f = _nmcli_fields(line)
        if len(f) >= 3 and f[0] == "yes":
            try:
                return {"ssid": f[1], "signal": int(f[2])}
            except ValueError:
                return {"ssid": f[1]}
    return {}


def _wifi_scan() -> List[dict]:
    out = _run(["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,CHAN", "dev", "wifi", "list"])
    nets, seen = [], set()
    for line in (out or "").splitlines():
        f = _nmcli_fields(line)
        if len(f) < 4 or not f[1] or f[1] in seen:
            continue
        seen.add(f[1])
        try:
            nets.append({"ssid": f[0], "bssid": f[1],
                         "signal": int(f[2]), "channel": int(f[3])})
        except ValueError:
            continue
    return nets


def _bt_scan(scan_seconds: int = 8) -> List[dict]:
    _run(["bluetoothctl", "--timeout", str(scan_seconds), "scan", "on"],
         timeout=scan_seconds + 5)
    out = _run(["bluetoothctl", "devices"], timeout=5) or ""
    devices = []
    for line in out.splitlines():
        m = _BT_DEVICE.match(line.strip())
        if m:
            devices.append({"mac": m.group(1).upper(), "name": m.group(2).strip()})
    return devices


class RadioMonitor:
    def __init__(self, watch_bt_macs: Optional[List[str]] = None,
                 scan_interval: int = 300):
        self.scan_interval = scan_interval
        self.watch = [m.strip().upper() for m in (watch_bt_macs or []) if m.strip()]
        self._has_wifi = _wifi_available()
        self._has_bt = _bt_available()
        self._last_scan = 0.0
        self._ap_count = 0
        self._bt_count = 0
        self._scanning = False

    @property
    def has_wifi(self) -> bool:
        return self._has_wifi

    @property
    def has_bt(self) -> bool:
        return self._has_bt

    @property
    def available(self) -> bool:
        return self._has_wifi or self._has_bt

    def connected(self) -> dict:
        """Cheap per-cycle state: connected WiFi + last-scan counts."""
        out: dict = {}
        if self._has_wifi:
            out.update(_wifi_connected())
        out["ap_count"] = self._ap_count
        out["bt_count"] = self._bt_count
        return out

    def due(self) -> bool:
        return not self._scanning and (time.time() - self._last_scan) >= self.scan_interval

    def scan_in_background(self, on_done: Callable[[dict], None]) -> bool:
        """Run ``scan()`` on a daemon thread so callers (e.g. the telemetry
        cadence) are never blocked by the up-to-~25s WiFi+BT scan.

        Returns False (no-op) if a scan is already in flight, else True.
        ``on_done`` is called with the scan result once it completes.
        """
        if self._scanning:
            return False
        self._scanning = True
        self._last_scan = time.time()

        def _run_scan():
            try:
                result = self.scan(_mark_last_scan=False)
                on_done(result)
            except Exception:
                _log.exception("radio scan failed")
            finally:
                self._scanning = False

        threading.Thread(target=_run_scan, daemon=True, name="radio-scan").start()
        return True

    def scan(self, _mark_last_scan: bool = True) -> dict:
        """Expensive periodic scan. Returns wifi/bt lists + watched presence."""
        if _mark_last_scan:
            self._last_scan = time.time()
        out: dict = {}
        if self._has_wifi:
            nets = _wifi_scan()
            self._ap_count = len(nets)
            out["wifi"] = nets
        if self._has_bt:
            devs = _bt_scan()
            self._bt_count = len(devs)
            out["bt"] = devs
            if self.watch:
                seen = {d["mac"].upper() for d in devs}
                out["presence"] = {m: (m in seen) for m in self.watch}
        return out
