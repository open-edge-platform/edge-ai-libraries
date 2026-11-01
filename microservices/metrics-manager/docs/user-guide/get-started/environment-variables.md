# Environment Variables

Configuration is managed via environment variables. All variables map directly to Pydantic Settings field names (case-insensitive). The `.env` file is loaded automatically by `docker compose up`.

## Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | API server bind address |
| `METRICS_PORT` | `9090` | Metrics Manager API port |
| `SERVICE_NAME` | `metrics-manager` | Service name used in logs and health checks |
| `SERVICE_VERSION` | `2026.2.0` | Service version reported in health endpoints |
| `ENVIRONMENT` | `production` | Deployment environment: `development`, `staging`, `production`. Production disables `/docs` and `/redoc` Swagger endpoints |
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_FORMAT` | `json` | Log format: `json` (structured, for log aggregators) or `text` (human-readable) |
| `LOG_INCLUDE_TIMESTAMP` | `true` | Include timestamp field in log entries |
| `CORS_ORIGINS` | `*` | Allowed CORS origins (comma-separated or JSON array). Set to `http://localhost:3000,http://my-dashboard:3000` to restrict |
| `CORS_ALLOW_CREDENTIALS` | `false` | Allow credentials in CORS requests (cookies, etc.) |
| `METRICS_MANAGER_HOSTNAME` | _(unset)_ | Override the `host=` tag stamped on every metric (Telegraf, qmassa_reader.py, npu_reader.py). Unset = use kernel hostname. Set to a stable value (e.g., `lab-node-42`) to keep Grafana dashboards stable across reboots |
| `HARDWARE_TELEMETRY_ENABLED` | `true` | Start the `qmassa` GPU collector under supervisord. Set to `false` where `/dev/dri` cannot be mapped into the container; CPU, memory, temperature and NPU metrics are unaffected |

## Metrics Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `METRICS_RETENTION_SECONDS` | `300` | How long to keep metrics in memory (seconds). After this duration, metrics are expired and removed on next store access |
| `MAX_METRICS_BATCH_SIZE` | `1000` | Maximum metrics per single batch request (`POST /api/v1/metrics`) |
| `MAX_METRICS_IN_MEMORY` | `100000` | Maximum metrics in memory. When exceeded, oldest entries are evicted automatically |
| `CUSTOM_METRICS_DIR` | `/app/custom-metrics` | Directory where custom metric scripts are executed (via Telegraf `inputs.exec`). Do not change inside container |
| `FILE_PERSIST_DEBOUNCE_MS` | `100` | Debounce interval for Telegraf HTTP persistence (milliseconds). Higher values reduce HTTP calls but increase latency. Range: 10–5000 ms |

## Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | `true` | Enable rate limiting by client IP |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `1000` | Maximum requests per minute per client IP |
| `RATE_LIMIT_BURST` | `100` | Burst allowance (tokens available before rate limit kicks in) |

**Exempt paths**: `/health`, `/api/v1/stats`, and SSE endpoints are NOT rate limited.

## Performance

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_GZIP_COMPRESSION` | `true` | Enable gzip compression for HTTP responses >1 KB. Reduces bandwidth but increases CPU usage |

## Security

| Variable | Default | Description |
|----------|---------|-------------|
| `TRUST_FORWARDED_HEADERS` | `false` | Honor `X-Forwarded-For` / `X-Real-IP` headers for client IP detection. Set to `true` ONLY when running behind a trusted reverse proxy (Nginx, Traefik, etc.) |

> [!WARNING]
> Setting this to `true` without a reverse proxy allows clients to spoof their IP and bypass rate limiting.

## Telegraf Settings (Application Configuration)

These variables configure the Telegraf locations for the application to use:

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAF_CONFIG_PATH` | `/etc/telegraf/telegraf.conf` | Path to Telegraf config inside the container (informational, not loaded by the app) |
| `TELEGRAF_PORT` | `9273` | Telegraf Prometheus endpoint port (where SSE poller fetches system metrics) |
| `TELEGRAF_HTTP_PORT` | `8186` | Port of Telegraf's HTTP listener (`:8186/write`). Set in the image and by `compose.yaml`; must match the port in `TELEGRAF_HTTP_ENDPOINT` |
| `TELEGRAF_HTTP_ENDPOINT` | `http://localhost:8186/write` | Telegraf HTTP listener endpoint used to persist custom metrics in InfluxDB Line Protocol. Must be accessible from the app container |

## Hardware Telemetry Collectors

These variables are read by `entrypoint.sh` at container start. Each one decides whether a Telegraf drop-in from `telegraf.d/` is loaded. **Every collector is off by default**, so a default install, including one that mounts its own `telegraf.conf`, emits the same metrics as before these collectors existed. See [Hardware Telemetry Collectors](./hardware-telemetry.md) for what each one collects, hardware support and series counts.

Accepted "on" values (case-insensitive): `true`, `1`, `yes`, `on`, `auto`.

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_RAPL_POWER` | `false` | Load `10-power.conf`: CPU package RAPL power, per-core frequency, temperature and C-state residency (`inputs.intel_powerstat`). Needs the privileged container. Adds per-core series |
| `ENABLE_PSYS_POWER` | `false` | Load `90-rapl-psys.conf`: RAPL platform (`psys`) and package power via `rapl_reader.py`. Needs the privileged container |
| `ENABLE_DRAM_BW` | `false` | Load `20-dram-bw.conf`: DRAM read/write bandwidth via `perf stat` on the IMC free-running counters. `auto` loads it only when `perf` is installed, which requires an image built with `INSTALL_PERF=true` |
| `ENABLE_DISK_IO` | `false` | Load `30-disk.conf`: per-device I/O counters for whole physical disks (`nvme`, `sd`, `vd`, `mmcblk`) |
| `ENABLE_NET_IO` | `false` | Load `40-net.conf`: `inputs.net` and `inputs.ethtool`. In the default bridge deployment it only sees the container's own interface. The `host-nic-telemetry` Compose profile sets it to `true` by default |
| `ENABLE_INTERRUPTS` | `false` | Load `50-interrupts.conf`: one `interrupts_total` series per device IRQ |
| `ENABLE_TEMP_STATS` | `false` | Load `70-temp-stats.conf`: 100 ms CPU package temperature sampling with per-second min/max/mean |
| `ENABLE_GPU_THROTTLE` | `false` | Load `91-gpu-throttle.conf`: achieved GPU frequency and throttle reasons for the Intel `xe` driver |
| `ENABLE_TURBOSTAT` | `false` | Load `60-turbostat.conf`: IPC, SMI and per-core diagnostics. Skipped with a warning when no usable turbostat binary is present or `/dev/cpu/0/msr` cannot be opened |
| `TURBOSTAT_INTERVAL` | `5` | Turbostat sampling cadence in seconds |
| `TURBOSTAT_BIN` | _(unset)_ | Compose only. Host path of a kernel-matched `turbostat` binary, bind-mounted to `/usr/local/bin/turbostat`. `make up` resolves it when `ENABLE_TURBOSTAT` is on. Only needed with `ENABLE_TURBOSTAT=true` |
| `DRAM_BW_INTERVAL` | `1` | Sampling window in seconds for `dram_bw_reader.py` |

Reader trace logs are written inside the container to `/app/rapl_reader_trace.log`, `/app/dram_bw_reader_trace.log` and `/app/gpu_throttle_reader_trace.log`. Set `RAPL_READER_LOG_FILE`, `DRAM_BW_READER_LOG_FILE` or `GPU_THROTTLE_READER_LOG_FILE` to write them elsewhere.

> [!WARNING]
> Changing any `ENABLE_*` variable requires recreating the container (`docker compose up -d`). There is no hot reload.

## SSE Poller Settings

The SSE endpoint (`/metrics/stream`) polls the Telegraf Prometheus endpoint for each connected client independently. There is no shared queue.

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_POLLER_INTERVAL_MS` | `500` | Polling interval in milliseconds (100–5000). Lower values = more frequent SSE events but higher CPU usage per client. Recommended: 500 ms |
| `PROMETHEUS_TELEGRAF_ENDPOINT` | `http://localhost:9273` | Telegraf Prometheus endpoint polled by SSE clients. Must be accessible from the app container |

## Docker Compose Variables

These variables are used ONLY by `compose.yaml` and are NOT read by the application:

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAF_CONFIG` | `./telegraf.conf` | Host path to Telegraf config file (mounted into container) |
| `TELEGRAF_CONFIG_DIR` | `./telegraf.d` | Host path to the directory of shipped collector drop-ins (mounted read-only at `/etc/telegraf/telegraf.d`). The entrypoint copies only the drop-ins that have the shipped file names and are enabled with `ENABLE_*` into `/etc/telegraf/active.d`; **other files placed here are ignored**. To add your own inputs, use a custom `telegraf.conf` (`TELEGRAF_CONFIG`) |
| `INSTALL_PERF` | `false` | Build argument (`INSTALL_PERF=true make build`). Installs `linux-perf` (GPL-2.0, about 150 MB) into the image, needed for `ENABLE_DRAM_BW` |
| `TURBOSTAT_BIN` | _(unset)_ | See [Hardware Telemetry Collectors](#hardware-telemetry-collectors) |
| `HOST_METRICS_PORT` | `9090` | Host port mapping for Metrics Manager API |
| `HOST_TELEGRAF_PORT` | `9273` | Host port mapping for Telegraf Prometheus endpoint |
| `HOST_TELEGRAF_HTTP_PORT` | `8186` | Host port mapping for Telegraf HTTP listener |

---

## Example Configurations

### Development Setup

```bash
# .env
ENVIRONMENT=development
LOG_LEVEL=DEBUG
LOG_FORMAT=text
CORS_ORIGINS=*
RATE_LIMIT_ENABLED=false
```

### High-Throughput Scenario

```bash
# .env
RATE_LIMIT_REQUESTS_PER_MINUTE=5000
RATE_LIMIT_BURST=500
MAX_METRICS_IN_MEMORY=500000
PROMETHEUS_POLLER_INTERVAL_MS=200
ENABLE_GZIP_COMPRESSION=true
```

### Production with Reverse Proxy

```bash
# .env
ENVIRONMENT=production
LOG_LEVEL=WARNING
LOG_FORMAT=json
CORS_ORIGINS=https://my-dashboard.example.com,https://grafana.example.com
TRUST_FORWARDED_HEADERS=true
METRICS_MANAGER_HOSTNAME=production-node-01
```

### Behind Corporate Proxy

```bash
# .env
http_proxy=http://proxy.example.com:8080
HTTP_PROXY=http://proxy.example.com:8080
https_proxy=http://proxy.example.com:8080
HTTPS_PROXY=http://proxy.example.com:8080
no_proxy=localhost,127.0.0.1
NO_PROXY=localhost,127.0.0.1
```

---

## Custom Metrics Scripts

The image ships with a Telegraf [`inputs.exec`](https://github.com/influxdata/telegraf/blob/master/plugins/inputs/exec/README.md) block that, every 10 seconds, runs **every executable `*.sh` and `*.py` file** it finds in `/app/custom-metrics/` and feeds the stdout straight into the Prometheus endpoint on `:9273`. For details, see [Custom Metrics Scripts](./custom-metrics.md).

Simply dropping a script into the directory is the easiest way to publish a metric the service does not collect by default.

### How the Directory is Wired

- The directory is created by the Dockerfile (`/app/custom-metrics`)
- In `compose.yaml` it is mounted as a named volume `custom-metrics:`, so scripts survive container restarts
- `telegraf.conf` ships this block (do not edit unless you know what you are doing):

```toml
[[inputs.exec]]
  commands = ["/bin/sh -c 'for f in /app/custom-metrics/*.sh /app/custom-metrics/*.py; do [ -f \"$f\" ] && [ -x \"$f\" ] && \"$f\"; done 2>/dev/null; true'"]
  timeout = "5s"
  data_format = "influx"
  interval = "10s"
```

### Script Requirements

Each script must:

- Be **executable** (`chmod +x`)
- Print **InfluxDB Line Protocol** on stdout, one metric per line
- Finish **within 5 seconds** (Telegraf kills longer runs)
- Produce clean output (no debug prints, banners, or stderr)
- Handle errors gracefully (non-zero exit codes do not crash Telegraf)

### Example: Fan RPM Metric

See [Custom Metrics Scripts](./custom-metrics.md#end-to-end-example-fan-rpm-metric) for a complete end-to-end example.

---

## Optional Components

The Metrics Manager image includes optional components that are bundled but not active by default:

### qmmd (Prometheus GPU Exporter)

**What it is:** A lightweight Prometheus exporter for Intel Arc GPUs. It reads GPU metrics from sysfs and exposes them in Prometheus format.

**Current Status:** Bundled in the image but **NOT started by default**.

**Why not enabled:** The default Metrics Manager already collects GPU metrics via `qmassa_reader.py` and Telegraf's `inputs.execd`. Using both would be redundant.

**When to enable:** If you want a dedicated GPU metrics exporter that outputs to a separate Prometheus port (typically `:9100` or similar) without going through Telegraf.

**How to enable:** Edit `supervisord.conf` or extend it in your downstream image:

```ini
[program:qmmd]
command=/usr/local/bin/qmmd
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
priority=40
```

**License:** Prometheus exporter for Intel® GPUs, published on crates.io under the MIT license. See <https://crates.io/crates/qmmd>.

---

## Optional Services & Extending supervisord

The container's bundled `supervisord.conf` contains an `[include]` section:

```ini
[include]
files=/etc/supervisor/conf.d/*.conf
```

Any `*.conf` file dropped into `/etc/supervisor/conf.d/` is picked up automatically at supervisord start, so you do not need to fork or edit `supervisord.conf` to add your own programs.

### Pattern: Add a Program in Your Downstream Image

```dockerfile
FROM intel/metrics-manager:2026.2.0

# Drop additional supervisord program units into the include directory.
COPY my-extra-service.conf /etc/supervisor/conf.d/my-extra-service.conf
```

`my-extra-service.conf`:

```ini
[program:my-extra-service]
command=/usr/local/bin/my-extra-service --flag
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
priority=40   ; >30 = starts after metrics-manager (priority 20)
```

### Verify the Extra Unit is Running

```bash
docker exec metrics-manager supervisorctl -c /etc/supervisor/supervisord.conf status
# my-extra-service                 RUNNING   pid 47, uptime 0:01:23
```

---

## Custom Telegraf Configuration

### Mount Custom Config

```yaml
# compose.yaml
services:
  metrics-manager:
    volumes:
      - ./my-telegraf.conf:/etc/telegraf/telegraf.conf:ro
```

Or via environment:

```bash
TELEGRAF_CONFIG=./my-telegraf.conf docker compose up
```

### Shipped Collector Drop-ins

`telegraf.d/` holds the drop-ins for the [hardware telemetry collectors](./hardware-telemetry.md). Enable them with the `ENABLE_*` variables rather than by editing files. You can edit a shipped drop-in (for example the `devices` filter in `30-disk.conf`) and mount your copy with `TELEGRAF_CONFIG_DIR`, but a file with a new name is **not** loaded: only the drop-ins that the entrypoint knows about are copied into the directory Telegraf reads.

To add your own Telegraf inputs, put them in your own `telegraf.conf` and mount it with `TELEGRAF_CONFIG`, or use [custom metrics scripts](./custom-metrics.md).

### Example: Disable GPU or NPU Metrics

The default `telegraf.conf` registers both GPU (qmassa) and NPU readers as `[[inputs.execd]]` blocks. To disable:

```toml
# my-telegraf.conf (omit GPU/NPU inputs)
[agent]
  interval = "1s"

[[outputs.prometheus_client]]
  listen = ":9273"

[[inputs.cpu]]
[[inputs.mem]]
# GPU and NPU inputs omitted
```

---

## Structured Logging

Logs are output in JSON format by default for easy parsing by log aggregators:

```json
{
  "timestamp": "2026-03-04T10:15:30.123456Z",
  "level": "INFO",
  "logger": "app.routes",
  "message": "Accepted metrics via batch",
  "correlation_id": "abc-123-def",
  "extra": {"count": 10}
}
```

Switch to human-readable format for development:

```bash
LOG_FORMAT=text docker compose up
```

## Correlation IDs

Every request is assigned a correlation ID for distributed tracing. Pass your own via header or receive an auto-generated UUID:

```bash
curl -H "X-Correlation-ID: my-trace-123" http://localhost:9090/api/v1/metrics
# Response header: X-Correlation-ID: my-trace-123
```

Correlation IDs appear in all log entries for request tracing.

## Supporting Resources

- [Get Started Guide](../get-started.md)
- [System Requirements](./system-requirements.md)
- [Custom Metrics Scripts](./custom-metrics.md)
- [Hardware Telemetry Collectors](./hardware-telemetry.md)
- [Helm Deployment](./deploy-with-helm.md)
- [Troubleshooting](../troubleshooting.md)

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0
