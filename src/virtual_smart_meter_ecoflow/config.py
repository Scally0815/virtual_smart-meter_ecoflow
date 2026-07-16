from __future__ import annotations

import secrets
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import __version__

DataProvider = Literal["mqtt", "static"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    http_bind: str = "0.0.0.0"
    http_port: int = 80
    product_type: str = "HWE-P1"
    product_name: str = "P1 Meter"
    serial: str | None = None
    firmware_version: str = __version__
    state_dir: Path = Path("/data")

    mdns_enabled: bool = True
    mdns_interface: str | None = None
    mdns_hostname: str | None = None
    mdns_instance_name: str | None = None
    discovery_require_measurement: bool = True

    data_provider: DataProvider = "mqtt"
    static_measurement_file: Path | None = None
    static_measurement_json: str | None = None

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_state_topic: str = "virtual-smart-meter/og/measurement"
    mqtt_client_id: str = "virtual-smart-meter-ecoflow"
    mqtt_qos: int = Field(1, ge=0, le=2)
    mqtt_retain_expected: bool = True
    mqtt_keepalive: int = 60
    mqtt_tls: bool = False
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_ca_file: Path | None = None
    mqtt_cert_file: Path | None = None
    mqtt_key_file: Path | None = None
    mqtt_tls_insecure: bool = False

    required_fields: str = "active_power_w"
    stale_warning_seconds: float = 120.0
    debug_endpoint_enabled: bool = True
    log_level: str = "INFO"
    http_request_logging: bool = True

    @field_validator("serial")
    @classmethod
    def validate_serial(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        normalized = value.lower()
        if len(normalized) != 12 or any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("SERIAL must be exactly 12 hexadecimal characters")
        return normalized

    @property
    def required_field_set(self) -> set[str]:
        return {part.strip() for part in self.required_fields.split(",") if part.strip()}

    @property
    def api_version(self) -> str:
        return "v1"

    @property
    def resolved_serial(self) -> str:
        if self.serial:
            return self.serial
        return load_or_create_serial(self.state_dir)


def load_or_create_serial(state_dir: Path) -> str:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "serial"
    if path.exists():
        value = path.read_text(encoding="utf-8").strip().lower()
        Settings.validate_serial(value)
        return value
    value = "02" + secrets.token_hex(5)  # locally administered, not vendor OUI
    path.write_text(value + "\n", encoding="utf-8")
    return value


def redact_settings(settings: Settings) -> dict[str, object]:
    data = settings.model_dump(mode="json")
    for key in list(data):
        if any(secret in key.lower() for secret in ("password", "key", "cert", "token")):
            data[key] = "***redacted***" if data[key] else None
    data["serial"] = settings.resolved_serial
    return data
