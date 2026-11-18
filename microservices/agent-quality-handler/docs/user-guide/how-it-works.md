<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

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
   Built-in specialists + any registry-defined custom agents
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
4. The configured agent registry runs in dependency-safe order. By default
   that is the built-in Policy, Analysis, Evidence, and Ticketing set.
   Custom agents can be inserted into the flow when `agent_registry` is
   configured.
5. The run becomes `completed` or `error`, then the MQTT delivery is
   acknowledged.

`POST /agents/run` is the manual fallback. It creates its own run ID and uses
optional `min_id` and `max_id` bounds.

Run state is held in memory and is lost when the agent container restarts.
Terminal built-in outputs (`policy`, `analysis`, `evidence`, `ticket`) and
any registered custom-agent outputs are additionally written to atomic JSON
files in the `aqh_agent_output` named volume and remain queryable after a
container restart. Persisted entries use the same retention limits as the run
registry.

Graph failures are explicit: the run status becomes `error`, while successful partial outputs remain in the result with a structured `errors` list. Unexpected pipeline exceptions use the same error status and identify the failure as the `pipeline` agent.

## Dynamic Agent Routing (LLM Mode)

In LLM mode, which agents run — and in what order — is not always the fixed
built-in Policy → Analysis → Evidence → Ticketing chain:

- The severity router can ask the LLM to classify severity and return its
  own `route`: a subset and ordering of the agents currently registered for
  the use case.
- The deep-agent runner asks the LLM for a further execution plan, which can
  reorder or narrow that route again.

Both stages normalize their result before executing it. The registry's
`depends_on` graph is the source of truth:

- unknown agent names are dropped,
- duplicates are removed while preserving first occurrence,
- any agent is moved after the dependencies it declared in the registry, and
- independent agents keep the LLM's requested relative ordering.

For the built-in registry this preserves the long-standing rule that
`ticketing` always runs after `policy` and `analysis`. For custom registries,
the same topological normalization applies transitively to every declared
dependency chain. Whenever normalization changes the order, this is logged so
the effective execution order stays observable.

Fallback (rule-based) mode is unaffected: its routes are fixed lookups keyed
by severity, with no LLM involved to reorder.

## Config-Driven Agent Registry

AQH now loads its specialist-agent topology from configuration. The built-in
registry is still the default:

- `policy`
- `analysis`
- `evidence`
- `ticketing` (depends on `policy` and `analysis`)

If `agent_registry` is omitted — or present as an empty list — AQH uses those
four built-ins automatically, so older deployments keep working unchanged.
If `agent_registry` is provided, it becomes the full registry for that use
case. In practice, start from the built-in entries and insert your custom
specialists where needed.

Each registry entry declares:

| Field | Required | Meaning |
|-------|----------|---------|
| `name` | yes | Unique agent identifier used in routes, `extra_agents`, and per-agent output history |
| `module` | yes | Dotted import path to a module exposing a `run(context)` callable |
| `depends_on` | no (default: none) | Other registered agent names whose output this agent needs; enforced as an execution-order constraint |
| `prompt_section` | no (default: uppercased `name`) | Section name this agent reads from the use-case prompt file |

The registry is validated at load time: unknown agent names, duplicate
names, self-dependencies, and dependency cycles are all rejected before any
run starts.

### Uniform agent contract: `AgentContext`

Every built-in and custom specialist now runs through the same contract:

```python
run(context: AgentContext) -> dict
```

`AgentContext` contains:

- `use_case_id`
- `config`
- `prompts_dir`
- `min_id`
- `max_id`
- `upstream_results`

`upstream_results` is keyed by dependency name, so a custom agent can read
the outputs it declared in `depends_on` via `context.upstream("<agent>")`.
For example, the built-in `ticketing` agent reads upstream `policy` and
`analysis`, and a custom `sensor_correlation` agent can read upstream
`policy` without AQH needing any agent-specific orchestration code.

### End-to-end dependency handling

The registry drives the entire pipeline, not just validation:

1. **Registry load** — startup reads `agent_registry`, validates it, and
   imports each agent module's `run(context)` callable.
2. **Route normalization** — `route_utils.normalize_route()` uses the
   registry's dependency graph to deduplicate and topologically reorder LLM
   routes.
3. **Execution graph** — `meta_agent.py` builds the orchestration graph from
   the registry and executes agents in dependency-safe order. If a dependency
   fails, downstream dependents are marked as skipped with structured errors.
4. **Deep-agent tools** — in LLM mode, `deep_agent_runner.py` generates one
   tool per registered agent. Custom agents receive one
   `<dependency>_result_json` parameter per declared dependency; dependency-
   free custom agents receive a `reason` parameter. The four built-in tools
   keep their legacy names, parameters, and docstrings for compatibility.
5. **Result/API surfacing** — the built-ins still return top-level `policy`,
   `analysis`, `evidence`, and `ticket` keys. Any additional registered agent
   is surfaced additively under `extra_agents` and persisted in its own output
   history file, accessible through `GET /agents/outputs/{agent}`.

One backward-compatibility quirk is preserved deliberately: the built-in
registry entry is named `ticketing`, but its persisted output/API key remains
`ticket`, so existing `ticket.json` readers continue to work.

### Worked example: fused vision + sensor correlation

The following registry matches the integration-tested example used for fused
vision + sensor/timeseries defect reasoning. It uses the generic agent for
`sensor_correlation`, so this is a copy/paste-ready, zero-new-Python example:

```yaml
agent_registry:
  - name: policy
    module: src.agents.policy_agent
    depends_on: []
    prompt_section: POLICY
  - name: sensor_correlation
    module: src.agents.generic_prompt_agent
    depends_on: [policy]
    prompt_section: SENSOR_CORRELATION
  - name: analysis
    module: src.agents.analysis_agent
    depends_on: []
    prompt_section: ANALYSIS
  - name: evidence
    module: src.agents.evidence_agent
    depends_on: []
    prompt_section: EVIDENCE
  - name: ticketing
    module: src.agents.ticketing_agent
    depends_on: [policy, analysis]
    prompt_section: TICKETING
```

With an LLM route like:

```json
["policy", "sensor_correlation", "analysis", "evidence", "ticketing"]
```

AQH will:

- run `policy` first,
- pass that output into `sensor_correlation` as
  `context.upstream("policy")`,
- continue with `analysis` and `evidence`,
- run `ticketing` only after both `policy` and `analysis` are available,
- return the built-in outputs at the top level, and
- return the custom agent under:

```json
{
  "extra_agents": {
    "sensor_correlation": {
      "summary": "vision and sensor anomalies correlated"
    }
  }
}
```

That same custom output is also queryable through
`GET /agents/outputs/sensor_correlation` and stored in
`/app/output/sensor_correlation.json`.

See the commented example block in `defaults/config/agents.yaml` for the same
registry shape.

## External Integrations

- **Storage:** required; defaults to `http://host.docker.internal:5001`.
  Detection Service owns writes and database choice. Agent Quality Handler
  performs bounded reads only.
- **MQTT:** enabled by default; the bundled broker is private. Authentication
  is supported for an external broker.
- **LLM:** optional; fallback mode is the default.

The FIFO queue and run registry are process-local. MQTT acknowledgement waits
for terminal state so interrupted event-driven work can be redelivered.
Manual queued work is not durable across restarts.

`GET /health` reports Agent Quality Handler liveness and in-memory run count.
It does not probe or guarantee availability of the downstream storage API.
