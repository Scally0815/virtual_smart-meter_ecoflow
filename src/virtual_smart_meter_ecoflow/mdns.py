from __future__ import annotations

import asyncio
import fcntl
import logging
import socket
import struct
from dataclasses import dataclass
from ipaddress import IPv4Address, ip_address

from zeroconf import IPVersion, InterfaceChoice, ServiceInfo, Zeroconf

from .config import Settings
from .state import AppState

LOG = logging.getLogger(__name__)
SERVICE_TYPE = "_hwenergy._tcp.local."
SIOCGIFADDR = 0x8915


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


def _usable_automatic_address(value: str) -> IPv4Address | None:
    try:
        address = ip_address(value)
    except ValueError:
        return None
    if not isinstance(address, IPv4Address):
        return None
    if address.is_loopback or address.is_unspecified or address.is_link_local:
        return None
    return address


def interface_address(interface: str) -> IPv4Address:
    """Resolve an IPv4 address or Linux interface name to its IPv4 address."""
    try:
        address = ip_address(interface)
    except ValueError:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                request = struct.pack("256s", interface.encode("utf-8")[:15])
                result = fcntl.ioctl(sock.fileno(), SIOCGIFADDR, request)
            address = ip_address(socket.inet_ntoa(result[20:24]))
        except (OSError, UnicodeError) as exc:
            raise ValueError(
                f"MDNS_INTERFACE {interface!r} is not an IPv4 address or an interface "
                "with an IPv4 address"
            ) from exc
    if not isinstance(address, IPv4Address):
        raise ValueError("MDNS_INTERFACE must be an interface name or IPv4 address")
    if address.is_loopback or address.is_unspecified:
        raise ValueError("MDNS_INTERFACE must not resolve to loopback or 0.0.0.0")
    return address


def automatic_address() -> IPv4Address:
    """Select a routable host IPv4 address without advertising unsafe fallbacks."""
    candidates: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # No packet is sent; connect asks the kernel which source address it would use.
            sock.connect(("192.0.2.1", 9))
            candidates.append(sock.getsockname()[0])
    except OSError:
        pass
    try:
        candidates.extend(
            item[4][0]
            for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        )
    except OSError:
        pass
    for candidate in candidates:
        if address := _usable_automatic_address(candidate):
            return address
    raise RuntimeError(
        "Could not determine a usable non-loopback IPv4 address; set MDNS_ADDRESS explicitly"
    )


def advertised_address(settings: Settings) -> IPv4Address:
    if settings.mdns_address is not None:
        return settings.mdns_address
    if settings.mdns_interface:
        address = interface_address(settings.mdns_interface)
        if address.is_link_local:
            raise ValueError(
                "MDNS_INTERFACE resolved to a link-local address; set MDNS_ADDRESS explicitly "
                "to advertise it"
            )
        return address
    return automatic_address()


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
        address = advertised_address(self.settings)
        interface = (
            interface_address(self.settings.mdns_interface)
            if self.settings.mdns_interface
            else None
        )
        self.info = ServiceInfo(
            SERVICE_TYPE,
            name,
            addresses=[address.packed],
            port=self.settings.http_port,
            properties=txt_records(self.settings),
            server=fqdn,
        )
        self.zeroconf = Zeroconf(
            interfaces=[str(interface)] if interface is not None else InterfaceChoice.Default,
            ip_version=IPVersion.V4Only,
        )
        await asyncio.to_thread(self.zeroconf.register_service, self.info)
        self.state.mdns_registered = True
        LOG.info(
            "mdns_registered address=%s interface=%s hostname=%s service=%s port=%s",
            address,
            interface or "default",
            fqdn,
            name,
            self.settings.http_port,
        )

    async def unregister(self) -> None:
        if self.zeroconf and self.info:
            await asyncio.to_thread(self.zeroconf.unregister_service, self.info)
            await asyncio.to_thread(self.zeroconf.close)
            LOG.info("mdns_unregistered service=%s", self.info.name)
        self.state.mdns_registered = False
