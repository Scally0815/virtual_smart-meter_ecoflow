from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..models import validate_measurement_payload
from ..state import AppState


@dataclass
class StaticProvider:
    settings: Settings
    state: AppState

    async def start(self) -> None:
        if self.settings.static_measurement_json:
            payload = self.settings.static_measurement_json
        elif self.settings.static_measurement_file:
            payload = self.settings.static_measurement_file.read_text(encoding="utf-8")
        else:
            raise RuntimeError(
                "DATA_PROVIDER=static requires STATIC_MEASUREMENT_JSON or STATIC_MEASUREMENT_FILE"
            )
        measurement, _ = validate_measurement_payload(payload, self.settings.required_field_set)
        self.state.update_measurement(measurement)
        self.state.mqtt_connected = False

    async def stop(self) -> None:
        return None
