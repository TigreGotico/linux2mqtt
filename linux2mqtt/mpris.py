"""MPRIS now-playing + transport control via ``playerctl``.

Exposes the active media player's status and metadata (read) and play-pause /
next / previous (control, via MQTT button command topics). Inactive — no entities
— when ``playerctl`` is missing or no player is present.
"""

from __future__ import annotations

import subprocess
from shutil import which
from typing import Optional

_COMMANDS = {"play_pause": "play-pause", "next": "next", "previous": "previous"}


def _run(args) -> Optional[str]:
    try:
        out = subprocess.run(["playerctl", *args], capture_output=True, text=True,
                             timeout=5)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


class MPRISMonitor:
    def __init__(self):
        self._has = bool(which("playerctl"))

    @property
    def available(self) -> bool:
        # playerctl present and at least one player has ever registered.
        return self._has and _run(["status"]) is not None

    def read(self) -> dict:
        status = _run(["status"]) or "No player"
        meta = _run(["metadata", "--format",
                     "{{title}}\t{{artist}}\t{{album}}"]) or ""
        title, artist, album = (meta.split("\t") + ["", "", ""])[:3]
        return {"status": status, "title": title, "artist": artist, "album": album}

    def command(self, action: str) -> None:
        verb = _COMMANDS.get(action)
        if verb:
            _run([verb])
