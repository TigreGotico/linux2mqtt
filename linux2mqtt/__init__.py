"""linux2mqtt — publish Linux/SBC system metrics to MQTT for Home Assistant.

A homelab bridge: whole-device **power** (via the [powerguess](https://github.com/TigreGotico/powerguess)
library — measured or estimated, with provenance) plus **system telemetry** as
their own Home Assistant entities:

- CPU — utilization, frequency, temperature, and package power (RAPL)
- GPU — utilization, temperature, VRAM, and validated power (NVIDIA)
- Raspberry Pi — throttling, overheating, overclocking, undervoltage
- energy (kWh) and cost

Run ``python -m linux2mqtt`` (or the ``linux2mqtt`` console script) with MQTT
settings in the environment; entities appear via MQTT discovery.
"""
from linux2mqtt.version import __version__

__all__ = ["__version__"]
