# Run with Docker Compose

## Prerequisites

- Docker Engine 24.0+
- Docker Compose v2.x
- YOLO-Pose model files at `./models/yolo_models/yolo26n-pose/` (`.xml` + `.bin`)
- Running instances of SeaweedFS, MQTT broker, and OVMS (for VLM)
- Access to a container registry that hosts `intel/behavioral-analysis:<tag>`

See [System Requirements](system-requirements.md) for details.

---

## Pull the Image

Set the image tag in `.env.local` (for `RELEASE_TAG`) and pull the image before startup:

```bash
docker compose --env-file .env.local pull behavioral-analysis
```

If you prefer to build your own image (for customization, reproducibility, compliance, or local development workflows), follow [build-from-source.md](./build-from-source.md) and then return here to run with Docker Compose.

---

## Run with Docker Compose

Docker Compose starts the behavioral-analysis service. External dependencies (SeaweedFS, MQTT broker, and OVMS) must be reachable from the compose network.

### 1. Configure the environment

```bash
cp .env .env.local
# Edit .env.local with your deployment-specific values
```

Configuration is mandatory for successful startup and analysis.
See [Configuration](configuration.md) for all required environment variables and pattern settings.

### 2. Start the stack

```bash
docker compose --env-file .env.local up -d --no-build
```

### 3. View logs

```bash
docker compose logs behavioral-analysis -f
```

### 4. Stop the stack

```bash
docker compose down
```

---

## Network Configuration

The service uses a Docker network defined in `docker-compose.yml` (currently `ba-network`).

If SeaweedFS, MQTT broker, or OVMS are running in other containers, update the compose network configuration so all services are on a shared reachable network.

The service must be able to resolve and reach:
- `seaweedfs` (or the value of `SEAWEEDFS_ENDPOINT`)
- The MQTT broker hostname
- `ovms-vlm` (or the value of `VLM_ENDPOINT`)

---

## Health Check

The container includes a Docker health check:

```yaml
healthcheck:
  test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]
  interval: 10s
  timeout: 5s
  retries: 10
  start_period: 60s
```

Check health status:

```bash
docker inspect --format='{{.State.Health.Status}}' behavioral-analysis
```

Or call the endpoint directly:

```bash
curl http://localhost:8085/health
```

---

## Container Logs

```bash
docker compose logs behavioral-analysis -f
```

---

## Shutdown

```bash
docker compose down
```

The service handles `SIGTERM` gracefully: the MQTT consumer awaits in-flight analyses before stopping, and the VLM HTTP client is closed cleanly.

---

## Troubleshooting

See [Troubleshooting](../troubleshooting.md) for common container issues.
