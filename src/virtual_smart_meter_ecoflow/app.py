from __future__ import annotations

import asyncio
import logging
import signal

from aiohttp import web

from . import __version__
from .api import create_http_app
from .config import Settings
from .mdns import MdnsAdvertiser
from .providers.mqtt import MqttProvider
from .providers.static import StaticProvider
from .state import AppState

LOG = logging.getLogger(__name__)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def run(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    state = AppState(provider=settings.data_provider)
    mdns = MdnsAdvertiser(settings, state)
    provider = (
        MqttProvider(settings, state, mdns)
        if settings.data_provider == "mqtt"
        else StaticProvider(settings, state)
    )
    LOG.info(
        "startup version=%s provider=%s http=%s:%s",
        __version__,
        settings.data_provider,
        settings.http_bind,
        settings.http_port,
    )
    app = create_http_app(settings, state)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.http_bind, settings.http_port)
    await site.start()
    await provider.start()
    if settings.mdns_enabled and (
        not settings.discovery_require_measurement or state.measurement_available
    ):
        await mdns.register()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    LOG.info("graceful_shutdown")
    await provider.stop()
    await mdns.unregister()
    await runner.cleanup()
