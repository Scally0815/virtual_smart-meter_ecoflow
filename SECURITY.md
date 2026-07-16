# Security

The HTTP API is intentionally local and unauthenticated because it emulates HomeWizard API v1 behavior. Do not expose the HTTP port to the public internet. Run it only on trusted LANs/VLANs and use firewall rules to restrict access.

Use MQTT authentication strongly, and use MQTT TLS when MQTT crosses an untrusted network. Supply credentials through environment variables or secret files. The application must not log MQTT passwords, private keys, tokens, or Authorization headers.

`/debug/state` can reveal local measurement data. Disable it with `DEBUG_ENDPOINT_ENABLED=false` if that data is sensitive.

This project does not include telemetry and should not make outbound connections except to the configured MQTT broker.

Report vulnerabilities through private GitHub security advisories when available, or open an issue with minimal non-sensitive reproduction details.
