# Service Setup Reference

This document covers starting DL Streamer Pipeline Server, building from
source, and configuring environment variables.

---

## Prerequisites

- Docker and Docker Compose v2 installed
- (For GPU/NPU) Intel GPU or NPU device available on the host
- Sufficient disk space for models and video resources

---

## Quick Start (Pre-built Image)

```bash
# 1. Sparse checkout only the pipeline server component
git clone --filter=blob:none --sparse https://github.com/open-edge-platform/edge-ai-libraries.git -b release-2026.2.0
cd edge-ai-libraries
git sparse-checkout set microservices/dlstreamer-pipeline-server
cd microservices/dlstreamer-pipeline-server/docker

# 2. (GPU/NPU only) Set render group ID
export RENDER_GID=$(stat -c "%g" /dev/dri/render* | head -1)
# Or add RENDER_GID=<id> to the .env file

# 3. Pull the pre-built image
docker pull "$(grep ^DLSTREAMER_PIPELINE_SERVER_IMAGE= .env | cut -d= -f2-)"

# 4. Start the service
docker compose up
```

The service starts on port **8080** (REST API) and **8554** (RTSP output).

### Verify Service is Running

```bash
curl http://localhost:8080/pipelines
# Returns JSON array of available pipeline definitions
```

---

## Pull Image from Docker Hub

The pre-built image is available on Docker Hub:

```bash
docker pull intel/dlstreamer-pipeline-server:latest
```

See all available tags at: https://hub.docker.com/r/intel/dlstreamer-pipeline-server/tags

---

## Custom Pipeline Configs

Mount a custom `config.json` to replace the default pipeline configuration:

```yaml
# In docker-compose.yml, under dlstreamer-pipeline-server volumes:
volumes:
  - "../configs/my_custom_config/config.json:/home/pipeline-server/config.json"
```

### Available Sample Configs

| Config directory | Purpose |
|------------------|---------|
| `configs/default/` | Basic CPU inference (default) |
| `configs/sample_cpu_decode_and_inference/` | CPU-only decode and inference |
| `configs/sample_gpu_decode_and_inference/` | GPU VA-API decode + inference |
| `configs/sample_npu_decode_and_inference/` | NPU decode + inference |
| `configs/sample_mqtt_publisher/` | MQTT metadata publishing |
| `configs/sample_image_ingestor/` | Image file input via REST |
| `configs/sample_s3write/` | S3-compatible storage output |
| `configs/sample_opcua/` | OPC UA protocol publishing |
| `configs/sample_ros2_publisher/` | ROS2 topic publishing |
| `configs/sample_influx/` | InfluxDB timeseries storage |
| `configs/open_telemetry/` | OpenTelemetry + Prometheus + Grafana |
| `configs/model_registry/` | Dynamic model loading via Model Registry |

---

## Environment Variables

### Core (Mandatory)

| Variable | Default | Purpose |
|----------|---------|---------|
| `REST_SERVER_PORT` | `8080` | REST API port |
| `ENABLE_RTSP` | `true` | Enable RTSP frame streaming |
| `RTSP_PORT` | `8554` | RTSP output port |
| `PIPELINE_SERVER_USER` | `intelmicroserviceuser` | Container user |
| `UID` | `1999` | User ID in container |

### GPU / NPU

| Variable | Purpose |
|----------|---------|
| `RENDER_GID` | Render group ID for GPU/NPU device access |
| `GST_DEBUG=1` | GStreamer debug logging |

### MQTT

| Variable | Default | Purpose |
|----------|---------|---------|
| `MQTT_HOST` | — | MQTT broker IP address |
| `MQTT_PORT` | `1883` | MQTT broker port |

### S3 Storage

| Variable | Purpose |
|----------|---------|
| `S3_STORAGE_HOST` | S3/MinIO host address |
| `S3_STORAGE_PORT` | S3/MinIO port (default `9000`) |
| `S3_STORAGE_USER` | S3 access username |
| `S3_STORAGE_PASS` | S3 access password |

### OPC UA

| Variable | Purpose |
|----------|---------|
| `OPCUA_SERVER_IP` | OPC UA server address |
| `OPCUA_SERVER_PORT` | OPC UA port (default `48010`) |
| `OPCUA_SERVER_USERNAME` | OPC UA username |
| `OPCUA_SERVER_PASSWORD` | OPC UA password |

### InfluxDB

| Variable | Purpose |
|----------|---------|
| `INFLUXDB_HOST` | InfluxDB host address |
| `INFLUXDB_PORT` | InfluxDB port (default `8086`) |
| `INFLUXDB_USERNAME` | InfluxDB username |
| `INFLUXDB_PASS` | InfluxDB password |

### OpenTelemetry

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_OPEN_TELEMETRY` | `false` | Enable telemetry export |
| `OTEL_COLLECTOR_HOST` | `otel-collector` | Collector host |
| `OTEL_COLLECTOR_PORT` | `4318` | Collector port |
| `OTEL_EXPORT_INTERVAL_MILLIS` | `5000` | Export interval in ms |
| `PROMETHEUS_PORT` | `9999` | Prometheus metrics port |
| `GRAFANA_PORT` | `3000` | Grafana dashboard port |

### WebRTC

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_WEBRTC` | `false` | Enable WebRTC streaming |
| `WHIP_SERVER_IP` | — | MediaMTX server IP |
| `WHIP_SERVER_PORT` | `8889` | MediaMTX server port |

### Build

| Variable | Purpose |
|----------|---------|
| `BUILD_TARGET` | `dlstreamer-pipeline-server` (optimized) or `dlstreamer-pipeline-server-extended` |
| `BASE_IMAGE` | Base DL Streamer image (e.g. `intel/dlstreamer:2026.1.0-ubuntu24`) |
| `DLSTREAMER_PIPELINE_SERVER_IMAGE` | Full image name for build/run |

### Miscellaneous

| Variable | Purpose |
|----------|---------|
| `LOG_LEVEL` | `INFO`, `DEBUG`, `WARN`, `ERROR` |
| `ADD_UTCTIME_TO_METADATA` | Add UTC timestamp to metadata output |
| `HTTPS` | Set `true` to enable SSL/TLS (mount certificates) |
| `http_proxy` / `https_proxy` / `no_proxy` | Proxy configuration |

---

## Helm Deployment

For Kubernetes deployments see the Helm chart at `helm/`.

```bash
cd edge-ai-libraries/microservices/dlstreamer-pipeline-server/helm

# Edit values.yaml for your environment, then:
helm install dlsps . -n apps --create-namespace
```

### Key Helm Values

```yaml
namespace: apps
env:
  LOG_LEVEL: "INFO"
  REST_SERVER_PORT: "8080"
  ENABLE_RTSP: "true"

gpu:
  enabled: false          # true if K8s GPU device plugin installed
  type: "gpu.intel.com/i915"
  count: 1

npu:
  enabled: false          # true if K8s NPU device plugin installed
  count: 1

config:
  dlstreamer_pipeline_server:
    ext:
      rest_api_port: "30007"
      rtsp_output_port: "30025"
```

- **With GPU K8s Extension:** set `gpu.enabled: true`
- **Without GPU K8s Extension:** set `privileged_access_required: true`
- Same pattern applies for NPU

---

## Access Points

| Service | URL |
|---------|-----|
| REST API | `http://localhost:8080` |
| RTSP output | `rtsp://<host-ip>:8554/<pipeline-path>` |
| WebRTC (if enabled) | `http://<host-ip>:8889` |
| Prometheus (if enabled) | `http://localhost:9999` |
| Grafana (if enabled) | `http://localhost:3000` |

---

## Docker Compose Files

| File | Purpose |
|------|---------|
| `docker/docker-compose.yml` | Main service + MQTT broker |
| `docker/docker-compose-mediamtx.yml` | Add WebRTC streaming via MediaMTX |
| `docker/docker-compose-otel.yml` | Add OpenTelemetry + Prometheus + Grafana |
