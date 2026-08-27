# Integrating the Agent Microservice into Another Application

The agent-service is detection-agnostic: it never talks to DL Streamer or any
detector directly, and never subscribes to raw detection data. It only needs
two things from the application that owns detection — a data source it can
query over HTTP, and a trigger telling it when a window of new detections is
ready to reason over. Any application that satisfies these two contracts can
reuse the agent-service unmodified.

## Architecture at a Glance

```
Your app / detection pipeline
        │
        │ (1) writes detections to a storage-service-compatible DB
        ▼
   Storage API  ◄──────────────── (3) agent-service reads detections
        ▲                              bounded to an id window (HTTP GET)
        │
        │ (2) publishes "batch-complete" MQTT event
        │     naming the id window that's ready
        ▼
   MQTT broker ───────────────► agent-service subscribes, reasons,
                                 stores the result in-memory, exposed
                                 via its own REST API
```

The agent-service owns none of the detection lifecycle. Your app owns:
- writing detections somewhere queryable (contract 1),
- telling the agent when to reason, and over what id range (contract 2).

## Contract 1 — Detection Data Source (HTTP)

The agent-service reads detections via `STORAGE_SERVICE_URL` (default
`http://apm-storage:5001`). Point this at your own storage-service instance,
or implement an adapter exposing the same shape:

| Method | Path | Required? | Purpose |
|--------|------|------------|---------|
| `GET` | `/detections?min_id=&max_id=&label=&min_confidence=&limit=` | Yes | Returns detection records the agents reason over |
| `GET` | `/detections/summary?min_id=&max_id=` | Yes | Per-class aggregate stats used by the analysis agent |
| `GET` | `/detections/max_id` | Only if using the explicit trigger (Contract 2b) to bookmark a watermark | Current max detection id + total count |

Each detection record must include at least:
```json
{
  "frame_id": 42,
  "label": "scratch",
  "confidence": 0.92,
  "x": 100, "y": 100, "width": 20, "height": 20
}
```

If your app already reuses `storage-service` as-is, this contract is
satisfied for free — just write your detections to it the same way DL
Streamer's subscriber does today (`POST /detections` or `/detections/batch`).

## Contract 2a — Event-Driven Trigger (recommended)

Publish one MQTT message per detection batch to the topic the agent
subscribes to (`MQTT_BATCH_TOPIC`, default `apm/batch-complete`, configurable
via env var on the agent-service):

```json
{
  "run_id": "your-generated-uuid",
  "status": "completed",
  "start_id": 5102723,
  "end_id": 5102726,
  "device": "optional, informational only",
  "video_filename": "optional, informational only"
}
```

- `run_id` — generate this yourself; the agent-service reuses it as-is, so
  you can correlate your detection run with the agent's reasoning run.
- `status: "completed"` — the agent reasons over `(start_id, end_id]`.
- Any other `status` (e.g. `"error"`) — the agent records the run as failed
  and **skips reasoning entirely**. Never publish `"completed"` unless the
  detection window is actually valid — the agent has no way to independently
  verify this.
- `start_id` / `end_id` — the detection id range for this batch. The agent
  fetches exactly this window from the storage API before reasoning.

This is the preferred integration path: it requires no direct network call
into the agent-service and keeps the two systems fully decoupled.

## Contract 2b — Explicit Trigger (fallback)

If you'd rather call the agent directly (e.g. for synchronous/manual testing
without MQTT), use the REST API instead:

```bash
curl -X POST http://<agent-service-host>:5002/agents/run \
  -H "Content-Type: application/json" \
  -d '{"min_id": 5102723, "max_id": 5102726}'
```

Response: `202 { "run_id": "...", "status": "running" }` (a new `run_id` is
generated for you). Returns `409` if a run is already in progress — only one
reasoning run executes at a time.

## Checking Results

Regardless of which trigger you used, poll for the result via the agent's own
REST API:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/agents/status/{run_id}` | `{"run_id", "status", "phase"}` — `status` is `running`/`completed`/`error` |
| `GET` | `/agents/results/{run_id}` | Full pipeline output (policy, analysis, evidence, ticketing) once completed |
| `GET` | `/agents/runs` | List all known runs |
| `GET` | `/health` | Liveness/readiness check |

Results are held **in-memory** for the life of the agent-service process —
persist them yourself (e.g. write `GET /agents/results/{run_id}` output to
your own datastore) if you need durable history across restarts.

## Configuration Reference

All integration points are environment-variable driven — no code changes are
required to point the agent-service at a different storage backend, MQTT
broker/topic, or use-case config:

| Env var | Default | Purpose |
|---------|---------|---------|
| `STORAGE_SERVICE_URL` | `http://apm-storage:5001` | Contract 1 base URL |
| `MQTT_HOST` / `MQTT_PORT` | `mqtt-broker` / `1883` | Broker for Contract 2a |
| `MQTT_BATCH_TOPIC` | `apm/batch-complete` | Topic for Contract 2a |
| `MQTT_DISABLED` | `false` | Set `true` to disable the event subscriber entirely and rely only on Contract 2b |
| `AGENTS_CONFIG_PATH` | — | Path to `agents.yaml` (agent policy/config) |
| `USE_CASE_PROMPTS_DIR` | — | Path to prompt templates for the LLM-backed agents |
| `LLM_BASE_URL` / `LLM_MODE` | — | LLM backend (OVMS) or `fallback` for rule-based reasoning without an LLM |
| `APM_API_KEY` | — | Sent as `X-API-Key` header on storage-service calls, if your storage API enforces it |

## Minimal Integration Checklist

1. Stand up (or reuse) a storage API satisfying Contract 1.
2. Point the agent-service's `STORAGE_SERVICE_URL` at it.
3. After each detection batch, publish a `batch-complete` MQTT event (Contract
   2a) — or call `POST /agents/run` directly (Contract 2b).
4. Poll `GET /agents/status/{run_id}` → `GET /agents/results/{run_id}` for
   the outcome.
5. No changes to agent-service source code are required for any of the above.
