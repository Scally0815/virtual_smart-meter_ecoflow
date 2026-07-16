from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from pydantic import ValidationError
from zeroconf import IPVersion

from virtual_smart_meter_ecoflow.api import create_http_app
from virtual_smart_meter_ecoflow.config import Settings, load_or_create_serial, redact_settings
from virtual_smart_meter_ecoflow.mdns import (
    MdnsAdvertiser,
    automatic_address,
    instance_name,
    txt_records,
)
from virtual_smart_meter_ecoflow.models import (
    MeasurementValidationError,
    validate_measurement_payload,
)
from virtual_smart_meter_ecoflow.providers.mqtt import MqttProvider
from virtual_smart_meter_ecoflow.state import AppState


def settings(tmp_path: Path, **kw: object) -> Settings:
    return Settings(
        state_dir=tmp_path, serial="001122334455", http_port=8080, mdns_enabled=False, **kw
    )


@pytest.mark.asyncio
async def test_api_and_data(tmp_path: Path) -> None:
    s = settings(tmp_path)
    st = AppState(measurement={"active_power_w": -20})
    async with TestClient(TestServer(create_http_app(s, st))) as c:
        assert (await (await c.get("/api")).json())["product_type"] == "HWE-P1"
        assert await (await c.get("/api/v1/data")).json() == {"active_power_w": -20}


@pytest.mark.parametrize("serial", ["001122334455", "AABBCCDDEEFF"])
def test_serial_validation(tmp_path: Path, serial: str) -> None:
    assert Settings(state_dir=tmp_path, serial=serial).serial == serial.lower()


@pytest.mark.parametrize("serial", ["bad", "00112233445g", "00112233445566"])
def test_invalid_serial(tmp_path: Path, serial: str) -> None:
    with pytest.raises(ValidationError):
        Settings(state_dir=tmp_path, serial=serial)


def test_persistent_generated_serial(tmp_path: Path) -> None:
    first = load_or_create_serial(tmp_path)
    second = load_or_create_serial(tmp_path)
    assert first == second and len(first) == 12 and first.startswith("02")


def parse(payload: str) -> dict[str, object]:
    return validate_measurement_payload(payload, {"active_power_w"})[0]


def test_minimal_positive_negative_decimal_and_no_invention() -> None:
    assert parse('{"active_power_w": -20}') == {"active_power_w": -20}
    m = parse('{"active_power_w": 20, "total_power_export_t1_kwh": 2.363}')
    assert m["active_power_w"] == 20 and m["total_power_export_t1_kwh"] == 2.363
    assert (
        "active_power_l1_w" not in m
        and "active_voltage_l1_v" not in m
        and "active_current_l1_a" not in m
        and "total_power_import_t1_kwh" not in m
    )


def test_null_unknown_and_missing_optional() -> None:
    m, unknown = validate_measurement_payload(
        '{"active_power_w": -20, "wifi_strength": null, "x": 1}', {"active_power_w"}
    )
    assert m == {"active_power_w": -20}
    assert unknown == {"x"}


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        "[]",
        '{"active_power_w":"1"}',
        '{"active_power_w":true}',
        '{"active_power_w":NaN}',
        '{"active_power_w":Infinity}',
        "{}",
    ],
)
def test_invalid_payloads(payload: str) -> None:
    with pytest.raises(MeasurementValidationError):
        parse(payload)


@pytest.mark.asyncio
async def test_invalid_does_not_replace_and_retained_processing(tmp_path: Path) -> None:
    st = AppState()
    p = MqttProvider(settings(tmp_path), st)
    assert await p.process_payload(b'{"active_power_w":-20}')
    assert st.measurement == {"active_power_w": -20}
    assert not await p.process_payload(b'{"active_power_w":"bad"}')
    assert st.measurement == {"active_power_w": -20}


@pytest.mark.asyncio
async def test_no_measurement_and_ready(tmp_path: Path) -> None:
    s = settings(tmp_path)
    st = AppState(mqtt_connected=True)
    async with TestClient(TestServer(create_http_app(s, st))) as c:
        assert (await c.get("/api/v1/data")).status == 503
        assert (await c.get("/ready")).status == 503


def test_stale_warning_without_modifying(tmp_path: Path) -> None:
    st = AppState()
    st.update_measurement({"active_power_w": -20})
    st.last_message_received_at = st.last_message_received_at.replace(year=2000)  # type: ignore[union-attr]
    age = st.age_seconds()
    assert age is not None and age > 120
    assert st.measurement == {"active_power_w": -20}


def test_mdns_records(tmp_path: Path) -> None:
    s = settings(tmp_path)
    assert instance_name(s) == "p1meter-334455"
    assert txt_records(s)["serial"] == "001122334455"


@pytest.mark.asyncio
async def test_explicit_mdns_address_and_configurable_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[object] = []

    class FakeZeroconf:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

        def register_service(self, info: object) -> None:
            created.append(info)

        def unregister_service(self, info: object) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("virtual_smart_meter_ecoflow.mdns.Zeroconf", FakeZeroconf)
    s = Settings(
        state_dir=tmp_path,
        serial="001122334455",
        http_port=8123,
        mdns_address="192.168.10.25",
        mdns_interface="192.168.10.25",
    )
    advertiser = MdnsAdvertiser(s, AppState())
    await advertiser.register()

    assert advertiser.info is not None
    assert advertiser.info.parsed_addresses() == ["192.168.10.25"]
    assert advertiser.info.port == 8123
    assert created[0] == {
        "interfaces": ["192.168.10.25"],
        "ip_version": IPVersion.V4Only,
    }


def test_automatic_mdns_address_skips_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSocket:
        def __enter__(self) -> FakeSocket:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def connect(self, address: object) -> None:
            pass

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 12345)

    monkeypatch.setattr("virtual_smart_meter_ecoflow.mdns.socket.socket", lambda *a: FakeSocket())
    monkeypatch.setattr(
        "virtual_smart_meter_ecoflow.mdns.socket.getaddrinfo",
        lambda *a: [
            (2, 1, 6, "", ("127.0.0.1", 0)),
            (2, 1, 6, "", ("169.254.10.20", 0)),
            (2, 1, 6, "", ("192.168.10.30", 0)),
        ],
    )
    assert str(automatic_address()) == "192.168.10.30"


@pytest.mark.parametrize("address", ["127.0.0.1", "0.0.0.0", "not-an-address", "::1"])
def test_invalid_mdns_address_has_clear_configuration_error(
    tmp_path: Path, address: str
) -> None:
    with pytest.raises(ValidationError, match="mdns_address|MDNS_ADDRESS"):
        Settings(state_dir=tmp_path, mdns_address=address)


def test_secret_redaction(tmp_path: Path) -> None:
    redacted = redact_settings(settings(tmp_path, mqtt_password="secret", mqtt_key_file=Path("/k")))
    assert "secret" not in str(redacted)


@pytest.mark.asyncio
async def test_graceful_stop_without_started_task(tmp_path: Path) -> None:
    await MqttProvider(settings(tmp_path), AppState()).stop()
