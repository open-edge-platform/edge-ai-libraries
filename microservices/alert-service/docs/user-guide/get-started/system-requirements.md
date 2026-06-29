# System Requirements

## Hardware Requirements

- **CPU**: x86_64 or compatible processor.
- **Memory**: 4 GB RAM minimum.
- **Disk**: 2 GB free space recommended for log files and Docker image layers.

| Device  | Minimum    | Recommended |
| ------- | ---------- | ----------- |
| CPU     | x86_64     | Dual-core   |
| Memory  | 4 GB RAM   | 8 GB RAM    |
| Disk    | 2 GB free  | 5 GB free   |

## Software Requirements

### Operating System

- Ubuntu 22.04 LTS (validated) or a compatible Linux distribution, Windows, or macOS.
- For container deployment: Docker Engine 24+ and Docker Compose v2.

### Host Packages (Standalone Run)

For local development or standalone execution, make sure you have python dev tools installed. If you plan to test MQTT locally outside Docker, the MQTT client tools can be installed using:

```bash
sudo apt-get update
sudo apt-get install -y mosquitto-clients
```

### Python

- Python 3.10 or newer.
- Dependencies installed from `requirements.txt`.

## Network Requirements

- Inbound access to TCP port `8000` (default) for REST API and WebSocket clients.
- Outbound access to external webhooks (if configured).
- Port `1883` access for MQTT broker communication (embedded Mosquitto broker exposes port `1883` on localhost).
- Port `9001` access if using MQTT-over-WebSockets.
