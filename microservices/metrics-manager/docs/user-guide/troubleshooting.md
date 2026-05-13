# Troubleshooting

This guide covers common issues and solutions.

## Connection and Startup

### Connection Refused on Port 9090

**Symptom**: `curl: (7) Failed to connect to localhost port 9090: Connection refused`

**Check:**
1. Container is running: `docker ps | grep metrics-manager`
2. Port is bound: `docker port metrics-manager`
3. Service is healthy: `docker logs metrics-manager | tail -20`

**Solution:**
```bash
# Check if container is running
docker ps

# If not running, start it
docker compose up -d

# Check logs for errors
docker logs metrics-manager
```

---

## Metrics Not Appearing

### Custom Metric Not Appearing on `/api/v1/metrics`

**Symptom**: Metric accepted (201 response) but doesn't appear in query.

**Check:**
```bash
# Verify metric was accepted
curl -X POST http://localhost:9090/api/v1/metrics/simple \
  -H "Content-Type: application/json" \
  -d '{"name": "test_metric", "value": 42}'

# Query immediately
curl http://localhost:9090/api/v1/metrics | jq '.metrics | keys'
```

**Causes and Solutions:**

| Cause | Solution |
|-------|----------|
| Metric expired (default 300s) | Set `METRICS_RETENTION_SECONDS=3600` to keep longer |
| Memory limit reached | Set `MAX_METRICS_IN_MEMORY=500000` to increase limit |
| Telegraf :8186 unreachable | Check Telegraf is running: `docker logs metrics-manager \| grep telegraf` |
| Invalid metric format | Check request format matches one of the four supported formats |

---

### Custom Metric Not Appearing in Prometheus (`:9273/metrics`)

**Symptom**: Custom metric appears in `/api/v1/metrics` but not in `:9273/metrics`.

**Root cause**: Metric hasn't been persisted to Telegraf yet (debounced 100ms by default).

**Solution:**
```bash
# Wait a moment and check again
sleep 1
curl http://localhost:9273/metrics | grep my_metric
```

Or reduce debounce delay:
```bash
FILE_PERSIST_DEBOUNCE_MS=10 docker compose up
```

---

### Custom Metric Not Appearing in SSE Stream

**Symptom**: Metric in Prometheus endpoint but not in `/metrics/stream`.

**Root cause**: SSE client not polling frequently enough (default 500ms).

**Solution:**
1. Reduce polling interval:
   ```bash
   PROMETHEUS_POLLER_INTERVAL_MS=100 docker compose up
   ```

2. Wait for next polling cycle:
   ```bash
   # Default 500ms polling interval
   sleep 1
   curl -N -H "Accept: text/event-stream" http://localhost:9090/metrics/stream
   ```

---

## GPU and NPU Metrics

### No GPU Metrics

**Symptom**: No `gpu_*` or `engine_usage_*` metrics in `:9273/metrics`.

**Check:**
```bash
# Verify Intel GPU is present
lspci | grep -i intel | grep -i graphics

# Check qmassa FIFO exists
docker exec metrics-manager ls -la /app/qmassa.fifo

# Check if qmassa is running
docker exec metrics-manager supervisorctl -c /etc/supervisor/supervisord.conf status qmassa

# View qmassa logs
docker logs metrics-manager | grep qmassa
```

**Solutions:**

| Issue | Fix |
|-------|-----|
| No Intel GPU | Expected. qmassa logs `No DRM devices found` and exits. Other metrics continue. |
| `/dev/dri` not accessible | Ensure `--device /dev/dri` in `docker run` or `devices:` in `compose.yaml` |
| Old GPU drivers | Update GPU drivers: `sudo apt update && sudo apt install intel-media-driver` (Ubuntu) |
| qmassa process crashed | Check logs: `docker logs metrics-manager \| grep -i qmassa` |

---

### No NPU Metrics

**Symptom**: No `npu_power`, `npu_frequency`, etc. in `:9273/metrics`.

**Check:**
```bash
# Verify Intel NPU driver is loaded
ls /sys/bus/pci/drivers/intel_vpu/

# Check PMT sysfs interface
ls /sys/class/intel_pmt/

# Verify privileged mode
docker inspect metrics-manager | grep Privileged

# Check npu_reader logs
docker exec metrics-manager cat /app/npu_reader_trace.log

# View supervisord status
docker exec metrics-manager supervisorctl -c /etc/supervisor/supervisord.conf status
```

**Solutions:**

| Issue | Fix |
|-------|-----|
| `intel_vpu` driver not loaded | Load it: `sudo modprobe intel_vpu` (host) |
| Container not privileged | Run with `privileged: true` (Docker) or `docker run --privileged` |
| `/sys` not accessible | Mount with `--privileged` or `-v /sys:/sys:ro` |
| Old hardware (pre-PTL) | `npu_memory_mb` returns `-1` — expected on MTL/ARL |
| No NPU hardware | Expected. Reader logs warning, then enters idle mode. Other metrics continue. |

---

## Telegraf Issues

### Telegraf Metrics Empty

**Symptom**: `:9273/metrics` returns 404 or empty response.

**Check:**
```bash
# Verify Telegraf is running
docker exec metrics-manager supervisorctl -c /etc/supervisor/supervisord.conf status telegraf

# Check Telegraf logs
docker logs metrics-manager | grep -i telegraf

# Check Telegraf config syntax
docker exec metrics-manager telegraf -config /etc/telegraf/telegraf.conf -test
```

**Common issues:**

| Issue | Solution |
|-------|----------|
| Telegraf config error | Check logs: `docker logs metrics-manager \| grep -i error` |
| CPU metrics disabled | Verify `[[inputs.cpu]]` block in `telegraf.conf` |
| Prometheus output not configured | Verify `[[outputs.prometheus_client]]` in `telegraf.conf` |

---

## Rate Limiting

### Rate Limited (429 Too Many Requests)

**Symptom**: `HTTP/1.1 429 Too Many Requests`

**Check:**
```bash
# Current rate limit config
curl http://localhost:9090/api/v1/stats | jq '.requests_total, .errors_total'
```

**Solution:**

Increase rate limits in `.env`:

```bash
RATE_LIMIT_REQUESTS_PER_MINUTE=5000
RATE_LIMIT_BURST=500
```

Then restart:

```bash
docker compose down && docker compose up -d
```

---

## Logging and Debugging

### Find Correlation IDs in Logs

```bash
# Search logs by correlation ID
docker logs metrics-manager 2>&1 | grep "correlation_id.*abc-123"

# Or use jq for JSON logs
docker logs metrics-manager 2>&1 | jq 'select(.correlation_id == "abc-123")'
```

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG docker compose up
```

This logs all requests, responses, and internal state.

### Check Service Health

```bash
# Basic health
curl http://localhost:9090/health | jq .

# Internal stats
curl http://localhost:9090/api/v1/stats | jq .

# Detailed health with store info
curl http://localhost:9090/api/health | jq .
```

---

## Graceful Shutdown

Shutdown is handled by uvicorn/FastAPI on SIGTERM and SIGINT:

```bash
# Graceful shutdown (waits up to 60s for in-flight requests)
docker compose down

# Force kill (less safe)
docker compose kill
```

---

## Memory Protection

Automatic eviction prevents memory exhaustion:

- Default limit: 100,000 metrics in memory
- Oldest metrics evicted when limit reached
- Configure via `MAX_METRICS_IN_MEMORY`

**To see memory usage:**

```bash
# Docker stats
docker stats metrics-manager

# Inside container
docker exec metrics-manager ps aux | grep uvicorn
```

---

## Docker-Specific Issues

### Port Already in Use

**Symptom**: `docker: Error response from daemon: driver failed programming external connectivity on endpoint metrics-manager`

**Solution:**

1. Change ports in `.env`:
   ```bash
   HOST_METRICS_PORT=19090
   HOST_TELEGRAF_PORT=19273
   HOST_TELEGRAF_HTTP_PORT=18186
   ```

2. Or find and stop the process using the port:
   ```bash
   lsof -i :9090  # Find process on port 9090
   kill <PID>     # Kill the process
   ```

### Insufficient Disk Space for Build

**Symptom**: `docker build: Build failed — no space left on device`

**Solution:**

```bash
# Clean up Docker build cache
docker builder prune

# Or remove all unused images
docker system prune -a
```

---

## Testing All Endpoints

Use this script to smoke-test all major endpoints:

```bash
#!/bin/bash
set -e

echo "=== 1. Health ==="
curl -s http://localhost:9090/health | jq .

echo -e "\n=== 2. Push Simple Metric ==="
curl -s -X POST http://localhost:9090/api/v1/metrics/simple \
  -H "Content-Type: application/json" \
  -d '{"name": "test_metric", "value": 123.45}' | jq .

echo -e "\n=== 3. Query Metrics ==="
curl -s http://localhost:9090/api/v1/metrics/latest | jq '.metrics | keys'

echo -e "\n=== 4. Prometheus Format ==="
curl -s http://localhost:9090/metrics | head

echo -e "\n=== 5. Telegraf Endpoint ==="
curl -s http://localhost:9273/metrics | head

echo -e "\n=== 6. SSE Stream (first event) ==="
timeout 2 curl -N -H "Accept: text/event-stream" http://localhost:9090/metrics/stream || true

echo -e "\n=== All tests passed! ==="
```

---

## Getting Help

1. **Check logs**: `docker logs metrics-manager`
2. **Check service health**: `curl http://localhost:9090/api/health`
3. **Increase log level**: `LOG_LEVEL=DEBUG docker compose up`
4. **Search GitHub issues**: https://github.com/open-edge-platform/edge-ai-libraries/issues (use `metrics-manager` label)
5. **Manual endpoint testing**: Use curl commands from [API Reference](./api-reference.md)

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0

## Supporting Resources

- [API Reference](./api-reference.md)
- [Configuration Guide](./get-started/environment-variables.md)
- [How It Works](./how-it-works.md)
- [Get Started Guide](./get-started.md)
