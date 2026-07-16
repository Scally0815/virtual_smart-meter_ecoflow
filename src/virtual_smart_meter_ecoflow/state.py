from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class AppState:
    measurement: dict[str, Any] | None = None
    last_message_received_at: datetime | None = None
    mqtt_connected: bool = False
    mdns_registered: bool = False
    provider: str = "mqtt"

    def update_measurement(self, measurement: dict[str, Any]) -> None:
        self.measurement = dict(measurement)
        self.last_message_received_at = datetime.now(UTC)

    @property
    def measurement_available(self) -> bool:
        return self.measurement is not None

    def age_seconds(self) -> float | None:
        if self.last_message_received_at is None:
            return None
        return (datetime.now(UTC) - self.last_message_received_at).total_seconds()
