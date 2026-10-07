# Get Started

Sensor Manager discovers USB and ONVIF network cameras and exposes them through a REST API.

## Prerequisites

- See [System Requirements](./get-started/system-requirements.md).

## Run with Docker Compose

1. Go to the component directory:

   ```bash
   cd edge-ai-libraries/microservices/sensor-manager
   ```

2. Build the image and start the service (`.env` is created from `.env.example` on first run):

   ```bash
   make build run
   ```

3. List the discovered cameras:

   ```bash
   curl http://localhost:8090/api/v1/sensors
   ```

4. Load the ONVIF profiles of a network camera:

   ```bash
   curl -X POST http://localhost:8090/api/v1/sensors/network-camera-192.168.1.100-80/profiles \
     -H "Content-Type: application/json" \
     -d '{"username": "<user>", "password": "<password>"}'
   ```

   Avoid putting real passwords in your shell history. For example, read them from a file or an
   environment variable.

5. Stop the service:

   ```bash
   make stop
   ```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SENSOR_MANAGER_HOST` | `0.0.0.0` | Bind address of the HTTP server |
| `SENSOR_MANAGER_PORT` | `8090` | HTTP port |
| `ONVIF_DISCOVERY_ENABLED` | `true` | Enable the periodic WS-Discovery sweep |
| `ONVIF_DISCOVERY_INTERVAL_S` | `20` | Seconds between discovery sweeps (minimum 1) |
| `LOG_LEVEL` | `INFO` | Python log level |
| `VIDEO_GID` | `44` | Host GID of the `video` group (Docker Compose only) |

## Networking and Security Notes

- ONVIF WS-Discovery sends a UDP multicast probe to `239.255.255.250:3702` and receives unicast
  replies, which do not pass Docker's bridge NAT. The container therefore uses
  `network_mode: host`, so the API is reachable on all host interfaces on `SENSOR_MANAGER_PORT`.
  The API has no authentication: restrict access with a firewall, or set `SENSOR_MANAGER_HOST`
  to a specific address.
- Containers on a bridge network reach the service through the host gateway, for example with
  `extra_hosts: ["host.docker.internal:host-gateway"]` and
  `http://host.docker.internal:8090`.
- `/dev` is mounted read-only. Access to V4L2 (`c 81:*`) and USB (`c 189:*`) character devices
  is granted with `device_cgroup_rules`. The container runs as a non-root user with a read-only
  root filesystem and all capabilities dropped.

## Learn More

- [Build from Source](./get-started/build-from-source.md)
- [Deploy with Helm Chart](./get-started/deploy-with-helm-chart.md)
- [API Reference](./api-reference.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements
./get-started/build-from-source
./get-started/deploy-with-helm-chart

:::
hide_directive-->
