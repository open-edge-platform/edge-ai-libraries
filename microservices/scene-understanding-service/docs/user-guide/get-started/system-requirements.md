# System Requirements

## Hardware Requirements

- **CPU**: x86_64. Intel Core Ultra (Meteor Lake) or newer is recommended.
  Older Intel Core / Xeon processors will run the service but may be slower
  when the optional behavioral-analysis path is enabled.
- **Memory**: 4 GB RAM minimum for the service itself. 8 GB or more is
  recommended when many concurrent person sessions are tracked.
- **Disk**: 5 GB free space for the image and logs. Evidence frames are stored
  in SeaweedFS (a separate service), not on the service's local disk.
- **GPU**: Not required by this service. The optional behavioral-analysis
  worker (pose + VLM) is a separate microservice that may use a GPU.

| Device          | Minimum    | Recommended                              |
| --------------- | ---------- | ---------------------------------------- |
| CPU             | x86_64     | Intel Core Ultra (Meteor Lake) or newer  |
| Memory          | 4 GB RAM   | 8 GB RAM or more                         |
| Disk            | 5 GB free  | SSD/NVMe                                 |
| GPU             | Not needed | Used only by the separate BA worker      |

## Software Requirements

### Operating System

- Ubuntu 22.04 LTS (validated) or a compatible Linux distribution.
- For container deployment: Docker Engine and Docker Compose v2.

### Python (Standalone Run)

- Python 3.11 or newer.
- [`uv`](https://docs.astral.sh/uv/) package manager (used to create the
  virtual environment and install dependencies from `pyproject.toml`).

## External Dependencies

The service is an event consumer/producer and depends on external
infrastructure at runtime:

| Dependency               | Required?              | Purpose                                            |
| ------------------------ | ---------------------- | -------------------------------------------------- |
| SceneScape MQTT broker   | Yes (functional)       | Source of all person and zone events.              |
| SceneScape REST API      | Yes (functional)       | Zone auto-discovery (zone name → UUID).            |
| SeaweedFS                | Only if BA rules used  | Evidence frame storage for escalation.             |
| behavioral-analysis      | Only if BA rules used  | Pose + VLM analysis over MQTT.                     |
| alert-service            | Optional               | Routes/delivers generated alerts.                  |

The service starts and serves its API even when these are unavailable; it
retries the MQTT connection in the background. It only produces meaningful
output once a SceneScape deployment is reachable.

## Network Requirements

- Outbound access to the SceneScape MQTT broker (default TCP `1883`, or `8883`
  with TLS) and the SceneScape REST API (HTTPS).
- Inbound access to TCP port `8082` (default) for API clients.
- When the optional features are enabled, network reachability to SeaweedFS,
  the behavioral-analysis worker (shared MQTT broker), and the alert-service.
