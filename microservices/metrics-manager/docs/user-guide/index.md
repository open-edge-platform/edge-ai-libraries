# Metrics Manager

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.1.0/microservices/metrics-manager">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.1.0/microservices/metrics-manager/README.md">
     Readme
  </a>
</div>
hide_directive-->

**Metrics Manager** is an open-source, container-ready service for unified collection, ingestion, and real-time relay of system and application metrics on edge and cloud nodes. It bundles Telegraf-based hardware telemetry (CPU, memory, temperature, Intel® GPU, Intel® NPU) with a FastAPI REST surface that accepts custom metrics in JSON, InfluxDB Line Protocol, and OpenTelemetry formats, and exposes them through a Prometheus-compatible endpoint as well as a Server-Sent Events (SSE) stream suitable for live dashboards.

## Key Benefits

- **Multi-format Ingestion**: Accepts metrics from any source — JSON, InfluxDB Line Protocol, OpenTelemetry (OTLP), or simple single-metric endpoints
- **Real-time Streaming**: Live SSE stream for dashboards without polling overhead; browser-friendly HTML UI included
- **Hardware Telemetry**: Automatic collection from CPU, RAM, temperature sensors, Intel® Arc GPU (qmassa), and Intel® NPU (via PMT)
- **Container-Ready**: Single Docker image with all dependencies; runs on Kubernetes via Helm chart
- **Low Latency**: In-memory metrics with configurable retention; debounced persistence to avoid bottlenecks

## Features

- **Four REST API formats** for ingestion: JSON Batch, Simple JSON, InfluxDB Line Protocol, OpenTelemetry (OTLP)
- **Prometheus-compatible** output (`/metrics` and `/metrics/latest` endpoints)
- **Server-Sent Events (SSE)** streaming (`/metrics/stream`) with automatic HTML UI in browsers
- **Custom metrics scripts** — accepts executables dropped into `/app/custom-metrics/` and runs them every 10s via Telegraf
- **Rate limiting** — token bucket per IP, configurable burst
- **Structured JSON logging** with correlation IDs for distributed tracing
- **Health checks** — basic and detailed endpoints with service statistics
- **Memory protection** — automatic eviction of oldest metrics when limit reached (default 100k metrics)
- **Flexible configuration** — 30+ environment variables for tuning a wide range of aspects
- **Docker Compose & Kubernetes** — production-ready `compose.yaml` and Helm chart included

## Use Cases

- **Edge AI Inference**: Monitor model latency, throughput, GPU/NPU utilization in real-time
- **System Monitoring**: Collect CPU, RAM, temperature from heterogeneous edge nodes (Intel Arc GPU, NPU)
- **Live Dashboards**: Stream metrics to [ViPPET](https://docs.openedgeplatform.intel.com/2026.1/edge-ai-libraries/visual-pipeline-and-platform-evaluation-tool/index.html),
  Grafana, or a custom WebUI without polling
- **Multi-source Aggregation**: Ingest metrics from Telegraf agents, OpenTelemetry collectors, and custom applications in one place
- **Telemetry Integration**: Accept metrics from any framework (OTLP) or protocol (InfluxDB Line Protocol) without code changes

## Key Metrics Collected

**System Metrics** (via Telegraf, every 1 second):

- **CPU**: per-core usage (user, system, idle), frequency, temperature
- **Memory**: used/available percentage, total, used bytes
- **Intel Arc GPU**: engine usage (compute, render, copy, video), frequency, power
- **Intel NPU**: power, frequency, temperature, utilization, bandwidth, tile configuration, memory
- **Temperature**: CPU package temperature via `coretemp`

**Custom Metrics**:

- Accept any metric format (JSON, Influx, OTLP) via REST API
- Automatic tag support (e.g., `{"source": "camera1", "model": "yolov8"}`)
- Configurable retention (default 300 seconds)

## Architecture Overview

![Metrics Manager Microservice Architecture](./_assets/metrics-mgr-microsvc-arch.drawio.svg "microservice architecture diagram")

Metrics flow through three main channels:

1. **System Metrics**: Telegraf agents collect CPU, memory, GPU, NPU data every 1 second and expose them on `:9273/metrics` in Prometheus format
2. **Custom Metrics**: Applications push metrics via REST API (`/api/v1/metrics/*`) → stored in-memory → debounced persistence to Telegraf `:8186/write` → appear in Prometheus endpoint
3. **Real-time Streaming**: SSE clients connect to `/metrics/stream` → poller queries Telegraf `:9273` every 500ms → broadcasts metrics as Server-Sent Events

All metrics are available on three endpoints:

- `GET /metrics` — Prometheus text format (custom metrics only)
- `GET /api/v1/metrics/latest` — JSON format with latest values
- `GET /metrics/stream` — SSE stream for live dashboards (system + custom)

For details, see [How It Works](./how-it-works.md).

## Supporting Resources

- [Get Started Guide](./get-started.md)
- [System Requirements](./get-started/system-requirements.md)
- [Testing Guide](./get-started/testing.md)
- [How It Works (Architecture Details)](./how-it-works.md)
- [API Reference](./api-reference.md)
- [Environment Variables](./get-started/environment-variables.md)
- [Custom Metrics Scripts](./get-started/custom-metrics.md)
- [Helm Deployment](./get-started/deploy-with-helm.md)
- [Building from Source](./get-started/build-from-source.md)
- [Troubleshooting](./troubleshooting.md)
- [Release Notes](./release-notes.md)

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0

<!--hide_directive
:::{toctree}
:hidden:

./get-started.md
./how-it-works.md
./api-reference.md
./troubleshooting.md
Release Notes <./release-notes.md>

:::
hide_directive-->
