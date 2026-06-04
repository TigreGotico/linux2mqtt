"""MQTT client with Home Assistant MQTT auto-discovery for powerguess."""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from ._mqtt import new_client
from .config import Config
from .system import proc_id as _proc_id
from .version import __version__

LOG = logging.getLogger(__name__)


class MQTTClient:
    """Publishes power readings to MQTT and registers Home Assistant discovery.

    :param has_battery: include the battery sensor group in discovery.
    :param client: inject a pre-built MQTT client (used by tests); a real
        ``paho.mqtt`` client is created when omitted.
    """

    def __init__(self, has_battery: bool = False, has_gpu: bool = False,
                 has_gpu_power: bool = False, has_cpu: bool = False,
                 has_cpu_power: bool = False, has_rpi: bool = False,
                 has_system: bool = False, disks=None, watch_processes=None,
                 has_fan: bool = False, has_audio: bool = False,
                 has_mic: bool = False, has_mpris: bool = False,
                 has_wifi: bool = False, has_bt: bool = False, watch_bt_macs=None,
                 client=None) -> None:
        self._prefix = Config.MQTT_TOPIC_PREFIX
        self._availability = f"{self._prefix}/availability"
        self._has_gpu = has_gpu
        self._has_gpu_power = has_gpu_power
        self._has_cpu = has_cpu
        self._has_cpu_power = has_cpu_power
        self._has_rpi = has_rpi
        self._has_system = has_system
        self._disks = disks or []          # list of (label, path)
        self._watch = watch_processes or []  # list of process names
        self._has_fan = has_fan
        self._has_audio = has_audio
        self._has_mic = has_mic
        self._has_mpris = has_mpris
        self._has_wifi = has_wifi
        self._has_bt = has_bt
        self._watch_bt = watch_bt_macs or []
        self._commands = {}  # topic -> handler(payload_str)
        self.client = client or new_client(Config.MQTT_CLIENT_ID)
        if client is None:
            if Config.MQTT_USER and Config.MQTT_PASSWORD:
                self.client.username_pw_set(Config.MQTT_USER, Config.MQTT_PASSWORD)
            # Reconnect automatically if the broker drops, and tell HA we're gone.
            try:
                self.client.reconnect_delay_set(min_delay=1, max_delay=30)
            except Exception:  # pragma: no cover - older paho
                pass
            self.client.will_set(self._availability, "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self._connected = False
        self._has_battery = has_battery
        self._device_name = Config.DEVICE_NAME
        self._device_id = Config.DEVICE_ID
        self._last_publish = 0.0
        self._last_power = None

    # --- connection -----------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, *args):
        # reason_code is an int (paho 1.x) or ReasonCode (2.x); both == 0 on success.
        if reason_code == 0:
            LOG.info("MQTT connected to %s:%s", Config.MQTT_HOST, Config.MQTT_PORT)
            self._connected = True
            # Announce availability, then (re)publish discovery — important after a
            # reconnect so HA flips the entities back to available.
            self.client.publish(self._availability, "online", qos=1, retain=True)
            if Config.HA_ENABLED:
                self.publish_discovery()
            for topic in self._commands:
                self.client.subscribe(topic)
        else:
            LOG.warning("MQTT connection failed, reason=%s", reason_code)

    def _on_disconnect(self, client, userdata, *args):
        LOG.warning("MQTT disconnected; will auto-reconnect")
        self._connected = False

    def _on_message(self, client, userdata, msg):
        handler = self._commands.get(msg.topic)
        if not handler:
            return
        try:
            handler(msg.payload.decode())
        except Exception as exc:  # noqa: BLE001
            LOG.warning("command on %s failed: %s", msg.topic, exc)

    def register_command(self, topic: str, handler) -> None:
        """Register a handler for an inbound command topic (HA -> device)."""
        self._commands[topic] = handler
        if self._connected:
            self.client.subscribe(topic)

    def connect(self) -> None:
        LOG.info("Connecting to MQTT broker %s:%s", Config.MQTT_HOST, Config.MQTT_PORT)
        for attempt in range(1, Config.MQTT_RETRY_COUNT + 1):
            try:
                self.client.connect(Config.MQTT_HOST, Config.MQTT_PORT,
                                    keepalive=Config.MQTT_KEEPALIVE)
                self.client.loop_start()
                deadline = time.time() + Config.MQTT_CONNECT_TIMEOUT
                while time.time() < deadline:
                    if self._connected:
                        return
                    time.sleep(0.1)
                LOG.warning("MQTT connection timeout, retrying...")
            except Exception as exc:
                LOG.warning("MQTT connection attempt %s/%s failed: %s",
                            attempt, Config.MQTT_RETRY_COUNT, exc)
                time.sleep(min(2 ** attempt, Config.MQTT_RETRY_MAX_BACKOFF))
        LOG.error("MQTT failed to connect after %s attempts, continuing anyway",
                  Config.MQTT_RETRY_COUNT)

    def disconnect(self) -> None:
        try:
            if self._connected:
                self.client.publish(self._availability, "offline", qos=1, retain=True)
            self.client.loop_stop()
        except Exception:
            pass
        self.client.disconnect()

    # --- state publishing -----------------------------------------------------

    def publish_reading(self, reading, energy_wh: float = 0.0,
                        bounds=None, force: bool = False) -> bool:
        """Publish a :class:`Reading`. Throttled to ``PUBLISH_INTERVAL`` but sent
        early when power moves by more than ``PUBLISH_DELTA`` watts.

        :param bounds: optional ``(floor_w, ceiling_w)`` envelope to publish.
        Returns ``True`` if the reading was published.
        """
        now = time.time()
        moved = (self._last_power is None or Config.PUBLISH_DELTA <= 0
                 or abs(reading.power - self._last_power) >= Config.PUBLISH_DELTA)
        if not force and not moved and now - self._last_publish < Config.PUBLISH_INTERVAL:
            return False
        self._last_publish = now
        self._last_power = reading.power
        energy_kwh = round(energy_wh / 1000.0, 4)
        payload = reading.as_dict()
        payload["energy"] = energy_kwh
        payload["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        if bounds:
            payload["floor"] = round(bounds[0], 3)
            payload["ceiling"] = round(bounds[1], 3)
        if Config.ENERGY_TARIFF > 0:
            payload["cost"] = round(energy_kwh * Config.ENERGY_TARIFF, 4)
        self._publish(f"{self._prefix}/state", json.dumps(payload))
        return True

    def publish_battery(self, battery: Optional[dict]) -> None:
        if not battery:
            return
        charging = battery.get("status") == "Charging"
        self._publish(f"{self._prefix}/battery", json.dumps({
            "level": round(battery.get("capacity", 0), 1),
            "status": battery.get("status", "unknown"),
            "charging": charging,
            "power": round(battery.get("power", 0), 3),
            "voltage": round(battery.get("voltage", 0), 3),
        }))

    def publish_model(self, model: str) -> None:
        self._publish(f"{self._prefix}/model", json.dumps({"model": model or "unknown"}))

    def publish_gpu(self, gpu_reading) -> None:
        if gpu_reading is None:
            return
        self._publish(f"{self._prefix}/gpu", json.dumps(gpu_reading.as_dict()))

    def publish_cpu(self, cpu_reading) -> None:
        if cpu_reading is None:
            return
        self._publish(f"{self._prefix}/cpu", json.dumps(cpu_reading.as_dict()))

    def publish_rpi(self, throttled: dict) -> None:
        if not throttled:
            return
        self._publish(f"{self._prefix}/rpi", json.dumps(throttled))

    def publish_system(self, system: Optional[dict]) -> None:
        if not system:
            return
        self._publish(f"{self._prefix}/system", json.dumps(system))

    def publish_system_info(self, info: Optional[dict]) -> None:
        if not info:
            return
        self.client.publish(f"{self._prefix}/system_info", json.dumps(info),
                            qos=Config.MQTT_QOS, retain=True)

    def publish_procs(self, procs: Optional[dict]) -> None:
        if not procs:
            return
        self._publish(f"{self._prefix}/procs", json.dumps(procs))

    def publish_audio(self, audio: Optional[dict]) -> None:
        if not audio:
            return
        self._publish(f"{self._prefix}/audio", json.dumps(audio))

    def publish_media(self, media: Optional[dict]) -> None:
        if not media:
            return
        self._publish(f"{self._prefix}/media", json.dumps(media))

    def publish_radio(self, radio: Optional[dict]) -> None:
        if not radio:
            return
        self._publish(f"{self._prefix}/wifi", json.dumps(radio))

    def publish_radio_scan(self, scan: Optional[dict]) -> None:
        if not scan:
            return
        if "wifi" in scan:
            self._publish(f"{self._prefix}/wifi_scan",
                          json.dumps({"networks": scan["wifi"]}))
        if "bt" in scan:
            self._publish(f"{self._prefix}/bt_scan",
                          json.dumps({"devices": scan["bt"]}))
        if scan.get("presence"):
            self._publish(f"{self._prefix}/bt_presence", json.dumps(scan["presence"]))

    def _publish(self, topic: str, payload: str) -> None:
        if not self._connected:
            LOG.debug("MQTT not connected, dropping message to %s", topic)
            return
        self.client.publish(topic, payload, qos=Config.MQTT_QOS,
                            retain=Config.MQTT_RETAIN)

    # --- Home Assistant discovery ---------------------------------------------

    def _device(self) -> dict:
        return {
            "identifiers": [self._device_id],
            "name": self._device_name,
            "model": "linux2mqtt",
            "manufacturer": "TigreGotico",
            "sw_version": __version__,
        }

    def publish_discovery(self) -> None:
        """Publish Home Assistant MQTT discovery payloads."""
        device = self._device()
        state = f"{self._prefix}/state"

        self._sensor("Power", "power", state, "{{ value_json.power }}", device,
                     unit="W", device_class="power", state_class="measurement",
                     icon="mdi:flash", precision=1)
        self._sensor("Current", "current", state, "{{ value_json.current }}", device,
                     unit="A", device_class="current", state_class="measurement")
        self._sensor("Voltage", "voltage", state, "{{ value_json.voltage }}", device,
                     unit="V", device_class="voltage", state_class="measurement")
        self._sensor("Energy", "energy", state, "{{ value_json.energy }}", device,
                     unit="kWh", device_class="energy",
                     state_class="total_increasing", icon="mdi:lightning-bolt")
        # Provenance: whether the latest reading is measured or estimated.
        self._sensor("Source", "source", state, "{{ value_json.source }}", device,
                     icon="mdi:check-decagram")
        self._sensor("Error Margin", "error_margin", state,
                     "{{ value_json.error_margin }}", device, unit="W",
                     icon="mdi:plus-minus", precision=1, entity_category="diagnostic")
        # The envelope: idle floor and peak/PSU ceiling the estimate sits between.
        self._sensor("Power Floor", "power_floor", state, "{{ value_json.floor }}",
                     device, unit="W", device_class="power", icon="mdi:arrow-collapse-down")
        self._sensor("Power Ceiling", "power_ceiling", state, "{{ value_json.ceiling }}",
                     device, unit="W", device_class="power", icon="mdi:arrow-collapse-up")
        if Config.ENERGY_TARIFF > 0:
            self._sensor("Cost", "cost", state, "{{ value_json.cost }}", device,
                         unit=Config.CURRENCY, device_class="monetary",
                         state_class="total_increasing", icon="mdi:cash")
        self._sensor("Model", "model", f"{self._prefix}/model",
                     "{{ value_json.model }}", device, icon="mdi:cpu-64-bit",
                     entity_category="diagnostic")

        if self._has_rpi:
            rpi = f"{self._prefix}/rpi"

            def _b(name, key, dclass="problem"):
                self._binary_sensor(name, key, rpi,
                                    "{{ 'ON' if value_json.%s else 'OFF' }}" % key,
                                    device, device_class=dclass)

            # Throttling
            _b("Throttled", "throttled")
            _b("Frequency Capped", "freq_capped")
            _b("Throttling Occurred", "throttled_occurred")
            # Overheating
            _b("Overheating", "soft_temp_limit", dclass="heat")
            _b("Overheating Occurred", "soft_temp_limit_occurred", dclass="heat")
            # Undervoltage (power supply)
            _b("Undervoltage", "undervoltage")
            _b("Undervoltage Occurred", "undervoltage_occurred")
            # Overclocking
            _b("Overclocked", "overclocked", dclass=None)
            self._sensor("ARM Clock", "arm_clock", rpi, "{{ value_json.arm_clock_mhz }}",
                         device, unit="MHz", device_class="frequency",
                         state_class="measurement")
            self._sensor("Configured ARM Freq", "arm_freq_config", rpi,
                         "{{ value_json.arm_freq_config_mhz }}", device, unit="MHz",
                         device_class="frequency", entity_category="diagnostic")
            self._sensor("Over-voltage", "over_voltage", rpi,
                         "{{ value_json.over_voltage }}", device, icon="mdi:flash-alert",
                         entity_category="diagnostic")
            self._sensor("Core Voltage", "core_voltage", rpi,
                         "{{ value_json.core_volts }}", device, unit="V",
                         device_class="voltage", state_class="measurement")

        if self._has_cpu:
            cpu = f"{self._prefix}/cpu"
            self._sensor("CPU Utilization", "cpu_utilization", cpu,
                         "{{ value_json.utilization }}", device, unit="%",
                         state_class="measurement", icon="mdi:cpu-64-bit")
            self._sensor("CPU Frequency", "cpu_frequency", cpu,
                         "{{ value_json.frequency_mhz }}", device, unit="MHz",
                         device_class="frequency", state_class="measurement")
            self._sensor("CPU Temperature", "cpu_temperature", cpu,
                         "{{ value_json.temperature }}", device, unit="°C",
                         device_class="temperature", state_class="measurement")
            if self._has_cpu_power:
                self._sensor("CPU Power", "cpu_power", cpu, "{{ value_json.power }}",
                             device, unit="W", device_class="power",
                             state_class="measurement", icon="mdi:cpu-64-bit", precision=1)

        if self._has_gpu:
            gpu = f"{self._prefix}/gpu"
            self._sensor("GPU Utilization", "gpu_utilization", gpu,
                         "{{ value_json.utilization }}", device, unit="%",
                         state_class="measurement", icon="mdi:expansion-card")
            self._sensor("GPU Temperature", "gpu_temperature", gpu,
                         "{{ value_json.temperature }}", device, unit="°C",
                         device_class="temperature", state_class="measurement")
            self._sensor("GPU Memory", "gpu_memory", gpu,
                         "{{ value_json.memory_percent }}", device, unit="%",
                         state_class="measurement", icon="mdi:memory")
            if self._has_gpu_power:
                self._sensor("GPU Power", "gpu_power", gpu, "{{ value_json.power }}",
                             device, unit="W", device_class="power",
                             state_class="measurement", icon="mdi:expansion-card-variant",
                             precision=1)

        if self._has_system:
            sysd = f"{self._prefix}/system"
            self._sensor("RAM Usage", "ram_usage", sysd, "{{ value_json.ram_percent }}",
                         device, unit="%", state_class="measurement", icon="mdi:memory")
            self._sensor("RAM Used", "ram_used", sysd, "{{ value_json.ram_used_mb }}",
                         device, unit="MB", device_class="data_size",
                         state_class="measurement", icon="mdi:memory", precision=0)
            self._sensor("RAM Total", "ram_total", sysd, "{{ value_json.ram_total_mb }}",
                         device, unit="MB", device_class="data_size",
                         entity_category="diagnostic")
            self._sensor("Swap Usage", "swap_usage", sysd, "{{ value_json.swap_percent }}",
                         device, unit="%", state_class="measurement", icon="mdi:harddisk")
            self._sensor("Uptime", "uptime", sysd, "{{ value_json.uptime }}",
                         device, device_class="timestamp", icon="mdi:clock-start")
            for n in (1, 5, 15):
                self._sensor(f"Load {n}m", f"load_{n}", sysd,
                             "{{ value_json.load_%d }}" % n, device,
                             state_class="measurement", icon="mdi:gauge", precision=2)
            for label, path in self._disks:
                self._sensor(f"Disk {label} Usage", f"disk_{label}_usage", sysd,
                             "{{ value_json.disk.%s.percent }}" % label, device,
                             unit="%", state_class="measurement", icon="mdi:harddisk")
                self._sensor(f"Disk {label} Free", f"disk_{label}_free", sysd,
                             "{{ value_json.disk.%s.free_gb }}" % label, device,
                             unit="GB", device_class="data_size",
                             state_class="measurement", icon="mdi:harddisk")
            self._sensor("Network Up", "net_up", sysd, "{{ value_json.net_tx_kbps }}",
                         device, unit="kB/s", device_class="data_rate",
                         state_class="measurement", icon="mdi:upload-network", precision=1)
            self._sensor("Network Down", "net_down", sysd, "{{ value_json.net_rx_kbps }}",
                         device, unit="kB/s", device_class="data_rate",
                         state_class="measurement", icon="mdi:download-network", precision=1)
            self._sensor("Disk Read", "disk_read", sysd, "{{ value_json.disk_read_kbps }}",
                         device, unit="kB/s", device_class="data_rate",
                         state_class="measurement", icon="mdi:harddisk", precision=1)
            self._sensor("Disk Write", "disk_write", sysd, "{{ value_json.disk_write_kbps }}",
                         device, unit="kB/s", device_class="data_rate",
                         state_class="measurement", icon="mdi:harddisk", precision=1)
            self._sensor("IP Address", "local_ip", sysd, "{{ value_json.local_ip }}",
                         device, icon="mdi:ip-network", entity_category="diagnostic")
            self._sensor("CPU Cores", "cpu_cores", sysd, "{{ value_json.cpu_cores }}",
                         device, icon="mdi:cpu-64-bit", entity_category="diagnostic")
            if self._has_fan:
                self._sensor("Fan Speed", "fan_speed", sysd, "{{ value_json.fan_rpm }}",
                             device, unit="rpm", state_class="measurement", icon="mdi:fan")
            info = f"{self._prefix}/system_info"
            self._sensor("Operating System", "os", info, "{{ value_json.os }}",
                         device, icon="mdi:linux", entity_category="diagnostic")
            self._sensor("Architecture", "architecture", info,
                         "{{ value_json.architecture }}", device,
                         icon="mdi:chip", entity_category="diagnostic")

        if self._watch:
            procs = f"{self._prefix}/procs"
            for name in self._watch:
                self._binary_sensor(f"{name} running", f"proc_{_proc_id(name)}", procs,
                                    "{{ 'ON' if value_json[%r] else 'OFF' }}" % name,
                                    device, device_class="running")

        if self._has_audio:
            audio = f"{self._prefix}/audio"
            cmd = f"{self._prefix}/audio/set"
            self._sensor("Audio Server", "audio_server", audio,
                         "{{ value_json.server }}", device, icon="mdi:speaker",
                         entity_category="diagnostic")
            self._number("Volume", "volume", audio, "{{ value_json.volume }}",
                         f"{cmd}/volume", device, icon="mdi:volume-high")
            self._switch("Mute", "mute", audio,
                         "{{ 'ON' if value_json.mute else 'OFF' }}",
                         f"{cmd}/mute", device, icon="mdi:volume-mute")
            if self._has_mic:
                self._number("Mic Volume", "mic_volume", audio,
                             "{{ value_json.mic_volume }}", f"{cmd}/mic_volume",
                             device, icon="mdi:microphone")
                self._switch("Mic Mute", "mic_mute", audio,
                             "{{ 'ON' if value_json.mic_mute else 'OFF' }}",
                             f"{cmd}/mic_mute", device, icon="mdi:microphone-off")

        if self._has_mpris:
            media = f"{self._prefix}/media"
            mcmd = f"{self._prefix}/media/set"
            self._sensor("Media Status", "media_status", media,
                         "{{ value_json.status }}", device, icon="mdi:play-circle")
            self._sensor("Media Title", "media_title", media,
                         "{{ value_json.title }}", device, icon="mdi:music-note")
            self._sensor("Media Artist", "media_artist", media,
                         "{{ value_json.artist }}", device, icon="mdi:account-music")
            self._button("Media Play/Pause", "media_play_pause", mcmd, "play_pause",
                         device, icon="mdi:play-pause")
            self._button("Media Next", "media_next", mcmd, "next", device,
                         icon="mdi:skip-next")
            self._button("Media Previous", "media_previous", mcmd, "previous", device,
                         icon="mdi:skip-previous")

        if self._has_wifi:
            wifi = f"{self._prefix}/wifi"
            self._sensor("WiFi Signal", "wifi_signal", wifi, "{{ value_json.signal }}",
                         device, unit="%", state_class="measurement", icon="mdi:wifi")
            self._sensor("WiFi SSID", "wifi_ssid", wifi, "{{ value_json.ssid }}",
                         device, icon="mdi:wifi", entity_category="diagnostic")
            self._sensor("WiFi APs Visible", "wifi_ap_count", wifi,
                         "{{ value_json.ap_count }}", device,
                         icon="mdi:access-point-network", state_class="measurement",
                         json_attributes_topic=f"{self._prefix}/wifi_scan")

        if self._has_bt:
            self._sensor("Bluetooth Devices", "bt_count", f"{self._prefix}/wifi",
                         "{{ value_json.bt_count }}", device, icon="mdi:bluetooth",
                         state_class="measurement",
                         json_attributes_topic=f"{self._prefix}/bt_scan")
            for mac in self._watch_bt:
                self._binary_sensor(f"BT {mac}", f"bt_{_proc_id(mac)}",
                                    f"{self._prefix}/bt_presence",
                                    "{{ 'ON' if value_json[%r] else 'OFF' }}" % mac.upper(),
                                    device, device_class="presence")

        if self._has_battery:
            bat = f"{self._prefix}/battery"
            self._sensor("Battery Level", "battery_level", bat,
                         "{{ value_json.level }}", device, unit="%",
                         device_class="battery", state_class="measurement")
            self._sensor("Battery Power", "battery_power", bat,
                         "{{ value_json.power }}", device, unit="W",
                         device_class="power", state_class="measurement")
            self._sensor("Battery Status", "battery_status", bat,
                         "{{ value_json.status }}", device, icon="mdi:battery")
            self._binary_sensor("Charging", "charging", bat,
                                "{{ 'ON' if value_json.charging else 'OFF' }}",
                                device, device_class="battery_charging")

        LOG.info("Home Assistant discovery payloads published")

    def _sensor(self, name: str, object_id: str, state_topic: str,
                value_template: str, device: dict, unit: Optional[str] = None,
                device_class: Optional[str] = None, state_class: Optional[str] = None,
                icon: Optional[str] = None, entity_category: Optional[str] = None,
                json_attributes_topic: Optional[str] = None,
                precision: Optional[int] = None) -> None:
        payload = {
            "name": f"{self._device_name} {name}",
            "unique_id": f"{self._device_id}_{object_id}",
            "state_topic": state_topic,
            "value_template": value_template,
            "device": device,
            "availability_topic": self._availability,
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        if unit:
            payload["unit_of_measurement"] = unit
        if device_class:
            payload["device_class"] = device_class
        if state_class:
            payload["state_class"] = state_class
        if icon:
            payload["icon"] = icon
        if entity_category:
            payload["entity_category"] = entity_category
        if json_attributes_topic:
            payload["json_attributes_topic"] = json_attributes_topic
        if precision is not None:
            payload["suggested_display_precision"] = precision
        topic = f"{Config.HA_DISCOVERY_PREFIX}/sensor/{self._device_id}/{object_id}/config"
        self.client.publish(topic, json.dumps(payload), qos=1, retain=True)

    def _binary_sensor(self, name: str, object_id: str, state_topic: str,
                       value_template: str, device: dict,
                       device_class: Optional[str] = None) -> None:
        payload = {
            "name": f"{self._device_name} {name}",
            "unique_id": f"{self._device_id}_{object_id}",
            "state_topic": state_topic,
            "value_template": value_template,
            "device": device,
            "availability_topic": self._availability,
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        if device_class:
            payload["device_class"] = device_class
        topic = f"{Config.HA_DISCOVERY_PREFIX}/binary_sensor/{self._device_id}/{object_id}/config"
        self.client.publish(topic, json.dumps(payload), qos=1, retain=True)

    def _base(self, name: str, object_id: str, device: dict) -> dict:
        return {
            "name": f"{self._device_name} {name}",
            "unique_id": f"{self._device_id}_{object_id}",
            "device": device,
            "availability_topic": self._availability,
            "payload_available": "online",
            "payload_not_available": "offline",
        }

    def _number(self, name, object_id, state_topic, value_template, command_topic,
                device, icon=None) -> None:
        payload = self._base(name, object_id, device)
        payload.update({"state_topic": state_topic, "value_template": value_template,
                        "command_topic": command_topic, "min": 0, "max": 100,
                        "step": 1, "mode": "slider", "unit_of_measurement": "%"})
        if icon:
            payload["icon"] = icon
        self.client.publish(
            f"{Config.HA_DISCOVERY_PREFIX}/number/{self._device_id}/{object_id}/config",
            json.dumps(payload), qos=1, retain=True)

    def _switch(self, name, object_id, state_topic, value_template, command_topic,
                device, icon=None) -> None:
        payload = self._base(name, object_id, device)
        payload.update({"state_topic": state_topic, "value_template": value_template,
                        "command_topic": command_topic, "payload_on": "ON",
                        "payload_off": "OFF"})
        if icon:
            payload["icon"] = icon
        self.client.publish(
            f"{Config.HA_DISCOVERY_PREFIX}/switch/{self._device_id}/{object_id}/config",
            json.dumps(payload), qos=1, retain=True)

    def _button(self, name, object_id, command_topic, press_payload, device,
                icon=None) -> None:
        payload = self._base(name, object_id, device)
        payload.update({"command_topic": command_topic, "payload_press": press_payload})
        if icon:
            payload["icon"] = icon
        self.client.publish(
            f"{Config.HA_DISCOVERY_PREFIX}/button/{self._device_id}/{object_id}/config",
            json.dumps(payload), qos=1, retain=True)
