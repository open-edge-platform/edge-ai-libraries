---
name: vss-observability
description: Use this skill for VSS live metrics, OpenTelemetry traces, pipeline bottlenecks, and metrics-panel troubleshooting. It is grounded in the Metrics Manager Compose/Helm integration and Pipeline Manager OTel wiring.
---

# VSS Observability

Use this only for `sample-applications/video-search-and-summarization`. Check
`docker/compose.metrics-manager.yaml`, `config/nginx/nginx.conf`,
`ui/react/src/components/Search/TelemetryAccordion.tsx`,
`pipeline-manager/src/tracing.ts`, and `setup.sh` before giving operational
advice.

## Environment setup

Run the bundled bootstrap and work from the resolved app root:

```bash
SKILL_DIR=".github/skills/vss-observability"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

## What observability exists

VSS has two independent paths:

1. Live system and dataprep metrics use Metrics Manager. Set
   `ENABLE_METRICS_MANAGER=true` in a search-enabled Compose deployment.
   `docker/compose.metrics-manager.yaml` starts
   `docker.io/intel/metrics-manager:2026.2.0-rc2`. DataPrep sends
   `dataprep_embeddings_per_second` to its simple-metrics REST API, and the UI
   consumes its SSE stream through nginx.
2. Pipeline Manager traces use the Node OpenTelemetry SDK. `OTLP_TRACE_URL`
   selects an external OTLP HTTP endpoint; when it is empty, spans use the
   console exporter in Pipeline Manager logs. The service name is
   `videoSummary`.

VSS does not bundle Jaeger, Tempo, an OpenTelemetry Collector, or a trace UI.

## Enable and verify live metrics

```bash
ENABLE_METRICS_MANAGER=true source setup.sh --search
# or
ENABLE_METRICS_MANAGER=true source setup.sh --summary --search

curl -f http://localhost:12345/metrics-manager/health
curl -N http://localhost:12345/metrics-manager/metrics/stream
curl http://localhost:9273/metrics | head
```

The nginx routes are deliberately limited to `/metrics-manager/health` and
`/metrics-manager/metrics/stream`. The browser uses `EventSource`, reconnects
automatically, and marks data stale when events stop. Metrics Manager provides
CPU, RAM, GPU, and NPU values when the corresponding host devices exist;
DataPrep publishes embedding throughput asynchronously. Missing accelerator
metrics are valid on hosts without those devices.

## Enable traces

```bash
OTLP_TRACE_URL=http://<trace-backend>:4318/v1/traces \
  source setup.sh --summary --search
```

No credentials or headers are configured by VSS, so use an endpoint reachable
without them or extend the trace exporter explicitly.

## Follow a video and find bottlenecks

- Save `videoId` from `POST /manager/videos` and `summaryPipelineId` (the
  `stateId`) from `POST /manager/summary`.
- Filter the trace backend for service `videoSummary` and the matching time
  window. Current auto-instrumented spans do not add those IDs as custom span
  attributes.
- Inspect EVAM start/status requests for chunking, outbound VLM completion
  requests for captioning, outbound LLM completion requests for final
  summarization, and DataPrep calls for embedding/indexing.
- Cross-check `/manager/summary/<stateId>/raw`,
  `/manager/pipeline/evam`, and `/manager/pipeline/frames`.
- Compare slow DataPrep calls with `dataprep_embeddings_per_second` in the SSE
  stream. Compare model latency with CPU/RAM/GPU/NPU saturation.

Metrics delivery failures do not imply trace failures, and missing metrics do
not stop ingestion. `search-ms` does not currently have application-level OTel
trace wiring.

For API payloads, environment variables, and troubleshooting detail, read
[references/telemetry-setup.md](references/telemetry-setup.md).
