from __future__ import annotations

import asyncio
import contextlib
import logging
import ssl
from dataclasses import dataclass, field
from typing import Any

import aiomqtt

from ..config import Settings
from ..mdns import MdnsAdvertiser
from ..models import MeasurementValidationError, validate_measurement_payload
from ..state import AppState

LOG = logging.getLogger(__name__)


@dataclass
class MqttProvider:
    settings: Settings
    state: AppState
    mdns: MdnsAdvertiser | None = None
    task: asyncio.Task[None] | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    async def start(self) -> None:
        self.task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self.stop_event.set()
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task

    def tls_context(self) -> ssl.SSLContext | None:
        if not self.settings.mqtt_tls:
            return None
        ctx = ssl.create_default_context(
            cafile=str(self.settings.mqtt_ca_file) if self.settings.mqtt_ca_file else None
        )
        if self.settings.mqtt_cert_file and self.settings.mqtt_key_file:
            ctx.load_cert_chain(self.settings.mqtt_cert_file, self.settings.mqtt_key_file)
        ctx.check_hostname = not self.settings.mqtt_tls_insecure
        ctx.verify_mode = ssl.CERT_NONE if self.settings.mqtt_tls_insecure else ssl.CERT_REQUIRED
        return ctx

    async def _run(self) -> None:
        backoff = 1.0
        while not self.stop_event.is_set():
            try:
                kwargs: dict[str, Any] = {
                    "hostname": self.settings.mqtt_host,
                    "port": self.settings.mqtt_port,
                    "identifier": self.settings.mqtt_client_id,
                    "keepalive": self.settings.mqtt_keepalive,
                    "protocol": aiomqtt.ProtocolVersion.V311,
                    "tls_context": self.tls_context(),
                }
                if self.settings.mqtt_username:
                    kwargs["username"] = self.settings.mqtt_username
                if self.settings.mqtt_password:
                    kwargs["password"] = self.settings.mqtt_password
                async with aiomqtt.Client(**kwargs) as client:
                    self.state.mqtt_connected = True
                    backoff = 1.0
                    LOG.info(
                        "mqtt_connected host=%s port=%s",
                        self.settings.mqtt_host,
                        self.settings.mqtt_port,
                    )
                    await client.subscribe(
                        self.settings.mqtt_state_topic, qos=self.settings.mqtt_qos
                    )
                    LOG.info(
                        "mqtt_subscribed topic=%s qos=%s",
                        self.settings.mqtt_state_topic,
                        self.settings.mqtt_qos,
                    )
                    async for message in client.messages:
                        await self.process_payload(message.payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.state.mqtt_connected = False
                LOG.warning("mqtt_reconnect_after_error error=%s backoff=%s", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def process_payload(self, payload: bytes | str) -> bool:
        try:
            measurement, unknown = validate_measurement_payload(
                payload, self.settings.required_field_set
            )
        except MeasurementValidationError as exc:
            LOG.warning("invalid_mqtt_payload reason=%s", exc)
            return False
        if unknown:
            LOG.warning("ignored_unknown_fields fields=%s", sorted(unknown))
        self.state.update_measurement(measurement)
        LOG.info("valid_measurement_received fields=%s", sorted(measurement))
        if self.mdns and (
            not self.settings.discovery_require_measurement or self.state.measurement_available
        ):
            await self.mdns.register()
        return True
