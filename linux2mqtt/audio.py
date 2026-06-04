"""Audio server status + volume/mute, read and controllable.

Detects the running audio server (PipeWire / PulseAudio / ALSA) and exposes the
default sink (output) and source (microphone) volume and mute — both as readable
state and as controllable entities (HA number/switch via MQTT command topics).

Backends, in preference order:
- ``pactl`` — PulseAudio *and* PipeWire (via pipewire-pulse), the common case.
- ``amixer`` — ALSA-only hosts.

Returns "unavailable" cleanly on a headless box with no audio server, so the
entities simply don't appear — the same validated-or-absent rule as elsewhere.
"""

from __future__ import annotations

import re
import subprocess
from shutil import which
from typing import Optional

_PCT = re.compile(r"(\d+)%")
_SINK = "@DEFAULT_SINK@"
_SOURCE = "@DEFAULT_SOURCE@"


def _run(cmd) -> Optional[str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _pct(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = _PCT.search(text)
    return int(m.group(1)) if m else None


class AudioMonitor:
    def __init__(self):
        self._server: Optional[str] = None
        self._backend: Optional[str] = None
        self._detect()

    def _detect(self) -> None:
        if which("pactl"):
            info = _run(["pactl", "info"])
            if info is not None:
                self._server = "pipewire" if "PipeWire" in info else "pulseaudio"
                self._backend = "pactl"
                return
        if which("amixer"):
            self._server, self._backend = "alsa", "amixer"
            return

    @property
    def available(self) -> bool:
        return self._backend is not None

    @property
    def server(self) -> Optional[str]:
        return self._server

    # --- read -----------------------------------------------------------------

    def read(self) -> dict:
        out: dict = {"server": self._server}
        if self._backend == "pactl":
            out["volume"] = _pct(_run(["pactl", "get-sink-volume", _SINK]))
            out["mute"] = self._pactl_mute("get-sink-mute", _SINK)
            out["mic_volume"] = _pct(_run(["pactl", "get-source-volume", _SOURCE]))
            out["mic_mute"] = self._pactl_mute("get-source-mute", _SOURCE)
        elif self._backend == "amixer":
            out["volume"], out["mute"] = self._amixer_get("Master")
            out["mic_volume"], out["mic_mute"] = self._amixer_get("Capture")
        return {k: v for k, v in out.items() if v is not None}

    def _pactl_mute(self, cmd: str, target: str) -> Optional[bool]:
        r = _run(["pactl", cmd, target])
        return ("yes" in r.lower()) if r else None

    def _amixer_get(self, control: str):
        r = _run(["amixer", "get", control])
        if not r:
            return None, None
        vol = _pct(r)
        mute = "[off]" in r if "[on]" in r or "[off]" in r else None
        return vol, mute

    # --- control --------------------------------------------------------------

    def set_volume(self, pct: int) -> None:
        self._set_volume(_SINK, "Master", pct)

    def set_mic_volume(self, pct: int) -> None:
        self._set_volume(_SOURCE, "Capture", pct)

    def set_mute(self, on: bool) -> None:
        self._set_mute(_SINK, "Master", on, "set-sink-mute")

    def set_mic_mute(self, on: bool) -> None:
        self._set_mute(_SOURCE, "Capture", on, "set-source-mute")

    def _set_volume(self, sink: str, control: str, pct: int) -> None:
        pct = max(0, min(100, int(pct)))
        if self._backend == "pactl":
            sub = "set-sink-volume" if sink == _SINK else "set-source-volume"
            _run(["pactl", sub, sink, f"{pct}%"])
        elif self._backend == "amixer":
            _run(["amixer", "set", control, f"{pct}%"])

    def _set_mute(self, sink: str, control: str, on: bool, pactl_cmd: str) -> None:
        if self._backend == "pactl":
            _run(["pactl", pactl_cmd, sink, "1" if on else "0"])
        elif self._backend == "amixer":
            _run(["amixer", "set", control, "mute" if on else "unmute"])
