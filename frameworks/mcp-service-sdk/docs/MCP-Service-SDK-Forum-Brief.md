# MCP Service SDK: Shared Contract Library for Agent-Ready Services

## Executive Summary

The `mcp-service-sdk` is a reusable Python library that helps any service expose its data, events, and actions to an AI agent through a consistent Model Context Protocol (MCP) contract.

Instead of every application team building its own MCP server, event log, delivery mechanism, policy checks, and telemetry, the SDK provides a common foundation. A service team writes only its domain-specific event schemas and read/action tools; the SDK supplies the standard agent-facing contract.

In simple terms:

> The SDK turns a normal service into an agent-ready service with a durable event log, safe action controls, telemetry, and MCP discovery built in.

It was initially created for Central QSR Agent services, where multiple systems such as order accuracy, kiosk, suspicious activity detection, and simulators need to be discovered and called by an agent in the same way. The design itself is domain-agnostic and can be used beyond QSR wherever services need to be exposed to an MCP-compatible agent.

## Why We Need This Library

AI agents become useful in operational environments only when they can reliably discover services, read current state, inspect historical events, and perform approved actions. Without a common service contract, every new service integration becomes custom work.

First, a clarification that usually comes up in the forum:

> FastMCP is the MCP protocol/tool layer. The SDK is the service-contract and production-behavior layer built on top of it. FastMCP lets you expose tools; the SDK makes every service expose the *same* contract with a durable log, replay, safety gate, delivery, and telemetry already wired in.

So most of the problems below are not "FastMCP cannot do it." They are "FastMCP does not standardize it, so each team builds it differently." The SDK removes that per-team variation.

Common problems without the SDK, and what the SDK actually does:

| Problem Without the SDK | Can FastMCP Do It? | What the SDK Adds |
|---|---|---|
| Each service may expose MCP tools with different names, schemas, and behavior. | Yes, FastMCP can expose tools, but each team chooses its own names, shapes, and conventions. | The SDK enforces one contract shape (`describe`/`read`/`act`/`emit`, with optional `subscribe`) so every service looks the same to the agent, even though tool names differ. The agent always onboards the same way: call `describe` first. |
| Every team may reimplement event logging, replay, retries, and history queries. | No. FastMCP has no durable log, replay, or history model. | The SDK provides a durable log, idempotent append, replay, and read-over-history out of the box. |
| Agent prompts or orchestration code may need changes whenever a service's tool names or schemas change. | With raw FastMCP the agent often hardcodes tool names/params, so a rename breaks it. | The SDK makes the agent *discover* capabilities through `describe` at runtime, so tool-name and schema changes are picked up without editing agent prompts or orchestration code. Genuine behavioral or capability changes may still require updates. |
| Runtime actions may be exposed without a consistent approval or safety policy. | FastMCP exposes tools directly; there is no built-in approval gate. | The SDK routes every action through a deterministic policy gate (automatic / needs-approval / blocked / rate-limited). |
| Debugging is harder when events are not durable, ordered, or replayable. | No. FastMCP does not persist events. | The SDK writes every event to a durable, ordered log before delivery, so events can be inspected and replayed. |
| Delivery failures may be difficult to trace without a standard delivery layer. | FastMCP does not manage fan-out or retries. | The SDK provides a delivery layer with retries and an explicit disabled mode, so failures are bounded and visible. |
| Telemetry may be inconsistent across services or added late. | FastMCP has no standard telemetry for emit/read/act. | The SDK builds telemetry spans into the emit, read, and act paths consistently for every service. |

The SDK solves this by standardizing the service contract while letting every team keep its own domain logic. It does not replace FastMCP; it uses FastMCP (or another MCP backend) underneath and adds the production patterns around it.

## What Problem It Solves

The core problem is not just "how do we expose one MCP tool?" The larger problem is how to scale from one agent integration to many services without accumulating integration debt.

The SDK solves the following problems:

| Problem | Problem Example | How the SDK Helps | SDK Example |
|---|---|---|---|
| Inconsistent service interfaces | SAD exposes `get_zone_activity`, Order Accuracy exposes `order_history`, and another service exposes different naming and response patterns. Hermes needs custom logic for each one. | Every service exposes the same `describe`, `subscribe`, `read`, and `act` pattern. | Hermes learns every service through the same contract before calling service-specific tools. |
| Fragile agent integration | Hermes is hardcoded to call `Get_activity_by_zone(zone_name)`, but the service changes it to `get_zone_activity(zone_id, include_pending)`. The agent call fails. | The agent discovers service capabilities instead of relying on hardcoded assumptions. | Hermes calls `describe` and sees the current tool name, parameters, descriptions, events, and action gate levels. |
| Real vs simulator mismatch | A simulator used in a demo returns one schema, but the real pipeline later returns a different schema, forcing agent changes. | A simulator and a production pipeline can expose the same contract. | A simulated kitchen LOITERING service and the real Scene Understanding pipeline both expose the same `LOITERING` event and read tools. |
| Lost events | A person loiters in `kitchen-prep`, but Hermes or the webhook is down when the event is produced. Without storage, the event may disappear. | Events are written to a durable log before delivery. | `emit()` writes `LOITERING` to SQLite or JSONL first, then attempts delivery. The event remains available if delivery fails. |
| Duplicate events | MQTT or an upstream pipeline retries the same event after a restart or timeout. The agent may see the same incident twice. | `ref_id` makes event append idempotent. | The same `ref_id`, such as `scene-001/person-123/kitchen-prep/loitering`, maps to one log entry even if retried. |
| Unsafe actions | An LLM requests an action with business impact, such as `issue_comp`, `shutdown_camera`, or repeated operator notifications. | Action tools are routed through a deterministic policy gate. | `notify_operator` can be `AUTOMATIC`, `issue_comp` can be `NEEDS_APPROVAL`, and `shutdown_camera` can be `BLOCKED`. |
| No replay/debug path | During a demo, the UI does not show an alert. The team cannot tell whether the event was never emitted, delivery failed, or the agent missed it. | Durable logs can be read and replayed. | Inspect the service log for `LOITERING` events and replay recent events to verify the integration path. |
| Delivery uncertainty | A webhook endpoint, EventHub sink, or agent callback is temporarily unavailable. Teams may not know what was delivered. | Delivery fan-out supports retries and explicit disabled mode. | Local tests can use disabled delivery intentionally; production can retry configured sinks without changing service code. |
| Missing observability | Agent latency is high, but teams cannot tell whether time is spent in event emit, read tool execution, or action execution. | Telemetry spans are built into emit, read, and act paths. | Spans such as `emit:LOITERING`, `read:get_zone_activity`, and `act:notify_operator` identify slow paths. |

## What The SDK Provides

The package is located at:

```text
oep/edge-ai-libraries/frameworks/mcp-service-sdk
```

Python package name:

```text
mcp-service-sdk
```

Python import namespace:

```python
from mcp_service_sdk import ServiceServer
```

Current version:

```text
0.2.0
```

Main modules:

| Module | Responsibility |
|---|---|
| `server.py` | `ServiceServer`, MCP binding, `describe`, `subscribe`, read tools, action tools. |
| `envelope.py` | Standard event envelope with event type, timestamp, service, store, payload, and `ref_id`. |
| `log.py` | Durable log abstraction with SQLite and JSONL implementations. |
| `delivery.py` | Event fan-out to disabled sink, webhook sink, or EventHub-style sink. |
| `policy.py` | Action policy gate: automatic, notify, needs approval, blocked, and rate limit. |
| `telemetry.py` | Timing spans and pluggable metrics backend. |
| `__init__.py` | Public SDK exports. |

The core library has no required runtime dependencies. MCP backends are optional extras.

## The Uniform Service Contract

Every SDK-based service exposes the same conceptual contract:

```text
emit -> durable log -> describe / subscribe / read / act
```

The agent-facing capabilities are:

| Capability | Purpose |
|---|---|
| `describe` | Tell the agent what events, read tools, and action tools this service supports. |
| `subscribe` | Register interest in future events. |
| `read` tools | Safe query tools for status, history, metrics, or service state. |
| `act` tools | Controlled action tools, always routed through the policy gate. |

This lets an agent such as Hermes connect to a service, discover what it can do, read relevant state, and take approved actions without custom integration logic for each service.

### Presenter Explanation Of The Five Verbs

Use this simple explanation if the forum asks what the contract means:

| Verb | Plain Meaning | Example In Our Use Case |
|---|---|---|
| `describe` | The service tells the agent what it supports. | SAD service says it supports `LOITERING`, zone activity reads, and operator notification actions. |
| `subscribe` | The agent asks to be notified when something happens. | Hermes subscribes to `LOITERING` instead of repeatedly asking if kitchen loitering happened. |
| `read` | The agent asks safe questions that do not change anything. | Get current person zone activity, recent alerts, or order accuracy rate. |
| `act` | The agent requests a real action, but policy decides whether it runs. | Notify operator automatically, require approval for a refund, block unsafe actions. |
| `emit` | The service records that something happened. | Scene Understanding emits a `LOITERING` event after dwell crosses the threshold. |

Kitchen example: Hermes calls `describe`, sees that `LOITERING` is supported, calls `subscribe` once, receives a notification when a person loiters in `kitchen-prep`, calls a `read` tool for context, then requests an `act` tool such as `notify_operator`. The service emits and stores the event before delivery, and the policy gate controls whether the action runs.

## How It Works

### Event Path

When a service emits an event:

```text
service.emit()
  -> create EventEnvelope
  -> append to durable log first
  -> dispatch to configured sinks
  -> record telemetry span
```

The log-first design is important. It means the service keeps a durable record before trying to notify anyone else. If delivery fails, the event is still available for replay and debugging.

### Durable Event Logging In Simple Terms

Durable event logging is the service's memory. When something important happens, the SDK saves the event before sending it anywhere else.

Kitchen example:

```text
Person loiters in kitchen-prep
  -> service creates LOITERING event
  -> SDK writes it to durable log first
  -> SDK then tries delivery to Hermes, webhook, or another sink
```

If delivery fails because the agent is offline, the event is still saved. Teams can inspect it, replay it, or use it for debugging. With a stable `ref_id`, retries do not create duplicate log records.

The durable backend can be SQLite or JSONL. For production, the log should live on persistent storage such as a mounted volume.

### Read Path

Read tools are normal Python functions registered with `@svc.read_tool(...)`.

```text
agent calls read tool
  -> SDK wrapper applies telemetry and optional timeout
  -> service function runs
  -> result returns to agent
```

Read tools are intended for safe queries such as summaries, counts, recent events, status, configuration, or analytics.

### Action Path

Action tools are normal Python functions registered with `@svc.act_tool(...)`, but they are never called directly by the MCP layer.

```text
agent calls action tool
  -> PolicyGate evaluates allow-list, gate level, and rate limits
  -> if allowed, service function runs
  -> if blocked or approval is needed, function does not run
```

This is a key governance principle: the LLM can request an action, but deterministic code decides whether that action can execute.

### Safe Action Controls In Simple Terms

Safe action controls are the permission checks around anything the agent can do. Reading information is usually safe; doing something requires control.

This is similar to Copilot asking for approval before it edits a file or runs a terminal command. The assistant can request the action, but the user or policy decides whether it is allowed.

Service examples:

| Action | Suggested Gate | Why |
|---|---|---|
| `notify_operator` | `AUTOMATIC` | Low-risk operational notification. |
| `request_remake` | `AUTOMATIC` with rate limit | Allowed, but should not spam repeated requests. |
| `issue_comp` | `NEEDS_APPROVAL` | Money/refund decision needs human approval. |
| `shutdown_camera` | `BLOCKED` | Unsafe or unsupported for the agent. |

Key message: the LLM proposes; deterministic policy decides.

## Policy Gate and Safety Model

The SDK supports these action levels:

| Gate Level | Meaning |
|---|---|
| `AUTOMATIC` | Action can run automatically if registered and within rate limits. |
| `NOTIFY` | Action can run while notifying or surfacing to the operator. |
| `NEEDS_APPROVAL` | Action requires human approval before execution. |
| `BLOCKED` | Action is exposed as unavailable and will not execute. |

Additional safeguards:

- Unregistered actions are blocked.
- Optional rate limits can be applied per action.
- Action metadata is visible through `describe`.
- The policy decision happens before the service function runs.

This gives teams a clear way to separate safe reads from operational actions such as remakes, refunds, equipment controls, escalations, or operator notifications.

## Why MCP Matters Here

MCP gives agents a standard way to discover and call tools. The SDK builds on MCP by adding the service-side patterns that production applications need:

- Durable event logging.
- Standard event envelope.
- Tool registration conventions.
- Read/action separation.
- Policy gate.
- Delivery fan-out.
- Telemetry.
- Backend flexibility for MCP implementations.

The SDK currently supports MCP binding through lazy backend selection:

1. Standalone FastMCP 2.x.
2. Official MCP SDK 2.x style server.
3. Official MCP SDK 1.x FastMCP server.

This allows the core library to stay testable without MCP installed, while services can add MCP support by installing the correct optional extra.

## Who Should Use It

Use this SDK when a service needs to be discoverable and usable by an AI agent.

Good candidates:

- Order accuracy service.
- Kiosk or drive-through service.
- Suspicious activity detection service.
- Inventory or stockout detection service.
- Kitchen food-safety monitoring service.
- Vision pipeline result service.
- Simulator that should look like a real service to the agent.
- Operational workflow service with read-only insights and gated actions.
- Any Python service that needs MCP tools plus durable events and governance.

## Can It Be Used With Any Service Anywhere?

Yes, with practical integration boundaries.

The SDK is domain-agnostic. It does not require QSR-specific concepts in the core. A service defines its own events, payload schemas, read tools, and actions. That means the same SDK pattern can be used for retail, manufacturing, healthcare, education, robotics, smart city, or other edge AI services.

Best fit:

- Python services.
- Containerized services.
- Services that can expose MCP over stdio, streamable HTTP, or SSE.
- Services that need agent discovery and operational action control.
- Services where event durability, replay, and auditability matter.

For non-Python services, there are two practical options:

- Add a small Python MCP sidecar that wraps the service API.
- Build an equivalent adapter in the service's native language using the same contract principles.

The SDK is not meant to replace a service's internal API, data plane, or high-throughput streaming path. It is the agent-facing control and insight layer.

## What A Service Team Writes

A service team only needs to define:

1. Event types and payload schemas.
2. Read tools for querying state or history.
3. Action tools for controlled operations.
4. Service-specific business logic.

Example:

```python
from mcp_service_sdk import GateLevel, ServiceServer

svc = ServiceServer(service="order_accuracy", store_id="store-001")

svc.register_event_type(
    "order_mismatch",
    schema={
        "order_id": "str",
        "station": "str",
        "accuracy_score": "float",
    },
)

@svc.read_tool("rework_rate", description="Return rework rate by daypart.")
def rework_rate(daypart: str) -> dict:
    events = svc.log.read(event_type="order_mismatch", limit=1000)
    return {"daypart": daypart, "orders_seen": len(events)}

@svc.act_tool(
    "request_remake",
    level=GateLevel.AUTOMATIC,
    description="Request remake for an inaccurate order.",
    max_calls=5,
    per_seconds=60,
)
def request_remake(order_id: str, reason: str) -> dict:
    return {"remake_requested": order_id, "reason": reason}

svc.run(transport="streamable-http", host="0.0.0.0", port=9000)
```

Everything else is supplied by the SDK.

## Service Responsibilities vs SDK Responsibilities

| Area | Service Team Owns | SDK Owns |
|---|---|---|
| Domain behavior | Business logic, service APIs, domain data | Not applicable |
| Event schema | Defines event names and payload fields | Provides standard envelope |
| Tool definitions | Defines read/action functions | Registers and exposes them through MCP |
| Event storage | Chooses backend and path | Durable log implementation |
| Agent discovery | Provides descriptions and schemas | Exposes `describe` contract |
| Actions | Implements action function | Policy gate, allow-list, rate limit |
| Observability | Uses returned telemetry if needed | Timing spans and metrics backend |
| Delivery | Chooses delivery mode | Fan-out and retries |

## Deployment Modes

The SDK supports multiple deployment styles:

| Mode | Use Case |
|---|---|
| `stdio` | Local development, CLI, direct agent process launch. |
| `streamable-http` | Containerized or networked MCP service. |
| `sse` | Environments using SSE-style MCP transport. |

Typical container mode:

```python
svc.run(transport="streamable-http", host="0.0.0.0", port=9000)
```

## Installation and Version Pinning

Local development:

```bash
pip install -e /path/to/edge-ai-libraries/frameworks/mcp-service-sdk[mcp]
```

As a Git package from another service:

```toml
dependencies = [
    "mcp-service-sdk[mcp] @ git+https://github.com/sachinkaushik/edge-ai-libraries.git@<tag-or-commit>#subdirectory=frameworks/mcp-service-sdk",
]
```

Production consumers should pin a release tag or commit SHA instead of using `main`. This keeps builds reproducible and lets different services adopt SDK versions independently.

## Example Reference Service

The SDK includes a reference service:

```text
examples/order_accuracy/service.py
```

It demonstrates:

- Event type declaration.
- Read tools such as rework rate and order history.
- Action tools such as remake request, expo notification, and comp/refund.
- Automatic actions with rate limits.
- Human-approved actions for sensitive operations.

This reference service is useful as the starting template for onboarding future services.

## Current Proof Points

The SDK already includes:

- Event envelope creation and serialization.
- SQLite durable log.
- JSONL durable log.
- Idempotent append using `ref_id`.
- Service configuration facade.
- Memory and null telemetry.
- Tool timeout support.
- Read and action tool registration.
- Policy gate with approval/block/rate-limit model.
- MCP backend auto-selection.
- Reference service implementation.
- Smoke test and unit coverage for v0.2.0 features.

It has been applied in the service architecture work for agent-facing retail/QSR services, including suspicious activity detection and order accuracy style service patterns.

## Benefits To The Larger Platform

For application teams:

- Less boilerplate.
- Faster service onboarding.
- One pattern to copy for every MCP service.
- Easier local testing because domain functions remain normal Python functions.

For agent/platform teams:

- Consistent discovery contract.
- Fewer hardcoded integrations.
- Easier simulator-to-real-service swap.
- Common action governance.
- Better replay and debugging story.

For operations and governance:

- Durable history of emitted events.
- Safer action execution.
- Rate-limited actions.
- Human approval path for sensitive operations.
- Telemetry hooks from the beginning.

## What This Is Not

The SDK is intentionally focused. It is not:

- A replacement for the service's own business logic.
- A replacement for high-throughput video, telemetry, or data streaming pipelines.
- A database abstraction for all service data.
- A full workflow engine.
- A security product by itself.
- A UI framework.

It is the standard agent-facing service contract layer.

## Recommended Adoption Pattern

1. Start with one real service and one simulator.
2. Define event types and payload schemas.
3. Add a small set of high-value read tools.
4. Add action tools only where policy is clear.
5. Use `NEEDS_APPROVAL` for sensitive operations.
6. Pin the SDK version in each consuming service.
7. Add service-level tests that call the Python functions directly and test the SDK contract.
8. Promote common patterns into examples and documentation.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Tool contracts drift across services | Use `describe`, examples, and versioned SDK releases. |
| Sensitive actions exposed too broadly | Use `act_tool`, allow-listing, gate levels, and rate limits. |
| Teams bypass durable event path | Make `svc.emit()` the standard event output path. |
| Production services depend on moving branch | Pin tags or commit SHAs. |
| Non-Python services cannot import SDK directly | Use a Python sidecar or native adapter following the same contract. |
| Agent behavior depends on poor descriptions | Keep descriptions close to code via decorators/docstrings. |

## Roadmap Recommendations

Recommended next steps before broad production rollout:

- Publish versioned release tags.
- Fix any remaining old package-name references in tests or docs.
- Add a formal service onboarding template.
- Add examples for one read-heavy service and one action-heavy service.
- Add CI for unit tests and packaging.
- Add approval callback integration for `NEEDS_APPROVAL` actions.
- Add optional OpenTelemetry exporter.
- Add richer schema generation from Python type hints.
- Add a compatibility test for supported MCP backends.

## Key Message For The Forum

The `mcp-service-sdk` gives us a repeatable way to make services agent-ready. It reduces custom integration work, standardizes how agents discover capabilities, provides durable event history, and places deterministic controls around actions.

It is small, domain-agnostic, and suitable for broader use anywhere we need an AI agent to interact with services in a reliable and governable way.

## Short Talk Track

We built `mcp-service-sdk` because exposing one service to an agent is easy, but exposing many services safely and consistently is where complexity grows. The SDK gives each service the same contract: describe what it can do, allow subscriptions, expose read tools, and expose gated action tools. Events are logged before delivery, actions go through a policy gate, and telemetry is built in. Service teams keep ownership of their domain logic, while the platform gets a common integration model. The result is faster onboarding, safer actions, easier debugging, and the ability to swap simulators and real pipelines without changing the agent.
