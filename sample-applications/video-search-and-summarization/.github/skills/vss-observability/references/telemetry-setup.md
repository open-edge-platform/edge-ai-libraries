# VSS metrics and tracing reference

## Metrics Manager

Compose uses `docker/compose.metrics-manager.yaml`, gated by
`ENABLE_METRICS_MANAGER=false` by default. It adds `metrics-manager`, exposes
its API on `${METRICS_MANAGER_HOST_PORT:-9090}` and Prometheus output on
`${METRICS_MANAGER_PROMETHEUS_HOST_PORT:-9273}`, and is enabled only for modes
that include search/DataPrep.

DataPrep receives:

| Variable | Value |
|---|---|
| `MM_DATAPREP_METRICS_MANAGER_URL` | `http://metrics-manager:9090` |
| `MM_DATAPREP_METRICS_MANAGER_TIMEOUT_SECONDS` | `2` by default |

After each embedding record, DataPrep asynchronously posts to
`/api/v1/metrics/simple` with this logical payload:

```json
{
  "name": "dataprep_embeddings_per_second",
  "value": 12.5,
  "timestamp": 1785300000.0,
  "tags": {
    "service": "multimodal-dataprep",
    "stage": "embedding"
  }
}
```

The publisher owns one async worker and a bounded latest-value queue. Failed
requests retry with capped backoff, a newer sample supersedes an older retry,
warnings are rate-limited, and shutdown cancels pending work. An empty URL
disables publishing. Metrics failures never delay or fail ingestion.

The UI reads `/metrics-manager/health` and
`/metrics-manager/metrics/stream` from nginx. The latter is an SSE endpoint.
The UI understands CPU, RAM, GPU, NPU, optional GPU detail, and
`dataprep_embeddings_per_second`; absent device metrics are not an error.

Useful checks:

```bash
curl -f http://localhost:9090/health
curl -N http://localhost:9090/metrics/stream
curl -f http://localhost:12345/metrics-manager/health
curl -N http://localhost:12345/metrics-manager/metrics/stream
curl http://localhost:9273/metrics | head
docker compose logs metrics-manager multimodal-dataprep nginx
```

For Helm, `global.metricsManager.enabled=false` is the gate. The
`metrics-manager` subchart is disabled by default and uses the stable service
name `metrics-manager`; the DataPrep URL is the same in-cluster URL shown
above.

## Pipeline Manager traces

`pipeline-manager/src/tracing.ts` configures the Node SDK with service name
`videoSummary` and Node auto-instrumentations. When `OTLP_TRACE_URL` is set it
uses the OTLP HTTP trace exporter; otherwise it logs spans with the console
exporter. VSS does not deploy a trace collector or viewer.

Useful correlation signals:

- `videoId` from `POST /manager/videos`
- `summaryPipelineId`/`stateId` from `POST /manager/summary`
- `/manager/summary/<stateId>/raw`
- `/manager/pipeline/evam`
- `/manager/pipeline/frames`

Long EVAM requests indicate ingestion/chunking pressure; long VLM and LLM
completion requests indicate inference pressure; long DataPrep requests plus
low embedding throughput indicate embedding/indexing pressure. Current spans
do not attach a custom state/video ID, and `search-ms` has no app-level OTel
setup.
