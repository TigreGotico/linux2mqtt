"""powerguess MQTT bridge configuration — all settings via environment variables."""

import os


class Config:
    """Static config holder populated once at startup."""

    # Monitor
    MEASURE_INTERVAL: float = float(os.getenv("MEASURE_INTERVAL", "5"))
    SMOOTH: bool = os.getenv("SMOOTH", "false").lower() == "true"
    PREFER_BATTERY: bool = os.getenv("PREFER_BATTERY", "false").lower() == "true"
    USE_POWERSTAT: bool = os.getenv("USE_POWERSTAT", "true").lower() == "true"
    PUBLISH_INTERVAL: float = float(os.getenv("PUBLISH_INTERVAL", "5"))
    # Publish early when power moves by more than this many watts (0 disables).
    PUBLISH_DELTA: float = float(os.getenv("PUBLISH_DELTA", "0.5"))

    # Calibration
    CALIBRATION_FILE: str = os.getenv("CALIBRATION_FILE", "")
    AUTO_CALIBRATE: bool = os.getenv("AUTO_CALIBRATE", "true").lower() == "true"

    # Optional INA219 I2C power monitor
    USE_INA219: bool = os.getenv("USE_INA219", "false").lower() == "true"
    INA219_BUS: int = int(os.getenv("INA219_BUS", "1"))
    INA219_ADDRESS: int = int(os.getenv("INA219_ADDRESS", "0x40"), 0)
    INA219_SHUNT_OHMS: float = float(os.getenv("INA219_SHUNT_OHMS", "0.1"))

    # CPU component telemetry (util/freq/temp, and package power via RAPL)
    USE_CPU: bool = os.getenv("USE_CPU", "true").lower() == "true"

    # Raspberry Pi via vcgencmd: PMIC board power (Pi 5) + throttling/undervoltage
    USE_RPI: bool = os.getenv("USE_RPI", "true").lower() == "true"

    # GPU telemetry (NVIDIA via nvidia-smi) published as its own entities
    USE_GPU: bool = os.getenv("USE_GPU", "true").lower() == "true"
    GPU_INDEX: int = int(os.getenv("GPU_INDEX", "0"))

    # Optional trained predictor model (JSON of linear coefficients)
    MODEL_FILE: str = os.getenv("MODEL_FILE", "")

    # Optional dataset collection (append measured rows as JSONL)
    DATASET_FILE: str = os.getenv("DATASET_FILE", "")

    # MQTT
    MQTT_HOST: str = os.getenv("MQTT_HOST", "localhost")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
    MQTT_USER = os.getenv("MQTT_USER") or None
    MQTT_PASSWORD = os.getenv("MQTT_PASSWORD") or None
    MQTT_TOPIC_PREFIX: str = os.getenv("MQTT_TOPIC_PREFIX", "powerguess")
    MQTT_CLIENT_ID: str = os.getenv("MQTT_CLIENT_ID", "powerguess-client")
    MQTT_QOS: int = int(os.getenv("MQTT_QOS", "0"))
    MQTT_RETAIN: bool = os.getenv("MQTT_RETAIN", "true").lower() == "true"
    MQTT_KEEPALIVE: int = int(os.getenv("MQTT_KEEPALIVE", "60"))
    MQTT_RETRY_COUNT: int = int(os.getenv("MQTT_RETRY_COUNT", "5"))
    MQTT_RETRY_MAX_BACKOFF: int = int(os.getenv("MQTT_RETRY_MAX_BACKOFF", "30"))
    MQTT_CONNECT_TIMEOUT: float = float(os.getenv("MQTT_CONNECT_TIMEOUT", "2.0"))

    # Home Assistant
    HA_ENABLED: bool = os.getenv("HA_ENABLED", "true").lower() == "true"
    HA_DISCOVERY_PREFIX: str = os.getenv("HA_DISCOVERY_PREFIX", "homeassistant")
    DEVICE_NAME: str = os.getenv("DEVICE_NAME", "PowerGuess")
    DEVICE_ID: str = os.getenv("DEVICE_ID", "powerguess_01")

    # Energy persistence + cost
    ENERGY_FILE: str = os.getenv("ENERGY_FILE", "")
    ENERGY_TARIFF: float = float(os.getenv("ENERGY_TARIFF", "0"))  # per kWh; 0 disables cost
    CURRENCY: str = os.getenv("CURRENCY", "EUR")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
