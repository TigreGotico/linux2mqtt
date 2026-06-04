"""CLI entry point: stream power readings to MQTT / Home Assistant."""

from __future__ import annotations

import json
import logging
import signal
import sys
import time
from typing import Any, Optional

from powerguess import AutoCalibrator, Calibration, PowerStatMonitor, Reading

from .config import Config
from .mqtt_client import MQTTClient
from .version import __version__

LOG = logging.getLogger("linux2mqtt")


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    )


def _build_ina219():
    if not Config.USE_INA219:
        return None
    try:
        from powerguess.ina219 import INA219
        return INA219(bus=Config.INA219_BUS, address=Config.INA219_ADDRESS,
                      shunt_ohms=Config.INA219_SHUNT_OHMS)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("INA219 unavailable (%s); falling back to other sources", exc)
        return None


def _build_cpu():
    if not Config.USE_CPU:
        return None, False
    from .cpu import CPUMonitor
    cpu = CPUMonitor()
    if cpu.power_available():
        LOG.info("CPU package power available via RAPL")
    return cpu, cpu.power_available()


def _build_gpu():
    if not Config.USE_GPU:
        return None, False
    try:
        from .gpu import NvidiaGPU
        if NvidiaGPU.available():
            gpu = NvidiaGPU(index=Config.GPU_INDEX)
            first = gpu.read()
            if first is not None:
                LOG.info("GPU detected: %s (power %s)", first.name,
                         "available" if first.power_valid else "unreliable — not published")
                return gpu, first.power_valid
    except Exception as exc:  # noqa: BLE001
        LOG.debug("GPU telemetry unavailable: %s", exc)
    return None, False


def _build_predictor():
    if not Config.MODEL_FILE:
        return None
    try:
        from powerguess.model import LinearPredictor
        return LinearPredictor.load(Config.MODEL_FILE)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("model %s failed to load (%s); using the curve estimate",
                    Config.MODEL_FILE, exc)
        return None


def main() -> None:
    setup_logging()
    LOG.info("linux2mqtt %s starting", __version__)

    calibration: Optional[Calibration] = (
        Calibration.from_env() or Calibration.load(Config.CALIBRATION_FILE))
    auto = AutoCalibrator(Config.CALIBRATION_FILE) if Config.AUTO_CALIBRATE else None

    from powerguess import pmic
    from . import rpi
    # vcgencmd present (any Pi) -> throttling/undervoltage sensors.
    has_rpi = Config.USE_RPI and rpi.available()
    # PMIC ADC power is Pi 5 only (powerguess owns it as a measured total source);
    # probe once so we don't poll a failing call every cycle on a Pi 3/4.
    has_pmic = has_rpi and pmic.pmic_available()
    if has_rpi:
        LOG.info("Raspberry Pi: throttling sensors on; PMIC board power %s",
                 "available (Pi 5)" if has_pmic else "unavailable (Pi 3/4 — use an INA219 HAT)")

    monitor = PowerStatMonitor(
        smooth=Config.SMOOTH,
        time_between_measures=Config.MEASURE_INTERVAL,
        calibration=calibration,
        auto_calibrator=auto,
        ina219=_build_ina219(),
        pmic=has_pmic,
        predictor=_build_predictor(),
        prefer_battery=Config.PREFER_BATTERY,
        use_powerstat=Config.USE_POWERSTAT,
        energy_file=Config.ENERGY_FILE or None,
    )

    cpu, cpu_power_ok = _build_cpu()
    gpu, gpu_power_ok = _build_gpu()

    sysmon = None
    if Config.USE_SYSTEM:
        from .system import SystemMonitor
        sysmon = SystemMonitor(disk_paths=Config.DISK_PATHS,
                               watch_processes=Config.WATCH_PROCESSES)
        LOG.info("System telemetry: disks=%s, watching=%s, fan=%s",
                 [p for _, p in sysmon.disks], sysmon.watch or "none", sysmon.has_fan)

    mqtt_client = MQTTClient(has_battery=monitor.has_battery,
                             has_gpu=gpu is not None, has_gpu_power=gpu_power_ok,
                             has_cpu=cpu is not None, has_cpu_power=cpu_power_ok,
                             has_rpi=has_rpi,
                             has_system=sysmon is not None,
                             disks=sysmon.disks if sysmon else [],
                             watch_processes=sysmon.watch if sysmon else [],
                             has_fan=sysmon.has_fan if sysmon else False)
    mqtt_client.connect()
    mqtt_client.publish_model(monitor.model)
    if sysmon:
        mqtt_client.publish_system_info(sysmon.info())

    dataset_fh = open(Config.DATASET_FILE, "a") if Config.DATASET_FILE else None

    def on_reading(reading: Reading) -> None:
        gpu_reading = gpu.read() if gpu is not None else None
        if mqtt_client.publish_reading(reading, energy_wh=monitor.energy_wh,
                                       bounds=monitor.bounds()):
            LOG.debug("%.2f W [%s] energy=%.4f kWh", reading.power, reading.source,
                      monitor.energy_wh / 1000)
            if monitor.has_battery:
                mqtt_client.publish_battery(monitor.get_battery())
            if gpu_reading is not None:
                mqtt_client.publish_gpu(gpu_reading)
            if cpu is not None:
                mqtt_client.publish_cpu(cpu.read())
            if has_rpi:
                mqtt_client.publish_rpi(rpi.soc_telemetry())
            if sysmon is not None:
                mqtt_client.publish_system(sysmon.read())
                mqtt_client.publish_procs(sysmon.processes())
        if dataset_fh and reading.measured:
            from powerguess.model import current_features, device_arch
            dataset_fh.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "arch": device_arch(), "model": monitor.model or "unknown",
                **current_features(monitor), "source": reading.source,
                "watts": round(reading.power, 3),
            }) + "\n")
            dataset_fh.flush()

    monitor.add_callback(on_reading)

    def _shutdown(signum: int, frame: Any) -> None:
        LOG.info("Received signal %s, shutting down", signum)
        monitor.stop()
        mqtt_client.disconnect()
        if dataset_fh:
            dataset_fh.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    monitor.start()
    LOG.info("linux2mqtt running — model %r, battery=%s, ina219=%s",
             monitor.model or "generic", monitor.has_battery, monitor.ina is not None)

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT, None)


if __name__ == "__main__":
    main()
