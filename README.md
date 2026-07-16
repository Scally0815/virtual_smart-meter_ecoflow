# virtual_smart-meter_ecoflow

> Experimental, unofficial interoperability project. EcoFlow compatibility has not been confirmed with real hardware by this project.

## Overview

`virtual_smart-meter_ecoflow` is a transparent protocol adapter. It subscribes to a JSON MQTT measurement that was already calculated by Home Assistant, ioBroker, Node-RED, or another source, stores the latest valid message, and exposes those exact supported fields through a HomeWizard HWE-P1-like local HTTP API v1 plus `_hwenergy._tcp` mDNS discovery.

```text
                    MQTT
 Home Assistant  ─────────────┐
 ioBroker        ─────────────┤
 Node-RED        ─────────────┤
 Other source    ─────────────┘
                              │
                              ▼
                 virtual_smart-meter_ecoflow
                    ├── MQTT subscriber
                    ├── measurement state
                    ├── HTTP API v1
                    └── mDNS discovery
                              │
                              ▼
                 HomeWizard-compatible client
                   Experimental: EcoFlow app
```

## Strict responsibility boundary

The emulator validates transport format, stores the latest valid measurement, and returns the same supported fields. It does **not** convert kW to W, change signs, calculate net power, distribute phases, calculate current/voltage/energy, round values, fill missing tariffs, invent defaults, or replace stale values with zero.

## Features

- Python 3.12 asyncio application using aiohttp, aiomqtt, pydantic-settings, and python-zeroconf.
- `GET /api`, `GET /api/v1/data`, `/health`, `/ready`, and optional `/debug/state`.
- MQTT 3.1.1 subscription with reconnect backoff and retained-message support.
- Central allowlist of HomeWizard API v1 fields, including the documented `montly_*` spelling.
- Optional static development provider.
- Docker, Docker Compose, systemd example, tests, ruff, mypy, and GitHub Actions.

## Non-goals

No write APIs, cloud control, firmware operations, raw telegram endpoint, HomeWizard API v2, energy management, telemetry, proprietary code, or confirmed EcoFlow support claims are included.

## Endpoints

- `GET /api` returns device information: product type, product name, serial, firmware version, and `api_version: v1`.
- `GET /api/v1/data` returns the latest valid MQTT/static measurement. If none exists, it returns a JSON error with HTTP 503.
- `GET /health` reports process/HTTP liveness and does not depend on MQTT.
- `GET /ready` is 2xx only when config is valid, MQTT is connected in MQTT mode, a measurement exists, and mDNS is registered when enabled.
- `GET /debug/state` returns diagnostics when enabled.

Unsupported paths return normal 404 responses.

## MQTT payload contract

Publish a retained JSON object to `virtual-smart-meter/og/measurement` by default:

```json
{
  "total_power_import_t1_kwh": 4382.17,
  "total_power_export_t1_kwh": 2.363,
  "active_power_w": -20
}
```

Unknown fields are ignored and logged. Null optional fields are ignored. Malformed JSON, arrays, strings/booleans where numbers are expected, NaN, and Infinity are rejected. Invalid messages never replace the previous valid measurement. `REQUIRED_FIELDS` defaults to `active_power_w`.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `HTTP_BIND` | `0.0.0.0` | HTTP bind address. |
| `HTTP_PORT` | `80` | HTTP port and mDNS SRV port. |
| `PRODUCT_TYPE` | `HWE-P1` | Device product type. |
| `PRODUCT_NAME` | `P1 Meter` | Device product name. |
| `SERIAL` | generated | 12 lowercase hex chars; generated serial is persisted in `/data/serial`. |
| `FIRMWARE_VERSION` | project version | Reported firmware version. |
| `STATE_DIR` | `/data` | Persistent state directory. |
| `DATA_PROVIDER` | `mqtt` | `mqtt` or `static`. |
| `STATIC_MEASUREMENT_FILE` | unset | Fixture for static mode. |
| `STATIC_MEASUREMENT_JSON` | unset | Inline static JSON. |
| `MQTT_HOST` / `MQTT_PORT` | `localhost` / `1883` | MQTT broker. |
| `MQTT_STATE_TOPIC` | `virtual-smart-meter/og/measurement` | Subscribed input topic. |
| `MQTT_CLIENT_ID` | `virtual-smart-meter-ecoflow` | MQTT client ID. |
| `MQTT_QOS` | `1` | Subscription QoS. |
| `MQTT_RETAIN_EXPECTED` | `true` | Documentation/diagnostic expectation. |
| `MQTT_KEEPALIVE` | `60` | MQTT keepalive seconds. |
| `MQTT_TLS` | `false` | Enable MQTT TLS. |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | unset | MQTT credentials. |
| `MQTT_CA_FILE`, `MQTT_CERT_FILE`, `MQTT_KEY_FILE` | unset | TLS files. |
| `MQTT_TLS_INSECURE` | `false` | Disable TLS verification. |
| `MDNS_ENABLED` | `true` | Enable zeroconf advertisement. |
| `MDNS_INTERFACE`, `MDNS_HOSTNAME`, `MDNS_INSTANCE_NAME` | unset | Optional mDNS overrides. |
| `DISCOVERY_REQUIRE_MEASUREMENT` | `true` | Wait for first valid measurement before mDNS registration. |
| `REQUIRED_FIELDS` | `active_power_w` | Comma-separated required supported fields. |
| `STALE_WARNING_SECONDS` | `120` | Diagnostic stale threshold only. |
| `DEBUG_ENDPOINT_ENABLED` | `true` | Enable `/debug/state`. |
| `LOG_LEVEL` | `INFO` | Logging level. |
| `HTTP_REQUEST_LOGGING` | `true` | HTTP request logging at DEBUG. |

## Docker installation

```sh
cp example.env .env
docker compose up --build -d
```

The Compose file uses Linux host networking so mDNS multicast and port 80 behave like a LAN device. Host networking has security and port-conflict implications and does not work identically on Docker Desktop, Windows, or macOS. Debian 12/Linux is the primary deployment target. The container runs as a non-root user and uses `NET_BIND_SERVICE` for port 80.

## Native Debian installation

See `deploy/systemd/`. Create a dedicated `virtual-smart-meter` user, install the Python package in `/opt/virtual-smart-meter-ecoflow/.venv`, copy the environment file to `/etc/virtual-smart-meter-ecoflow.env`, and install the unit. The unit uses `StateDirectory`, `Restart=on-failure`, hardening options, and only `CAP_NET_BIND_SERVICE` for port 80.

## Home Assistant example

Entity IDs are placeholders. This example performs source-side conversion from kW to W and publishes final HomeWizard field names. MQTT retain is enabled.

```yaml
automation:
  - id: publish_virtual_smart_meter_og
    alias: "Publish virtual smart meter OG"
    mode: restart
    triggers:
      - trigger: state
        entity_id:
          - sensor.og_power
          - sensor.og_energy
          - sensor.og_energy_export
      - trigger: homeassistant
        event: start
    conditions:
      - condition: template
        value_template: >
          {{
            has_value('sensor.og_power')
            and has_value('sensor.og_energy')
            and has_value('sensor.og_energy_export')
          }}
    actions:
      - action: mqtt.publish
        data:
          topic: virtual-smart-meter/og/measurement
          qos: 1
          retain: true
          payload: >-
            {{
              {
                "total_power_import_t1_kwh":
                  states('sensor.og_energy') | float,
                "total_power_export_t1_kwh":
                  states('sensor.og_energy_export') | float,
                "active_power_w":
                  (states('sensor.og_power') | float * 1000)
              } | tojson
            }}
```

The kW-to-W conversion happens in Home Assistant. Sign handling happens in Home Assistant or the physical meter. The emulator does not modify resulting values. Irregular wM-Bus updates can mean the same last value is returned repeatedly until a new telegram is received. Retained MQTT messages allow recovery after restart. Do not add a periodic MQTT heartbeat that makes old source data appear new.

## ioBroker / Node-RED principle

Publish the already-final HomeWizard API field names to MQTT as retained JSON. Do all conversions, sign choices, and calculations before publication.

## API examples

```sh
curl http://<DEVICE-IP>/api
curl http://<DEVICE-IP>/api/v1/data
curl http://<DEVICE-IP>/health
curl http://<DEVICE-IP>/ready
curl http://<DEVICE-IP>/debug/state
```

## mDNS discovery tests

```sh
avahi-browse -rt _hwenergy._tcp
```

macOS:

```sh
dns-sd -B _hwenergy._tcp .
```

The application and discovering client usually need to be on the same VLAN/layer-2 network unless multicast forwarding or an mDNS reflector is configured.

## Diagnostics and troubleshooting

Use `/ready` for orchestration and `/debug/state` for MQTT status, measurement age, mDNS registration, and current stored measurement. If discovery fails, verify host networking/native install, firewall rules, VLAN multicast forwarding, and that a valid retained MQTT measurement has arrived when `DISCOVERY_REQUIRE_MEASUREMENT=true`.

## Security considerations

The API is local and unauthenticated by design. Do not expose it to the internet. Use trusted VLANs/firewalls, MQTT authentication, and MQTT TLS on untrusted networks. Disable the debug endpoint if local measurement data is sensitive.

## Project status and limitations

This is a first, experimental implementation. It has not been certified, endorsed, or hardware-confirmed with EcoFlow PowerStream. Behavior may change if third-party applications, firmware, APIs, or discovery validation change.

## Disclaimer

This is an independent, unofficial community project for interoperability and experimentation. It is not affiliated with, endorsed by, sponsored by, certified by, or otherwise associated with EcoFlow or HomeWizard. Use it at your own risk; it is not a certified meter, safety system, export limiter, or billing device. See `DISCLAIMER.md`.

## Contributing

See `CONTRIBUTING.md`. Contributions must be original and must not include proprietary firmware, private keys, vendor code, logos, copied proprietary documentation, or GPL code unless licensing is reconsidered.

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.

## References

Consult official HomeWizard local API documentation, python-zeroconf documentation, MQTT protocol documentation, aiohttp, aiomqtt, and pydantic-settings documentation. This README summarizes behavior without copying extensive third-party text.
