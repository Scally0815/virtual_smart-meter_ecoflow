from __future__ import annotations

import logging

from aiohttp import web

from .config import Settings
from .state import AppState

LOG = logging.getLogger(__name__)


def json_error(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


def create_http_app(settings: Settings, state: AppState) -> web.Application:
    app = web.Application(middlewares=[request_logger] if settings.http_request_logging else [])

    async def api(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "product_type": settings.product_type,
                "product_name": settings.product_name,
                "serial": settings.resolved_serial,
                "firmware_version": settings.firmware_version,
                "api_version": settings.api_version,
            }
        )

    async def data(_: web.Request) -> web.Response:
        if state.measurement is None:
            return json_error(503, "no valid measurement has been received")
        return web.json_response(state.measurement)

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def ready(_: web.Request) -> web.Response:
        ready_state = state.measurement_available
        if settings.data_provider == "mqtt":
            ready_state = ready_state and state.mqtt_connected
        if settings.mdns_enabled:
            ready_state = ready_state and state.mdns_registered
        return web.json_response({"ready": ready_state}, status=200 if ready_state else 503)

    async def debug(_: web.Request) -> web.Response:
        if not settings.debug_endpoint_enabled:
            return json_error(404, "debug endpoint disabled")
        age = state.age_seconds()
        return web.json_response(
            {
                "provider": state.provider,
                "mqtt_connected": state.mqtt_connected,
                "measurement_available": state.measurement_available,
                "last_message_received_at": state.last_message_received_at.isoformat().replace(
                    "+00:00", "Z"
                )
                if state.last_message_received_at
                else None,
                "message_age_seconds": age,
                "stale_warning": bool(age is not None and age > settings.stale_warning_seconds),
                "mdns_registered": state.mdns_registered,
                "measurement": state.measurement,
            }
        )

    app.router.add_get("/api", api)
    app.router.add_get("/api/v1/data", data)
    app.router.add_get("/health", health)
    app.router.add_get("/ready", ready)
    app.router.add_get("/debug/state", debug)
    return app


@web.middleware
async def request_logger(request: web.Request, handler: web.Handler) -> web.StreamResponse:
    response = await handler(request)
    LOG.debug(
        "http_request method=%s path=%s remote=%s user_agent=%s status=%s",
        request.method,
        request.path,
        request.remote,
        request.headers.get("User-Agent"),
        response.status,
    )
    return response
