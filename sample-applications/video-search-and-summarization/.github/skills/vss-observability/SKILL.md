---
name: vss-observability
description: Use this skill for the video-search-and-summarization sample app whenever a developer asks "why is VSS processing slow", wants to trace a video through VSS, set up telemetry/OpenTelemetry for VSS, find the bottleneck in the pipeline, or view traces/metrics. It is intentionally grounded in the app's actual Docker Compose telemetry overlay, Pipeline Manager OTel wiring, and current service instrumentation; use it instead of inventing Jaeger/Prometheus/collector details.
---

# VSS Observability

Use this only for `sample-applications/video-search-and-summarization`. Start by checking the actual files if they may have changed: `docker/compose.telemetry.yaml`, `docker/compose.base.yaml`, `pipeline-manager/src/tracing.ts`, `pipeline-manager/src/telemetry/*`, `pipeline-manager/src/app.module.ts`, and `setup.sh`.

## What telemetry actually exists

There are two separate paths:

1. **Live system/dataprep metrics for the UI**: `ENABLE_VSS_COLLECTOR=true` adds `docker/compose.telemetry.yaml`, which starts `vss-collector` (`docker.io/intel/vippet-collector:2026.0.0`). It reads `pipeline-manager/telemetry/collector/telegraf.conf`, exposes a Prometheus scrape endpoint on host/container `9273`, and forwards JSON to `ws://pipeline-manager:3000/metrics/ws/collector`.
2. **OpenTelemetry traces from Pipeline Manager**: `pipeline-manager/src/main.ts` starts `otelSDK` from `src/tracing.ts`. The SDK uses service name `videoSummary`, Node auto-instrumentations, and `OTLPTraceExporter` only when `OTLP_TRACE_URL` is set. If `OTLP_TRACE_URL` is empty, spans go to `ConsoleSpanExporter` in `pipeline-manager` logs.

Do not claim the VSS Compose stack deploys Jaeger, Tempo, an OpenTelemetry Collector, or a trace UI. It does not. For a trace backend, the developer must provide an OTLP HTTP trace endpoint and set `OTLP_TRACE_URL`.

## Enable metrics overlay

From the app root:

```bash
cd sample-applications/video-search-and-summarization
ENABLE_VSS_COLLECTOR=true source setup.sh --search
# or, for dual summary + search:
ENABLE_VSS_COLLECTOR=true source setup.sh --summary --search
```

`setup.sh` defaults `ENABLE_VSS_COLLECTOR=false` and adds `-f docker/compose.telemetry.yaml` only when it is `true`. The docs say this collector is applicable to `--search` and `--summary --search` modes.

Verify:

```bash
curl http://localhost:3001/metrics/status
curl http://localhost:9273/metrics | head
```

Through nginx, Pipeline Manager routes are under `http://localhost:12345/manager/...`, so metrics status is also `http://localhost:12345/manager/metrics/status`.

## Enable Pipeline Manager OTel traces

For local debug without a backend, leave `OTLP_TRACE_URL` empty and read `pipeline-manager` logs; `src/tracing.ts` falls back to `ConsoleSpanExporter`.

To export traces, set a real OTLP HTTP traces endpoint before starting VSS:

```bash
OTLP_TRACE_URL=http://<your-otel-backend-or-collector>:4318/v1/traces source setup.sh --summary --search
```

Use the URL required by the developer's backend. VSS only passes `OTLP_TRACE_URL` into `pipeline-manager` (`docker/compose.base.yaml`) and constructs `new OTLPTraceExporter({ url: process.env.OTLP_TRACE_URL })`; it does not configure headers, auth, or a collector container.

## Follow one video through the pipeline

Because current code has no custom `stateId`/`videoId` span attributes, correlated tracing depends on combining Pipeline Manager spans, API responses, state endpoints, logs, and service metrics.

1. Capture IDs from API/UI calls:
   - `POST /manager/videos` returns `{ videoId }` (`VideoController`).
   - `POST /manager/summary` returns `{ summaryPipelineId }`, which is the `stateId` (`SummaryController`).
2. In the trace backend or console spans, filter service `videoSummary` and the time window around the upload/start request.
3. Follow Pipeline Manager HTTP client spans by destination:
   - MinIO/object store upload during `VideoService.uploadVideo`.
   - EVAM/DLStreamer chunking request: `POST http://<EVAM_HOST>:8080/pipelines/user_defined_pipelines/<pipeline>` from `EvamService.startChunkingStub`.
   - EVAM status polling: `GET http://<EVAM_HOST>:8080/pipelines/<pipelineId>` from `EvamService.getPipelineStatus`.
   - VLM captioning OpenAI-compatible calls from `VlmService.imageInference` to `VLM_CAPTIONING_API`.
   - LLM final summary OpenAI-compatible calls from `LlmService.summarizeMapReduce` / `getChatCompletions` to `LLM_SUMMARIZATION_API`.
   - Search embeddings calls from `DataPrepShimService` to `SEARCH_DATAPREP_ENDPOINT` (`/videos/minio` for full-video embeddings, `/summary` for chunk summaries).
4. Poll state while the job runs:

```bash
curl http://localhost:3001/summary/<summaryPipelineId>/raw
curl http://localhost:3001/pipeline/evam
curl http://localhost:3001/pipeline/frames
```

Correlated traces matter because the slow user-visible step is often not the endpoint that accepted the request. Pipeline Manager queues work and emits events; EVAM chunking, RabbitMQ frame delivery, VLM caption calls, LLM consolidation, and dataprep embeddings happen asynchronously. A single trace/time window plus the `stateId` keeps you from blaming UI latency when the actual wait is chunking, model inference, queue concurrency, or embeddings.

## Spot bottlenecks quickly

- **Collector disconnected or no UI metrics**: check `curl http://localhost:3001/metrics/status`, `vss-collector` logs, and `WEBSOCKET_URL=ws://pipeline-manager:3000/metrics/ws/collector` from `compose.telemetry.yaml`.
- **Host/device saturation**: inspect `http://localhost:9273/metrics`. The collector emits CPU `usage_user`, memory `used_percent`, CPU frequency, temperature, QMassa/GPU-related readings, and `dataprep_embeddings_per_second` when available.
- **Chunking slow**: look for long EVAM `POST /pipelines/user_defined_pipelines/...` or repeated `GET /pipelines/<id>` spans, and check `video-ingestion` health/logs.
- **VLM slow**: long outbound OpenAI-compatible chat completion spans from `VlmService.imageInference`; compare with `VLM_CONCURRENT`, model/device, and `vss-collector` CPU/GPU metrics.
- **Final summary slow**: long LLM chat completion spans from `LlmService.summarizeMapReduce`; check `LLM_CONCURRENT`, `MAX_CONTEXT_LENGTH`, and token limits.
- **Search embedding slow**: long calls to `vdms-dataprep` from `DataPrepShimService`, plus low `dataprep_embeddings_per_second` in collector metrics.
- **Search service traces missing**: expected today. `search-ms` does not contain app OTel wiring; grep only shows optional OTel extras in dependency lock data, not instrumentation.

For more detail, read [references/telemetry-setup.md](references/telemetry-setup.md).
