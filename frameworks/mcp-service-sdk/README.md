# mcp-service-sdk

Shared contract library for **Central QSR Agent** services. Every service — real
pipeline or simulator — presents the *same* contract to the agent, so the agent
can't tell them apart and we swap real pipelines in later with zero agent changes.

> This library **is the implementation of the uniform Service Contract** from the
> design (walkthrough §3): `emit → durable log → describe/subscribe/read/act`.
> It is domain-agnostic. Services import it and add only their own tools.

## What's in the box

| Module | Responsibility |
|---|---|
| `envelope.py` | The single event shape every service emits (type, ts, service/store id, payload, ref_id). |
| `log.py` | Per-service durable log (SQLite; Postgres adapter fits the same `DurableLog` protocol). Ordered, restart-safe, **idempotent on `ref_id`**, replayable. |
| `delivery.py` | Fan-out to enabled sinks: **EventHub** (default), **Webhook**, **Disabled** (clean benchmarks). Bounded retries; nothing dropped silently. |
| `policy.py` | Deterministic **Policy Gate** — automatic / notify / needs-approval / blocked, plus per-action rate limits and an allow-list. Not the LLM. |
| `telemetry.py` | Timing spans (the measurement spine) from day one. |
| `server.py` | `ServiceServer` — MCP scaffolding that exposes `describe/subscribe/read/act` and wires log + delivery + policy + telemetry together. |

The core is **stdlib-only**. The MCP server layer needs the `mcp` SDK and is
imported lazily, so everything except `run()`/`to_mcp()` works without it.

## Install

```bash
pip install -e .              # core only (stdlib)
pip install -e .[mcp]         # + official MCP SDK backend
pip install -e .[fastmcp]     # + standalone FastMCP 2.x backend (gofastmcp.com)
```

`to_mcp()` auto-picks whichever backend is installed. Both speak the same MCP
protocol on the wire.

## Use from another service

For a service that lives in a different repository, consume this library as a
Git package from `edge-ai-libraries` rather than copying the source tree.

Add this to the service's `pyproject.toml`:

```toml
dependencies = [
    "mcp-service-sdk[mcp] @ git+https://github.com/sachinkaushik/edge-ai-libraries.git@<tag-or-commit>#subdirectory=frameworks/mcp-service-sdk",
]
```

Use a release tag or commit SHA in place of `<tag-or-commit>` so builds stay
reproducible. Avoid pointing production consumers at `main`.

For local verification during SDK development, you can still install from a
checkout:

```bash
pip install -e /absolute/path/to/edge-ai-libraries/frameworks/mcp-service-sdk[mcp]
```

Service code then imports the SDK normally:

```python
from mcp_service_sdk import ServiceServer
```

## Writing a service (the whole job)

A service writes **only** its event schema + read/act tools:

```python
from mcp_service_sdk import GateLevel, ServiceServer

svc = ServiceServer(service="order_accuracy", store_id="store-001")

svc.register_event_type("order_mismatch", schema={"order_id": "str", "station": "str"})

@svc.read_tool("rework_rate", description="Rework rate for a daypart.")
def rework_rate(daypart: str, station: str | None = None) -> dict:
    ...

@svc.act_tool("request_remake", level=GateLevel.AUTOMATIC, max_calls=5)
def request_remake(order_id: str, reason: str) -> dict:
    ...

@svc.act_tool("issue_comp", level=GateLevel.NEEDS_APPROVAL)  # human-gated
def issue_comp(order_id: str, amount: float) -> dict:
    ...

if __name__ == "__main__":
    svc.run()   # starts the MCP server
```

Everything else — logging, replay, delivery, retries, gating, telemetry — is
inherited from the core.

## Reference service

`examples/order_accuracy/service.py` is a complete Order Accuracy service
(walkthrough §7.1). Use it as the template for the rest.

## Try it (no MCP SDK needed)

```bash
python examples/smoke_test.py
```

Exercises emit → log → idempotent replay → read tools → gated actions
(auto / approval / blocked / rate-limited) → describe → telemetry.

## How the agent uses it

Hermes connects to each service as an MCP client. On connect it calls `describe`
to learn the event types and tools, `subscribe`s to what it cares about, calls
`read` tools to gather, and calls `act` tools **through the Policy Gate**. Because
every service exposes the identical contract, onboarding a new service needs no
Hermes code changes.

## Status

Proposed / draft — for discussion. Per the rollout plan, build Order Accuracy and
Kiosk on this, then harden the core from what the two real services actually need.
