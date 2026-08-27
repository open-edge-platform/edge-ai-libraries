# Troubleshooting

## Agent Fails During Startup

Inspect the validated configuration:

```bash
docker compose -f docker/compose.yaml logs aqh-agent
```

Startup intentionally fails for invalid modes, URLs, ports, MQTT credentials, missing `agents.yaml` or fallback policy, and missing LLM prompt files. Correct the reported variable or mounted asset; do not expect the service to continue with an incomplete configuration.

## Storage Requests Fail

Storage is required and external:

```bash
curl "$STORAGE_SERVICE_URL/detections"
curl "$STORAGE_SERVICE_URL/detections/stats"
```

The default is `http://host.docker.internal:5001`. Ensure the host service
listens on an address reachable from Docker and implements both bounded read
routes. Detection Service, not Agent Quality Handler, owns writes.

## Batch Events Do Not Arrive

The bundled broker is private and has no host port. Check its health and agent connection:

```bash
docker compose -f docker/compose.yaml ps
docker compose -f docker/compose.yaml logs mqtt-broker aqh-agent
```

For an external broker, verify `MQTT_HOST`, `MQTT_PORT`,
`MQTT_BATCH_TOPIC`, `MQTT_BATCH_CLIENT_ID`, credentials. Set `MQTT_DISABLED=true` only for
manual HTTP operation.

Valid events remain unacknowledged until their run is terminal. Repeated
delivery of the same `run_id` is expected and does not rerun reasoning.

## LLM Services Are Missing

Both settings are required:

```bash
export LLM_MODE=llm
docker compose -f docker/compose.yaml --profile llm up --build -d
```

Without `--profile llm`, `aqh-ovms` and `model-download` do not start. For rule-based operation, unset `LLM_MODE` or set it to `fallback` and start without the profile.

## Result Has Status `error`

Inspect both status and result:

```bash
curl "http://localhost:5002/agents/status/$RUN_ID"
curl "http://localhost:5002/agents/results/$RUN_ID"
```

A graph failure sets status to `error` and returns structured entries in
`errors`. Outputs from successful graph stages may still be present and are
valid partial results. A Detection Service error event also creates an error
result, but does not invoke the graph.

## API Is Unreachable

There is no UI or Nginx endpoint. Use the direct service port:

```bash
curl http://localhost:5002/health
docker compose -f docker/compose.yaml logs aqh-agent
```

Run history is in memory and resets when the agent restarts.

## Persisted Agent Output Is Missing

Check the output mount and service logs:

```bash
docker compose -f docker/compose.yaml exec aqh-agent ls -l /app/output
docker compose -f docker/compose.yaml logs aqh-agent
curl http://localhost:5002/agents/outputs/analysis
```

The service must be able to create and atomically replace `policy.json`,
`analysis.json`, `evidence.json`, and `ticket.json`. Entries older than
`RUN_RETENTION_SECONDS` or beyond `MAX_RETAINED_RUNS` are removed.
