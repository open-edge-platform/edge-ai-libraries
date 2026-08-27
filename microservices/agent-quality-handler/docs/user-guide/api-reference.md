# API Reference

The Agent Quality Handler API is exposed directly on
`http://localhost:5002`.

## Agent routes

| Method | Path | Description |
|---|---|---|
| `POST` | `/agents/run` | Queue a manual bounded reasoning run |
| `GET` | `/agents/status/{run_id}` | Get run status |
| `GET` | `/agents/results/{run_id}` | Get terminal run results |
| `GET` | `/agents/runs` | List runs; optionally filter with `?id=<run_id>` |
| `GET` | `/agents/outputs/{agent}` | List persisted output history for one agent |
| `GET` | `/agents/outputs/{agent}/{run_id}` | Get one persisted agent/run output |
| `GET` | `/health` | Service liveness and retained run count |
| `GET` | `/metrics` | Prometheus-format run metrics |

### Queue a manual run

The HTTP route is a standalone fallback. Automated runs should originate from
batch-complete MQTT events.

```bash
curl -X POST http://localhost:5002/agents/run \
  -H "Content-Type: application/json" \
  -d '{"min_id": 100, "max_id": 250}'
```

All request fields are optional:

| Field | Type | Meaning |
|---|---|---|
| `min_id` | non-negative integer | Exclusive lower detection ID bound |
| `max_id` | non-negative integer | Inclusive upper detection ID bound |
| `config_path` | string or `null` | Server path overriding the agent config |
| `prompts_dir` | string or `null` | Server path overriding the prompts directory |

When both bounds are supplied, `min_id` must be less than `max_id`. The
response is HTTP `202` with status `queued`. Runs then transition through
`running` to `completed` or `error`.

`GET /agents/results/{run_id}` returns HTTP `202` while a run is queued or
running, and HTTP `404` for an unknown ID. Terminal results preserve partial
agent outputs and structured errors.

## Persisted per-agent outputs

Terminal runs are written to the named Docker volume mounted at `/app/output`.
The service maintains four files:

```text
/app/output/policy.json
/app/output/analysis.json
/app/output/evidence.json
/app/output/ticket.json
```

Each file is one JSON document with multiple records keyed by `run_id`:

```json
{
  "schema_version": "1.0",
  "agent": "analysis",
  "runs": {
    "inspection-42": {
      "run_id": "inspection-42",
      "run_status": "completed",
      "source": "mqtt",
      "min_id": 100,
      "max_id": 250,
      "completed_at": 1784563200.0,
      "completed_at_iso": "2026-07-20T12:00:00+00:00",
      "batch_metadata": {"device": "camera-west"},
      "output": {},
      "errors": [],
      "run_errors": []
    }
  }
}
```

Files are replaced atomically so readers do not observe partially written
JSON. Query them through HTTP rather than mounting the volume into downstream
applications:

```bash
curl http://localhost:5002/agents/outputs/analysis
curl http://localhost:5002/agents/outputs/analysis/inspection-42
```

Valid agent names are `policy`, `analysis`, `evidence`, and `ticket`. Unknown
agents or run IDs return HTTP `404`; an unavailable or corrupt output store
returns HTTP `503`.

Persisted records use the same `RUN_RETENTION_SECONDS` and
`MAX_RETAINED_RUNS` limits as the in-process run registry. Retention is applied
at startup and during normal API/run activity, including to files retained
from a previous container process.

## Detection Service batch event contract

Detection Service owns detection persistence and publishes one terminal event
per detection run. Agent Quality Handler subscribes to `MQTT_BATCH_TOPIC`
(`apm/batch-complete` by default).

```json
{
  "schema_version": "1.0",
  "run_id": "inspection-42",
  "status": "completed",
  "device": "camera-west",
  "video_filename": "inspection.mp4",
  "start_id": 100,
  "end_id": 250,
  "pipeline_status": "COMPLETED",
  "error": null
}
```

| Field | Requirement |
|---|---|
| `schema_version` | Optional; defaults to `1.0`; versions `1` and `1.0` are accepted |
| `run_id` | Required non-empty string, maximum 128 characters; idempotency key |
| `status` | Required; `completed` or `error` |
| `device` | Required non-empty string |
| `video_filename` | Required non-empty string |
| `start_id`, `end_id` | Required non-negative integers |
| `pipeline_status` | String or `null` |
| `error` | String or `null` |

A completed event must have `start_id < end_id`. It queues reasoning over
`id > start_id AND id <= end_id`. An error event creates an error result and
never reads storage or invokes the graph.

`run_id` is retained across Detection Service and Agent Quality Handler.
Duplicate events never rerun reasoning. Use QoS 1 or 2: valid deliveries are
acknowledged only after the corresponding run reaches a terminal state, so a
restart causes broker redelivery. Malformed events are acknowledged and
discarded as poison messages.

Configure the subscriber with `MQTT_HOST`, `MQTT_PORT`, `MQTT_BATCH_TOPIC`,
`MQTT_BATCH_CLIENT_ID`, `MQTT_QOS`, `MQTT_KEEPALIVE`,
`MQTT_MAX_PAYLOAD_BYTES`, and optional MQTT authentication settings.

## Required storage read contract

`STORAGE_SERVICE_URL` identifies the downstream storage service. Agent Quality
Handler requires:

| Method | Path | Response |
|---|---|---|
| `GET` | `/detections` | JSON array of detection records |
| `GET` | `/detections/stats` | JSON summary object |

Both routes accept optional `min_id` and `max_id` query parameters with
exclusive-lower/inclusive-upper semantics. `/detections` also retains its
`label`, `min_confidence`, and `limit` filters.

Detection Service owns all writes and database choices. Agent Quality Handler
has no database or storage-write dependency. Storage reads use configured
timeouts and bounded retries for transient failures.
