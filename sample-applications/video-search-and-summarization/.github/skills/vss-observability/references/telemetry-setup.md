# VSS telemetry setup reference

This reference is grounded in the current Video Search & Summarization sample app telemetry files and code.

## Stack components and ports

### Metrics/UI telemetry collector

`docker/compose.telemetry.yaml` defines one optional service:

| Component | Actual value | Purpose |
| --- | --- | --- |
| service/container | `vss-collector` | Optional telemetry collector for VSS UI metrics. |
| image | `docker.io/intel/vippet-collector:2026.0.0` | Collector image used by Compose. |
| host/container port | `9273:9273` | Prometheus-compatible debug scrape endpoint from Telegraf config. |
| config mount | `../pipeline-manager/telemetry/collector/telegraf.conf:/etc/telegraf/telegraf.conf:ro` | Collector input/output config. |
| shared signal volume | `collector_signals:/app/.collector-signals` | Carries dataprep throughput signal file. |
| websocket env | `WEBSOCKET_URL=ws://pipeline-manager:3000/metrics/ws/collector` | Collector-to-Pipeline-Manager relay target. |
| dependency | `pipeline-manager` service started | Collector connects after Pipeline Manager starts. |

The collector is privileged, uses host PID, and mounts `/sys`, `/dev`, `/run`, and `/proc` because it reads system/device metrics.

### Pipeline Manager metrics relay

`pipeline-manager/src/telemetry/telemetry.service.ts` creates two WebSocket paths on the existing Pipeline Manager HTTP server:

- `/metrics/ws/collector`: accepts a single collector connection.
- `/metrics/ws/clients`: broadcasts wrapped JSON metrics to UI clients.

`pipeline-manager/src/telemetry/telemetry.controller.ts` exposes:

- `GET /metrics/status`: returns `collectorConnected`, `clientsConnected`, and a message such as `Collector connected` or `Collector unavailable; telemetry disabled`.

With Compose defaults, Pipeline Manager is published by `docker/compose.base.yaml` as `${PM_HOST_PORT}:3000`, and `setup.sh` sets `PM_HOST_PORT=3001`. Through nginx, manager routes are under `${APP_HOST_PORT}` (`12345` default) with `/manager` prefix.

Useful checks:

```bash
curl http://localhost:3001/metrics/status
curl http://localhost:12345/manager/metrics/status
curl http://localhost:9273/metrics | head
```

### OTel traces

`pipeline-manager/src/tracing.ts` initializes `NodeSDK` with:

- `serviceName: 'videoSummary'`
- `instrumentations: [getNodeAutoInstrumentations()]`
- `traceExporter: new OTLPTraceExporter({ url: process.env.OTLP_TRACE_URL })` when `OTLP_TRACE_URL` is set
- otherwise `new ConsoleSpanExporter()`

`pipeline-manager/src/main.ts` imports `otelSDK` and calls `await otelSDK.start()` before creating the Nest app. On `SIGTERM`, `tracing.ts` shuts the SDK down.

Important limitation: the VSS Docker Compose telemetry overlay does not deploy an OpenTelemetry Collector or trace backend. Trace destination is whatever the developer provides in `OTLP_TRACE_URL`; if unset, traces are printed in Pipeline Manager logs.

## Environment variables

| Variable | Where wired | What it configures |
| --- | --- | --- |
| `ENABLE_VSS_COLLECTOR` | `setup.sh` lines around the telemetry toggle | Defaults to `false`; when `true`, setup adds `docker/compose.telemetry.yaml`. |
| `OTLP_TRACE_URL` | `docker/compose.base.yaml` -> `pipeline-manager/src/tracing.ts` | OTLP HTTP trace export URL. Empty means console span exporter. |
| `DATAPREP_TELEMETRY_URL` | `docker/compose.base.yaml` -> `DataprepTelemetryService` | Endpoint polled for dataprep throughput; default `http://multimodal-dataprep:8000/v1/dataprep/telemetry?limit=1`. |
| `DATAPREP_TELEMETRY_INTERVAL_MS` | `DataprepTelemetryService` | Poll interval, default `5000`. |
| `DATAPREP_TELEMETRY_TIMEOUT_MS` | `DataprepTelemetryService` | Poll timeout, default `30000`. |
| `TELEMETRY_SIGNAL_DIR` | `docker/compose.base.yaml` -> `DataprepTelemetryService` | Directory for `dataprep_embeddings_per_second.txt`; default `/app/.collector-signals`. |
| `WEBSOCKET_URL` | `docker/compose.telemetry.yaml` | Exported into `vss-collector`; actual Telegraf config also uses `ws://pipeline-manager:3000/metrics/ws/collector`. |

Related pipeline bottleneck variables:

- `VLM_CONCURRENT`, `LLM_CONCURRENT`: queue concurrency read by Pipeline Manager for VLM/LLM work.
- `VLM_CAPTIONING_API`, `LLM_SUMMARIZATION_API`: OpenAI-compatible backends for captioning and final summary.
- `SEARCH_DATAPREP_ENDPOINT`, `SEARCH_DATAPREP_TIMEOUT_MS`: dataprep endpoint and timeout for search embeddings.

## Telegraf metrics config

`pipeline-manager/telemetry/collector/telegraf.conf` collects:

- CPU total `usage_user` every second.
- Memory `used_percent`.
- CPU frequency via `/app/read_cpu_freq.sh`.
- Long-running `python3 /app/qmassa_reader.py` metrics.
- Temperature metrics filtered to `coretemp_package_id_*` sensors.
- `dataprep_embeddings_per_second` from `/app/.collector-signals/dataprep_embeddings_per_second.txt`.

Outputs:

- `[[outputs.prometheus_client]]` on `:9273`, path `/metrics`.
- `[[outputs.websocket]]` to `ws://pipeline-manager:3000/metrics/ws/collector`, JSON format.

`DataprepTelemetryService` writes the dataprep signal file by polling `DATAPREP_TELEMETRY_URL` and extracting either `items[0].stage_throughput.embeddings_throughput` or `items[0].throughput.embeddings_per_second`.

## Pipeline Manager instrumentation wiring

Dependencies in `pipeline-manager/package.json` include:

- `@opentelemetry/auto-instrumentations-node`
- `@opentelemetry/exporter-trace-otlp-http`
- `@opentelemetry/sdk-node`
- `@opentelemetry/sdk-trace-base`
- `nestjs-otel`

`pipeline-manager/src/app.module.ts` imports `OpenTelemetryModule.forRoot({ metrics: { hostMetrics: true } })` and `TelemetryModule`. The app's actual external metrics UI path, however, is the `vss-collector` WebSocket/Prometheus route described above; do not confuse it with a deployed OTel metrics exporter.

There are no custom `startSpan`, `@Span`, or manual video-specific span attributes in current Pipeline Manager code. Traces come from auto-instrumented Nest/HTTP/axios/fetch/OpenAI-compatible client activity where supported.

`search-ms` currently has no app-level OTel wiring. Grep for `OTEL_`, `OTLP`, `opentelemetry`, `trace`, and `span` finds no runtime setup beyond optional dependency extras in `poetry.lock` and ordinary Python `traceback` usage.

## Key spans and signals to look for

Filter traces by service name `videoSummary`, then inspect the time window around the video upload or summary start.

Expected useful operations/destinations:

1. **Upload / state creation**
   - Incoming `POST /videos` returns `videoId`.
   - Incoming `POST /summary` returns `summaryPipelineId` (`stateId`).
   - Database spans may show state/video persistence through TypeORM/Postgres.
2. **Object storage**
   - `VideoService.uploadVideo` uploads to MinIO through `DatastoreService`.
3. **Chunking / ingestion**
   - `EvamService.startChunkingStub` sends `POST http://<EVAM_HOST>:8080/pipelines/user_defined_pipelines/<pipeline>`.
   - `EvamService.getPipelineStatus` polls `GET http://<EVAM_HOST>:8080/pipelines/<pipelineId>` until complete.
   - State endpoints: `/pipeline/evam`, `/summary/<stateId>/raw`.
4. **Frame grouping and VLM captioning**
   - `ChunkingService.prepareFrames` builds frame windows from `multiFrame`, `frameOverlap`, and `samplingFrame`.
   - `ChunkingService.checkProcessing` queues VLM calls while `hasVlmSlots()` and `VlmService.serviceReady` are true.
   - `VlmService.imageInference` calls OpenAI-compatible chat completions at `VLM_CAPTIONING_API`.
5. **Chunk search embeddings**
   - `ChunkingService.createChunkSearchEmbeddings` sends summary chunks to dataprep when search is enabled.
   - `DataPrepShimService.createEmbeddingsFromSummary` posts to `<SEARCH_DATAPREP_ENDPOINT>/summary`.
6. **Final consolidation**
   - `SummaryQueueService.startVideoSummary` waits for frame summaries, then calls `LlmService.summarizeMapReduce`.
   - `LlmService.getChatCompletions` calls `LLM_SUMMARIZATION_API` for map/reduce or final streaming response.

State and queue inspection:

```bash
curl http://localhost:3001/summary/<stateId>/raw
curl http://localhost:3001/states/raw/<stateId>
curl http://localhost:3001/pipeline/frames
curl http://localhost:3001/pipeline/evam
```

## Bottleneck-hunting walkthrough

1. **Confirm telemetry is the expected kind**
   - Need live CPU/RAM/GPU/dataprep metrics in UI: use `ENABLE_VSS_COLLECTOR=true` and verify `vss-collector` plus `/metrics/status`.
   - Need distributed traces: set `OTLP_TRACE_URL` to a real backend's `/v1/traces` endpoint or use console spans in logs. There is no in-repo trace backend.

2. **Capture IDs and a time window**
   - Save `videoId` from `POST /videos`.
   - Save `summaryPipelineId`/`stateId` from `POST /summary`.
   - Note wall-clock start/end; current spans do not carry `stateId` attributes.

3. **Read the waterfall**
   - Long incoming `POST /videos`: upload/object-store/database path.
   - Long or repeated EVAM spans: ingestion/chunking/device/RabbitMQ path.
   - Long VLM completion spans: captioning model/device/concurrency bottleneck.
   - Long LLM completion spans: final consolidation/context/token bottleneck.
   - Long dataprep spans or low `dataprep_embeddings_per_second`: embedding/indexing bottleneck.

4. **Cross-check with state**
   - `status.videoChunking` / `status.chunking` stuck `IN_PROGRESS`: EVAM/audio/chunk delivery.
   - Many `frameSummaries` `IN_PROGRESS`: VLM or queue concurrency.
   - `status.summarizing` `IN_PROGRESS`: LLM consolidation.
   - `embeddingsCreated` false on frame summaries in search/unified mode: dataprep embeddings.

5. **Cross-check with metrics**
   - High CPU/memory/temperature or GPU readings during long VLM/LLM spans suggests model/device saturation.
   - Low or missing `dataprep_embeddings_per_second` while dataprep spans run suggests dataprep/embedding service trouble.
   - Collector disconnected means UI metrics are unavailable, not necessarily that OpenTelemetry traces are broken.

6. **Report accurately**
   - Say which signal proved the bottleneck: trace duration, state field, collector metric, or container log.
   - State current instrumentation limits when relevant: no search-ms traces and no custom per-video span attributes unless the app is changed.
