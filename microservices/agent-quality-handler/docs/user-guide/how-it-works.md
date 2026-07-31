# How It Works

The Agent Quality Handler is a standalone orchestration service. Detection production and persistence remain external.

## Data Flow

```text
Detection Service ---- writes ----> External storage API
       |
       | MQTT batch-complete event
       v
MQTT broker -----> Agent service FIFO queue
                         |
                         | bounded GET /detections
                         | bounded GET /detections/stats
                         v
            Policy -> Analysis -> Evidence -> Ticketing
                         |
                         v
               In-memory run results
                         |
                         v
             Per-agent JSON output volume
```

The Compose file starts `aqh-agent` and a private, unexposed `mqtt-broker`. A
secured external broker can replace the bundled connection through the
`MQTT_*` settings.

## Startup and Configuration

At startup, the service validates runtime values and required assets. Configuration errors terminate startup. Defaults live in `defaults`; custom config and prompt directories are mounted with `USE_CASE_CONFIGS_DIR` and `USE_CASE_PROMPTS_DIR`.

Fallback mode uses configured rules and starts with:

```bash
docker compose -f docker/compose.yaml up --build -d
```

LLM mode sends agent prompts to OVMS and requires both:

```bash
LLM_MODE=llm docker compose -f docker/compose.yaml --profile llm up --build -d
```

The profile adds `aqh-ovms` and `model-download`.

## Run Lifecycle

1. Detection Service publishes a terminal batch event after persistence.
2. A completed event enters the FIFO queue as `queued`; an error event becomes
   a terminal error without reasoning.
3. One worker changes the next run to `running` and reads only
   `(start_id, end_id]` from `STORAGE_SERVICE_URL`.
4. The four agents produce policy, analysis, evidence, and ticket outputs.
5. The run becomes `completed` or `error`, then the MQTT delivery is
   acknowledged.

`POST /agents/run` is the manual fallback. It creates its own run ID and uses
optional `min_id` and `max_id` bounds.

Run state is held in memory and is lost when the agent container restarts.
Terminal policy, analysis, evidence, and ticket outputs are additionally
written to atomic JSON files in the `aqh_agent_output` named volume and remain
queryable after a container restart. Persisted entries use the same retention
limits as the run registry.

Graph failures are explicit: the run status becomes `error`, while successful partial outputs remain in the result with a structured `errors` list. Unexpected pipeline exceptions use the same error status and identify the failure as the `pipeline` agent.

## External Integrations

- **Storage:** required; defaults to `http://host.docker.internal:5001`.
  Detection Service owns writes and database choice. Agent Quality Handler
  performs bounded reads only.
- **MQTT:** enabled by default; the bundled broker is private. Authentication are supported for an external broker.
- **LLM:** optional; fallback mode is the default.

The FIFO queue and run registry are process-local. MQTT acknowledgement waits
for terminal state so interrupted event-driven work can be redelivered.
Manual queued work is not durable across restarts.

`GET /health` reports Agent Quality Handler liveness and in-memory run count.
It does not probe or guarantee availability of the downstream storage API.
