# Contributing

## Development setup

Use Python 3.12 or newer:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Checks

```sh
ruff check .
ruff format --check .
mypy
pytest
docker build -t virtual-smart-meter-ecoflow .
```

Contributions must be original work. Do not submit proprietary firmware, private keys, vendor application code, logos, or copied proprietary documentation. Do not copy GPL-licensed code, including wmbusmeters code, unless the project licensing strategy is explicitly reconsidered first.

Sanitize interoperability captures before publication. Packet captures may include private IP addresses, hostnames, serial numbers, device identifiers, MQTT topics, and measurement data.
