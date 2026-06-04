"""Guided calibration: measure a device with a smart plug over MQTT.

``powerguess-calibrate`` walks you through measuring your device's real idle and
peak power using any MQTT smart plug (Tasmota, Shelly, ESPHome, Zigbee2MQTT, …)
as the meter, then writes a ``calibration.json`` PowerGuess can use. The plug is
ground truth; the wizard just reads it while prompting you to idle the device and
then load it.

The MQTT/parsing helpers and the number-crunching are importable and tested; the
``run()`` flow is the thin interactive layer.
"""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import statistics
import subprocess
import sys
import time
from collections import deque
from shutil import which
from typing import List, Optional

from powerguess import Calibration
from powerguess.utils import get_battery_info

LOG = logging.getLogger("powerguess.wizard")


# --- payload parsing (pure) ----------------------------------------------------

def _walk(data, dotted: str):
    """Follow a dotted path through nested dicts, case-insensitively."""
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        if part in cur:
            cur = cur[part]
            continue
        lowered = {k.lower(): k for k in cur}
        if part.lower() in lowered:
            cur = cur[lowered[part.lower()]]
        else:
            return None
    return cur


def parse_power(payload: str, key: Optional[str] = None) -> Optional[float]:
    """Extract watts from an MQTT payload.

    A bare number is used directly. Otherwise the payload is parsed as JSON and
    ``key`` (a dotted path like ``ENERGY.Power``) is read; with no key, common
    power fields are tried.
    """
    payload = (payload or "").strip()
    if not payload:
        return None
    if key:
        try:
            value = _walk(json.loads(payload), key)
            if value is not None:
                return float(value)
        except (ValueError, TypeError):
            pass
    try:
        return float(payload)
    except ValueError:
        pass
    try:
        data = json.loads(payload)
    except ValueError:
        return None
    for candidate in ("ENERGY.Power", "power", "Power", "apower", "watts", "W"):
        value = _walk(data, candidate)
        if value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                continue
    return None


# --- sample summarising (pure) -------------------------------------------------

def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[idx]


def summarise(samples: List[float]) -> dict:
    """Return median / min / p90 / max of a sample window."""
    clean = [s for s in samples if s is not None]
    if not clean:
        return {"n": 0, "median": 0.0, "min": 0.0, "p90": 0.0, "max": 0.0}
    return {
        "n": len(clean),
        "median": round(statistics.median(clean), 2),
        "min": round(min(clean), 2),
        "p90": round(_percentile(clean, 90), 2),
        "max": round(max(clean), 2),
    }


def build_calibration(idle_samples: List[float], load_samples: List[float],
                      voltage: float = 230.0,
                      psu_watts: Optional[float] = None) -> tuple:
    """Build a Calibration from measured windows; return (calibration, warnings).

    Idle uses the median (stable resting draw); load uses the 90th percentile
    (sustained peak, ignoring one-off spikes).
    """
    idle = summarise(idle_samples)
    load = summarise(load_samples)
    warnings: List[str] = []
    if idle["n"] == 0 or load["n"] == 0:
        warnings.append("no plug readings captured — is the power topic correct?")
        return None, warnings

    idle_w = idle["median"]
    load_w = load["p90"]
    if load_w <= idle_w:
        warnings.append("load power is not above idle — did the stress command run?")
    if psu_watts and load_w > psu_watts:
        warnings.append(f"measured peak {load_w} W exceeds the PSU rating "
                        f"{psu_watts} W — check the rating or the meter")
    if psu_watts and load_w < psu_watts * 0.1:
        warnings.append(f"measured peak {load_w} W is under 10% of the {psu_watts} W "
                        f"PSU — the plug may be reporting standby only")

    cal = Calibration(idle_power=idle_w, load_power=max(load_w, idle_w),
                      voltage=voltage, source="manual")
    return cal, warnings


# --- MQTT meter ----------------------------------------------------------------

class MQTTPowerMeter:
    """Subscribe to a smart-plug power topic and expose the latest watts."""

    def __init__(self, host: str, port: int, topic: str, key: Optional[str] = None,
                 user: Optional[str] = None, password: Optional[str] = None,
                 client=None):
        from ._mqtt import new_client
        self.topic = topic
        self.key = key
        self._latest: Optional[float] = None
        self._buf: deque = deque(maxlen=600)
        self._host, self._port = host, port
        self.client = client or new_client("powerguess-calibrate")
        if client is None and user and password:
            self.client.username_pw_set(user, password)
        self.client.on_message = self._on_message

    def _on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode("utf-8")
        except Exception:
            return
        watts = parse_power(payload, self.key)
        if watts is not None:
            self._latest = watts
            self._buf.append(watts)

    def connect(self) -> None:
        self.client.connect(self._host, self._port)
        self.client.subscribe(self.topic)
        self.client.loop_start()

    def disconnect(self) -> None:
        try:
            self.client.loop_stop()
        except Exception:
            pass
        self.client.disconnect()

    def latest(self) -> Optional[float]:
        return self._latest

    def wait_for_reading(self, timeout: float = 15.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._latest is not None:
                return True
            time.sleep(0.25)
        return False

    def sample(self, seconds: float, on_tick=None) -> List[float]:
        """Collect the latest reading once per second for ``seconds``."""
        out: List[float] = []
        for remaining in range(int(seconds), 0, -1):
            if self._latest is not None:
                out.append(self._latest)
            if on_tick:
                on_tick(remaining, self._latest)
            time.sleep(1.0)
        return out


# --- battery meter (no smart plug) ---------------------------------------------

class BatteryMeter:
    """Use the laptop battery's discharge rails as a whole-device power meter.

    Only valid while the device runs on battery (``Discharging``); on AC the
    battery is bypassed and reports nothing useful.
    """

    def _battery(self) -> Optional[dict]:
        bats = list(get_battery_info())
        return bats[0] if bats else None

    def discharging(self) -> bool:
        b = self._battery()
        return bool(b and b["status"] == "Discharging")

    def voltage(self) -> float:
        b = self._battery()
        return b["voltage"] if b and b["voltage"] else 11.1

    def read(self) -> Optional[float]:
        b = self._battery()
        if b and b["status"] == "Discharging" and b["power"]:
            return b["power"]
        return None


def _busy_until(deadline: float) -> None:  # pragma: no cover - runs in a child proc
    while time.time() < deadline:
        pass


def generate_load(seconds: float, workers: Optional[int] = None):
    """Spin every core with a busy loop for ``seconds``; returns the processes."""
    workers = workers or os.cpu_count() or 1
    deadline = time.time() + seconds
    procs = [multiprocessing.Process(target=_busy_until, args=(deadline,))
             for _ in range(workers)]
    for p in procs:
        p.start()
    return procs


_GPU_LOAD_SNIPPET = """
import sys, time
try:
    import torch
    if not torch.cuda.is_available():
        sys.exit(2)
except Exception:
    sys.exit(2)
end = time.time() + float(sys.argv[1])
dev = torch.device("cuda")
a = torch.randn(4096, 4096, device=dev)
b = torch.randn(4096, 4096, device=dev)
while time.time() < end:
    c = a @ b
    torch.cuda.synchronize()
"""


def generate_gpu_load(seconds: float):
    """Drive the GPU with a CUDA matmul loop (via torch, in a subprocess).

    Returns the Popen, or ``None`` if torch/CUDA isn't usable. A subprocess
    avoids the CUDA-after-fork problems of multiprocessing.
    """
    try:
        proc = subprocess.Popen([sys.executable, "-c", _GPU_LOAD_SNIPPET, str(seconds)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return None
    time.sleep(1.5)  # let torch import + CUDA init; bail if it exited (no GPU)
    if proc.poll() is not None:
        return None
    return proc


def gpu_power_draw() -> Optional[float]:
    """Current GPU power draw in watts via nvidia-smi, or None."""
    if not which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4)
        if out.returncode == 0:
            return float(out.stdout.strip().split("\n")[0])
    except (ValueError, OSError):
        pass
    return None


def _sample(meter, seconds: float, on_tick=None) -> List[float]:
    out: List[float] = []
    for remaining in range(int(seconds), 0, -1):
        value = meter.read()
        if value is not None:
            out.append(value)
        if on_tick:
            on_tick(remaining, value)
        time.sleep(1.0)
    return out


def autocalibrate_battery(idle_seconds: int = 20, load_seconds: int = 25,
                          ramp: float = 2.0, gpu: bool = True, on_tick=None):
    """Calibrate automatically using the battery as the meter — no smart plug.

    Measures idle, then loads every CPU core (and the GPU, if available) itself
    and measures the peak. Returns ``(calibration, warnings, summary)``. Requires
    the device to be on battery.
    """
    meter = BatteryMeter()
    if not meter.discharging():
        return None, ["the laptop is on AC — unplug it so the battery becomes the "
                      "meter, then run this again"], {}

    idle = _sample(meter, idle_seconds, on_tick)

    duration = load_seconds + ramp + 1
    gpu_proc = generate_gpu_load(duration) if gpu else None
    cpu_procs = generate_load(duration)
    time.sleep(ramp)  # let CPU + GPU load ramp up before sampling
    load = _sample(meter, load_seconds, on_tick)
    for p in cpu_procs:
        p.terminate()
        p.join()
    if gpu_proc is not None:
        gpu_proc.terminate()

    warnings_extra = []
    if gpu and gpu_proc is None:
        warnings_extra.append("GPU load skipped (torch/CUDA not usable) — peak is "
                              "CPU-only")
    cal, warnings = build_calibration(idle, load, voltage=meter.voltage())
    return cal, warnings + warnings_extra, {
        "idle": summarise(idle), "load": summarise(load),
        "gpu_loaded": gpu_proc is not None,
    }


# --- interactive flow ----------------------------------------------------------

def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def _suggest_load_command() -> str:
    if which("stress-ng"):
        return "stress-ng --cpu $(nproc) --timeout 40s"
    if which("stress"):
        return "stress --cpu $(nproc) --timeout 40s"
    return "for i in $(seq $(nproc)); do yes > /dev/null & done   # Ctrl-C / kill %1.. to stop"


def run() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from .config import Config

    print("PowerGuess calibration wizard")
    print("Measure your device with an MQTT smart plug, then save a calibration.\n")

    host = _ask("MQTT broker host", Config.MQTT_HOST)
    port = int(_ask("MQTT broker port", str(Config.MQTT_PORT)))
    user = _ask("MQTT username (blank for none)", Config.MQTT_USER or "")
    password = _ask("MQTT password (blank for none)", Config.MQTT_PASSWORD or "")
    topic = _ask("Smart-plug power topic", "tele/plug/SENSOR")
    key = _ask("JSON key for watts (blank if the payload is a bare number)",
               "ENERGY.Power")
    voltage = float(_ask("Supply voltage (230 mains EU, 120 mains US, 5 USB)", "230"))
    psu_raw = _ask("PSU rated watts (optional, for a sanity check)", "")
    psu_watts = float(psu_raw) if psu_raw else None

    meter = MQTTPowerMeter(host, port, topic, key=key,
                           user=user or None, password=password or None)
    print(f"\nConnecting to {host}:{port}, listening on {topic} …")
    try:
        meter.connect()
    except Exception as exc:  # noqa: BLE001
        print(f"could not connect to MQTT: {exc}")
        return 1

    if not meter.wait_for_reading():
        print("No power readings arrived. Check the topic and that the plug is "
              "publishing, then re-run.")
        meter.disconnect()
        return 1
    print(f"Reading the plug: {meter.latest()} W now.\n")

    def tick(remaining, value):
        print(f"  {remaining:2d}s … {value} W   ", end="\r", flush=True)

    input("STEP 1/2 — idle (the floor). Leave the device idle and quiet, then press Enter …")
    idle_samples = meter.sample(20, tick)
    idle_summary = summarise(idle_samples)
    print(f"\n  idle ≈ {idle_summary['median']} W  (the lower bound)\n")

    # Peak is the ceiling. Measure it for a tight bound, or fall back to the PSU
    # rating for a loose-but-valid one (see docs/theory.md).
    can_load = _ask("STEP 2/2 — can you put the device under full load now? [Y/n]",
                    "Y").lower() not in ("n", "no")
    if can_load:
        print("In another terminal, run e.g.:")
        print(f"    {_suggest_load_command()}")
        input("Start the load, wait a few seconds, then press Enter …")
        load_samples = meter.sample(20, tick)
        print(f"\n  peak ≈ {summarise(load_samples)['p90']} W  (the upper bound)\n")
        meter.disconnect()
        cal, warnings = build_calibration(idle_samples, load_samples,
                                          voltage=voltage, psu_watts=psu_watts)
    else:
        meter.disconnect()
        if idle_summary["n"] == 0:
            print("  ! no idle readings captured — check the power topic.")
            return 1
        if not psu_watts:
            psu_raw = _ask("Enter the PSU rated watts to use as the upper bound", "")
            psu_watts = float(psu_raw) if psu_raw else None
        if not psu_watts:
            print("  ! need either a load test or a PSU rating to set the upper bound.")
            return 1
        cal = Calibration.from_psu(idle_summary["median"], psu_watts, voltage)
        warnings = ["upper bound is the PSU rating (loose) — run a load test later "
                    "for a tighter estimate"]
        print(f"\n  ceiling = PSU rating {psu_watts} W  (loose upper bound)\n")

    for w in warnings:
        print(f"  ! {w}")
    if cal is None:
        return 1

    out = _ask("Save calibration to", Config.CALIBRATION_FILE or "calibration.json")
    cal.save(out)
    print(f"\nSaved {out}:")
    print(f"  idle {cal.idle_power} W   peak {cal.load_power} W   ({voltage} V)")
    print(f"\nUse it:  CALIBRATION_FILE={out} python -m powerguess")
    return 0


def run_battery(idle_seconds: int = 20, load_seconds: int = 25,
                out: Optional[str] = None, gpu: bool = True) -> int:
    """Automatic, smart-plug-free calibration using the battery as the meter."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from .config import Config

    print("PowerGuess battery auto-calibration (no smart plug)")
    meter = BatteryMeter()
    if not meter.discharging():
        print("\nThe laptop is on AC — the battery can only meter while discharging.")
        print("Unplug the charger, then run:  powerguess-calibrate --battery\n")
        return 1

    load_what = "every CPU core + the GPU" if gpu else "every CPU core"
    print(f"On battery ({meter.voltage():.1f} V). Measuring — leave it idle for "
          f"{idle_seconds}s, then I'll load {load_what} for {load_seconds}s.\n")

    def tick(remaining, value):
        print(f"  {remaining:2d}s … {value if value else '—'} W   ", end="\r", flush=True)

    print("STEP 1/2 — idle (the floor):")
    cal, warnings, summary = autocalibrate_battery(idle_seconds, load_seconds,
                                                   gpu=gpu, on_tick=tick)
    print(f"\n  idle ≈ {summary.get('idle', {}).get('median', 0)} W")
    print(f"  peak ≈ {summary.get('load', {}).get('p90', 0)} W "
          f"(CPU{'+GPU' if summary.get('gpu_loaded') else ''})\n")

    for w in warnings:
        print(f"  ! {w}")
    if cal is None:
        return 1

    out = out or Config.CALIBRATION_FILE or "calibration.json"
    cal.save(out)
    print(f"Saved {out}:  idle {cal.idle_power} W   peak {cal.load_power} W "
          f"({cal.voltage:.1f} V)")
    print(f"\nUse it:  CALIBRATION_FILE={out} python -m powerguess")
    return 0


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="PowerGuess calibration.")
    ap.add_argument("--battery", action="store_true",
                    help="auto-calibrate from the battery meter (laptops; no smart plug)")
    ap.add_argument("--idle-seconds", type=int, default=20)
    ap.add_argument("--load-seconds", type=int, default=25)
    ap.add_argument("--no-gpu", action="store_true", help="don't load the GPU")
    ap.add_argument("--out", default=None, help="calibration output path")
    args = ap.parse_args()
    if args.battery:
        raise SystemExit(run_battery(args.idle_seconds, args.load_seconds,
                                     args.out, gpu=not args.no_gpu))
    raise SystemExit(run())


if __name__ == "__main__":
    main()
