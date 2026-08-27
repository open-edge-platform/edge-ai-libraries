# System Requirements

## Software

| Software | Minimum |
|---|---|
| Docker | 24.0 |
| Docker Compose | 2.20 |

The Docker daemon must be running, and port `5002` must be available for the agent API.

## External Services

A reachable storage API is required and must implement bounded
`GET /detections` and `GET /detections/stats` reads.

MQTT ingestion can use the broker in the Compose deployment or a reachable external broker.

## Hardware

Fallback mode runs without an LLM. LLM mode uses the profile-gated OVMS deployment and requires a supported Intel GPU, appropriate `/dev/dri` access, sufficient memory for the selected model, and network access to obtain model assets.

See [Get Started](../get-started.md) for deployment commands.
