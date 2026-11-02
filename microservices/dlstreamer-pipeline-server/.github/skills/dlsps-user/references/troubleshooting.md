# Troubleshooting Reference

Common issues with DL Streamer Pipeline Server and their solutions.

---

## GPU / NPU Access Issues

### Container cannot access GPU or NPU

**Symptom:** Pipeline fails with device access errors.

**Solution:** Set the `RENDER_GID` environment variable before starting Docker Compose:

```bash
export RENDER_GID=$(stat -c "%g" /dev/dri/render* | head -1)
# Or add to .env file: RENDER_GID=<group_id>
docker compose up
```

The default `docker-compose.yml` already includes device rules for `/dev/dri` (GPU) and
`/dev/accel` (NPU).

---

### NPU Inference Not Working

**Pre-requisites:** Intel NPU drivers must be installed on the host. Refer to
[DL Streamer NPU driver docs](https://github.com/open-edge-platform/dlstreamer/blob/main/docs/user-guide/dev_guide/advanced_install/advanced_install_guide_prerequisites.md#optional-prerequisite-2---install-intel-npu-drivers).


---

## RTSP / WebRTC Issues

### RTSP Streaming Fails with GPU Pipeline

**Symptom:** RTSP stream is blank or fails when GPU elements are in the pipeline.

**Cause:** RTSP expects CPU buffers, but GPU pipeline produces VA memory buffers.

**Solution:** Add `vapostproc ! video/x-raw` before `appsink`:

```
... ! gvametapublish name=destination ! vapostproc ! video/x-raw ! appsink name=appsink
```

---

### RTSP Streaming Fails with UDF Pipeline

**Symptom:** RTSP fails when using `udfloader` (outputs RGB/BGR format).

**Solution:** Add format conversion before `appsink`:

```
... ! gvametapublish name=destination ! videoconvert ! video/x-raw, format=(string)NV12 ! appsink name=appsink
```

---

### Axis RTSP Camera Freezes or Pipeline Stops

**Solution:** Restart the DL Streamer Pipeline Server container.

---

### WebRTC Stream Not Visible in Browser

**Symptom:** Browser cannot display WebRTC stream.

**Cause:** Firewall may be blocking connections.

**Solution:**

```bash
sudo ufw disable    # Or add specific port exceptions
```

---

## Image Ingestor / Latency

### Slow First Inference in Image Ingestor Mode

**Expected behavior:** The first inference is slower, especially on GPU (up to 15 seconds).
Subsequent inferences are fast.

**Mitigation:** When using `sync` mode, provide a `timeout` value that accommodates first
inference latency.

---

## Helm / Kubernetes Deployment

### Deploying with Intel GPU K8s Extension

Set in `helm/values.yaml`:

```yaml
gpu:
  enabled: true
  type: "gpu.intel.com/i915"    # For PTL GPU: "gpu.intel.com/xe"
  count: 1
```

### Deploying without Intel GPU K8s Extension

```yaml
privileged_access_required: true
gpu:
  enabled: false
```

### Deploying with Intel NPU K8s Extension

```yaml
npu:
  enabled: true
  count: 1
```

### Deploying without Intel NPU K8s Extension

```yaml
privileged_access_required: true
npu:
  enabled: false
```

---

## Prometheus / Telemetry

### Time Sync Warning in Prometheus

**Symptom:** `Detected xxx seconds time difference between your browser and the server.`

**Solution:** Synchronize system time with NTP:

```bash
sudo apt install systemd-timesyncd
sudo systemctl restart systemd-timesyncd
systemctl status systemd-timesyncd
```

If behind a corporate proxy, configure NTP server in `/etc/systemd/timesyncd.conf`:

```ini
[Time]
NTP=your.ntp.server.com
```

---

## Docker Compose Issues

### Docker Compose v2 Required on Ubuntu 24.04

Install `docker compose v2` (the plugin version, not standalone `docker-compose`).

### Viewing Container Logs

```bash
docker logs -f <CONTAINER_NAME>
```

### Increasing GStreamer Debug Output

Set in `.env` or as an environment variable:

```bash
GST_DEBUG=1        # Basic logging
GST_DEBUG=3        # Detailed logging
```

---

## Common Port Reference

| Service | Port |
|---------|------|
| REST API | 8080 |
| RTSP output | 8554 |
| MQTT broker | 1883 |
| WebRTC (MediaMTX) | 8889 |
| Prometheus | 9999 |
| Grafana | 3000 |
| OPC UA | 48010 |
| InfluxDB | 8086 |
| S3 / MinIO | 9000 |
| OpenTelemetry collector | 4318 |
