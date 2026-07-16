from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass

from zeroconf import IPVersion, ServiceInfo, Zeroconf

from .config import Settings
from .state import AppState

LOG = logging.getLogger(__name__)
SERVICE_TYPE = "_hwenergy._tcp.local."


def instance_name(settings: Settings) -> str:
    return settings.mdns_instance_name or f"p1meter-{settings.resolved_serial[-6:]}"


def txt_records(settings: Settings) -> dict[str, str]:
    return {
        "api_enabled": "1",
        "path": "/api/v1",
        "serial": settings.resolved_serial,
        "product_name": settings.product_name,
        "product_type": settings.product_type,
    }


@dataclass
class MdnsAdvertiser:
    settings: Settings
    state: AppState
    zeroconf: Zeroconf | None = None
    info: ServiceInfo | None = None

    async def register(self) -> None:
        if not self.settings.mdns_enabled or self.state.mdns_registered:
            return
        host = self.settings.mdns_hostname or socket.gethostname()
        fqdn = host if host.endswith(".local.") else f"{host}.local."
        name = f"{instance_name(self.settings)}.{SERVICE_TYPE}"
        addresses = [socket.inet_aton("127.0.0.1")]
        self.info = ServiceInfo(
            SERVICE_TYPE,
            name,
            addresses=addresses,
            port=self.settings.http_port,
            properties=txt_records(self.settings),
            server=fqdn,
        )
        self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        await asyncio.to_thread(self.zeroconf.register_service, self.info)
        self.state.mdns_registered = True
        LOG.info("mdns_registered service=%s port=%s", name, self.settings.http_port)

    async def unregister(self) -> None:
        if self.zeroconf and self.info:
            await asyncio.to_thread(self.zeroconf.unregister_service, self.info)
            await asyncio.to_thread(self.zeroconf.close)
            LOG.info("mdns_unregistered service=%s", self.info.name)
        self.state.mdns_registered = False
