# Release Notes

## Version 2026.1.0

**Release Date**: May 11, 2026

### New

- **Server-Sent Events (SSE) Streaming** — New `/metrics/stream` endpoint streams all metrics (system + custom) in real-time via SSE. Each connected client polls the Telegraf Prometheus endpoint independently. Browser requests receive a live HTML table; SSE clients receive raw event stream
  - **Impact**: Dashboards can now consume metrics without polling, enabling real-time visualizations. Replaces the old WebSocket relay model
  
- **Multiple Input Formats** — Accept custom metrics in four formats without code changes:
  - JSON Batch (`POST /api/v1/metrics`) — multiple metrics with multiple fields
  - Simple JSON (`POST /api/v1/metrics/simple`) — single metric, simplest format
  - InfluxDB Line Protocol (`POST /api/v1/metrics/influx`) — standard Influx format
  - OpenTelemetry (OTLP) (`POST /api/v1/metrics/otlp`) — CNCF standard format
  - **Impact**: Any monitoring system can integrate without client library or format conversion

- **Intel NPU Telemetry** — Bundled `npu_reader.py` script collects metrics from Intel NPU:
  - Power draw (watts)
  - Frequency, temperature, utilization
  - Memory usage, bandwidth, tile configuration
  - Supported on Meteor Lake (MTL), Arrow Lake (ARL), Lunar Lake (LNL), Panther Lake (PTL)
  - **Impact**: Full hardware observability for edge AI applications on Intel platforms

- **Custom Metrics Scripts** — Drop executable scripts into `/app/custom-metrics/` (shell or Python). Telegraf runs them every 10 seconds and publishes metrics automatically
  - **Impact**: No REST API calls needed for custom metrics. Simplest way to add application-specific metrics

- **Docker Compose & Kubernetes** — Production-ready `compose.yaml` and Helm chart included
  - Docker Compose for standalone deployments
  - Helm chart published to OCI registry (`oci://registry-1.docker.io/intel/metrics-manager:2026.1.0-helm`)
  - **Impact**: Deploy in 3 commands on Docker or Kubernetes

- **Comprehensive API Reference** — Health checks, statistics, detailed endpoint documentation
  - Basic health (`GET /health`)
  - Detailed health with store statistics (`GET /api/health`)
  - Service statistics (`GET /api/v1/stats`)
  - **Impact**: Easy to integrate into monitoring systems and dashboards

### Improved

- **Debounced Persistence** — Custom metrics are persisted to Telegraf with configurable debounce (default 100ms). Prevents HTTP bottleneck when ingesting high-frequency metrics
  - **Impact**: Support for 1000+ metrics per second without API latency spikes

- **Memory Protection** — Automatic eviction of oldest metrics when in-memory limit is reached (default 100k metrics)
  - **Impact**: Metrics service can't run out of memory even under sustained high ingestion

- **Structured Logging** — JSON-formatted logs by default (with human-readable text option for development)
  - **Impact**: Easy integration with log aggregators (ELK, Datadog, etc.)

- **Rate Limiting** — Per-IP token bucket rate limiting (default 1000 requests/minute per IP)
  - **Impact**: Protection against accidental/malicious floods; health and stats endpoints exempt

- **Correlation IDs** — Every request gets a correlation ID (auto-generated UUID or from `X-Correlation-ID` header) for distributed tracing
  - **Impact**: Easy to track requests through logs and multiple services

- **GZIP Compression** — Automatic compression for HTTP responses >1 KB
  - **Impact**: Reduced bandwidth for metrics streaming (especially important for SSE)

### Known Issues

None at this release. See GitHub issues for feature requests and discussions.

---

## Version 2026.0.1

**Release Date**: May 5, 2026

### Fixed

- **SSE Stream HTML UI** — Browser requests to `/metrics/stream` now receive an HTML page with an in-place updated metrics table (previously showed raw SSE stream)
  - **Impact**: Live dashboard experience in browser without client-side framework

- **Content Negotiation** — `/metrics/stream` auto-detects client type:
  - Browser (`Accept: text/html`) → HTML page
  - SSE client (`Accept: text/event-stream`) → raw stream
  - **Impact**: Single endpoint works for both browsers and programmatic clients

---

## Version 2026.0.0

**Release Date**: April 1, 2026

### New

- **Initial Release** — Metrics Manager with:
  - Telegraf-based system metrics collection (CPU, RAM, temperature, GPU, NPU)
  - FastAPI REST interface for custom metrics ingestion
  - In-memory metrics store with configurable retention
  - Prometheus-compatible output (`GET /metrics`, `:9273/metrics`)
  - Real-time SSE streaming (`GET /metrics/stream`)

---

## Versions and Dependencies

### Current Image

- Intel® Metrics Manager **2026.1.0**
- Telegraf **1.37.3** (system metrics agent)
- qmassa **1.3.1** (Intel® GPU telemetry via named pipe)
- qmmd **0.1.1** *(optional)* — Lightweight Prometheus GPU exporter (bundled but **not started by default**; use only if you need a separate GPU metrics port)
- Intel® NPU telemetry via bundled `npu_monitor_tool` / `npu_reader`
- Python **3.12** runtime + FastAPI service
- supervisord process supervisor

**Note on qmmd:** The default Metrics Manager already collects GPU metrics via `qmassa_reader.py` and Telegraf. Enable qmmd only if you need a standalone Prometheus exporter on a separate port. See [Configuration Guide](./get-started/environment-variables.md#optional-components) for details.

---

## Support Matrix

| Component | Version | Support |
|-----------|---------|---------|
| Docker | 24.0+ | Required |
| Kubernetes | 1.25+ | Via Helm chart |
| Python | 3.12 | Included in image |
| Linux Kernel | 5.4+ | Required for system metrics collection |

---

## Migration Guide

### From Version 2026.0.x to 2026.1.0

No breaking changes. All existing endpoints remain compatible.

**What changed:**
- SSE stream now returns flat metric format instead of measurement/field split
- Content negotiation added for `/metrics/stream` (HTML vs SSE)

**Migration steps:**
1. Pull new image: `docker pull intel/metrics-manager:2026.1.0`
2. Update `docker-compose.yaml` or Helm values if pinning version
3. Restart: `docker compose up -d`
4. No data migration needed (in-memory store)

---

## Disclaimer

This container image is intended for demo and evaluation purposes and is not hardened for production deployments out of the box. To receive expanded security maintenance from Canonical on the Python/Debian base layer, you may follow the relevant Ubuntu Pro / vendor guidance and rebuild the image from the published `Dockerfile`.

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0

The Metrics Manager source code is licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).

### Third-Party Software

- **Telegraf** — Open source project developed by InfluxData and licensed under the MIT license. See <https://github.com/influxdata/telegraf/blob/master/LICENSE>
- **qmassa** — Open source Intel® GPU monitoring tool licensed under the MIT license. See <https://github.com/ulissesf/qmassa>
- **qmmd** — Prometheus exporter for Intel® GPUs, published on crates.io under the same project
- **Prometheus & OpenTelemetry** — CNCF projects. See <https://prometheus.io/> and <https://opentelemetry.io/> for license terms

You are solely responsible for determining if your use of these tools requires any additional licenses.

## Legal Information

Intel technologies' features and benefits depend on system configuration and may require enabled hardware, software, or service activation. Learn more at intel.com, or from the OEM or retailer.

No computer system can be absolutely secure. Intel does not assume any liability for lost or stolen data or systems or any damages resulting from such losses.

You may not use or facilitate the use of this document in connection with any infringement or other legal analysis concerning Intel products described herein. You agree to grant Intel a non-exclusive, royalty-free license to any patent claim thereafter drafted which includes subject matter disclosed herein.

No license (express or implied, by estoppel or otherwise) to any intellectual property rights is granted by this document.

Intel disclaims all express and implied warranties, including without limitation, the implied warranties of merchantability, fitness for a particular purpose, and non-infringement, as well as any warranty arising from course of performance, course of dealing, or usage in trade.

This document contains information on products, services and/or processes in development. All information provided here is subject to change without notice. Contact your Intel representative to obtain the latest forecast, schedule, specifications and roadmaps.

The products and services described may contain defects or errors which may cause deviations from published specifications. Current characterized errata are available on request.

Intel, the Intel logo, and Xeon are trademarks of Intel Corporation in the U.S. and/or other countries.

\*Other names and brands may be claimed as the property of others.

© 2025-2026 Intel Corporation

## Supporting Resources

- [Get Started Guide](./get-started.md)
- [API Reference](./api-reference.md)
- [Configuration Guide](./get-started/environment-variables.md)
- [How It Works](./how-it-works.md)
- [Troubleshooting](./troubleshooting.md)
