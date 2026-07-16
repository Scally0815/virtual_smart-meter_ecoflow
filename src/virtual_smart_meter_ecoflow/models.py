from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any

SUPPORTED_FIELDS: dict[str, type | tuple[type, ...]] = {
    "unique_id": str,
    "smr_version": (int, float),
    "meter_model": str,
    "wifi_ssid": str,
    "wifi_strength": (int, float),
    "active_tariff": (int, float),
    "total_power_import_kwh": (int, float),
    "total_power_import_t1_kwh": (int, float),
    "total_power_import_t2_kwh": (int, float),
    "total_power_import_t3_kwh": (int, float),
    "total_power_import_t4_kwh": (int, float),
    "total_power_export_kwh": (int, float),
    "total_power_export_t1_kwh": (int, float),
    "total_power_export_t2_kwh": (int, float),
    "total_power_export_t3_kwh": (int, float),
    "total_power_export_t4_kwh": (int, float),
    "active_power_w": (int, float),
    "active_power_l1_w": (int, float),
    "active_power_l2_w": (int, float),
    "active_power_l3_w": (int, float),
    "active_voltage_l1_v": (int, float),
    "active_voltage_l2_v": (int, float),
    "active_voltage_l3_v": (int, float),
    "active_current_l1_a": (int, float),
    "active_current_l2_a": (int, float),
    "active_current_l3_a": (int, float),
    "active_frequency_hz": (int, float),
    "voltage_sag_l1_count": (int, float),
    "voltage_sag_l2_count": (int, float),
    "voltage_sag_l3_count": (int, float),
    "voltage_swell_l1_count": (int, float),
    "voltage_swell_l2_count": (int, float),
    "voltage_swell_l3_count": (int, float),
    "any_power_fail_count": (int, float),
    "long_power_fail_count": (int, float),
    "active_power_average_w": (int, float),
    "montly_power_peak_w": (int, float),
    "montly_power_peak_timestamp": str,
    "total_gas_m3": (int, float),
    "gas_timestamp": str,
    "unique_gas_id": str,
    "external": object,
}

NUMERIC_TYPES = (int, float, Decimal)


class MeasurementValidationError(ValueError):
    pass


def _json_loads_strict(payload: str | bytes) -> Any:
    def bad_constant(value: str) -> None:
        raise MeasurementValidationError(f"invalid numeric value: {value}")

    try:
        return json.loads(payload, parse_constant=bad_constant, parse_float=Decimal)
    except MeasurementValidationError:
        raise
    except json.JSONDecodeError as exc:
        raise MeasurementValidationError(f"malformed JSON: {exc.msg}") from exc


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_value(v) for v in value]
    return value


def validate_measurement_payload(
    payload: str | bytes, required_fields: set[str]
) -> tuple[dict[str, Any], set[str]]:
    data = _json_loads_strict(payload)
    if not isinstance(data, dict):
        raise MeasurementValidationError("payload must be a JSON object")
    measurement: dict[str, Any] = {}
    unknown = set()
    for key, value in data.items():
        if key not in SUPPORTED_FIELDS:
            unknown.add(str(key))
            continue
        if value is None:
            continue
        expected = SUPPORTED_FIELDS[key]
        if expected is object:
            measurement[key] = _json_value(value)
            continue
        if expected is str:
            if not isinstance(value, str):
                raise MeasurementValidationError(f"field {key} must be a string")
            measurement[key] = value
            continue
        if isinstance(value, bool) or not isinstance(value, NUMERIC_TYPES):
            raise MeasurementValidationError(f"field {key} must be a finite number")
        if isinstance(value, float) and not math.isfinite(value):
            raise MeasurementValidationError(f"field {key} must be a finite number")
        measurement[key] = _json_value(value)
    if not measurement:
        raise MeasurementValidationError(
            "payload must contain at least one supported non-null field"
        )
    missing = required_fields - measurement.keys()
    if missing:
        raise MeasurementValidationError(f"missing required field(s): {', '.join(sorted(missing))}")
    return measurement, unknown
