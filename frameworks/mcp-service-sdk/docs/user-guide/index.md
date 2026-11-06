# MCP Service SDK

The `mcp-service-sdk` provides a reusable Python contract for agent-facing services in the Open Edge Platform ecosystem. It standardizes how services expose event types, subscriptions, replayable history, read tools, and action tools so that an agent can interact with them consistently across different implementations.

## Overview

This SDK is designed for services that need to participate in a common MCP-based contract without re-implementing the same plumbing each time. The library handles the shared concerns: event envelopes, durable logs, subscription dispatch, action gating, telemetry, and MCP server adaptation.

The core idea is simple:

- each service emits a typed event envelope
- events are first written to a durable log
- subscribers are notified through the registered callback flow
- read tools expose current or historical state
- action tools go through policy gating before execution
- telemetry is emitted so latency and behavior can be tracked

This keeps service logic focused on its domain instead of the agent contract itself.

## Installation

Install the core package:

```bash
pip install -e /absolute/path/to/edge-ai-libraries/frameworks/mcp-service-sdk
```

Install the optional MCP backend if you want to run an MCP server:

```bash
pip install -e /absolute/path/to/edge-ai-libraries/frameworks/mcp-service-sdk[mcp]
```

Or use the Git dependency form in another project:

```toml
dependencies = [
    "mcp-service-sdk[mcp] @ git+https://github.com/sachinkaushik/edge-ai-libraries.git@<tag-or-commit>#subdirectory=frameworks/mcp-service-sdk",
]
```

## Quick Start

Create a service instance and register an event type:

```python
from mcp_service_sdk import GateLevel, ServiceServer

svc = ServiceServer(service="order_accuracy", store_id="store-001")
svc.register_event_type("order_mismatch", schema={"order_id": "str", "station": "str"})
```

Add a read tool:

```python
@svc.read_tool("rework_rate", description="Rework rate for a daypart.")
def rework_rate(daypart: str, station: str | None = None) -> dict:
    return {"daypart": daypart, "station": station, "rate": 0.03}
```

Add a gated action tool:

```python
@svc.act_tool("request_remake", level=GateLevel.AUTOMATIC, max_calls=5)
def request_remake(order_id: str, reason: str) -> dict:
    return {"status": "accepted", "order_id": order_id, "reason": reason}
```

Start the MCP server:

```python
if __name__ == "__main__":
    svc.run()
```

## Main Capabilities

### Event Envelope

All emitted events follow a standard envelope with service, store, timestamp, payload, and reference metadata. This makes the event format consistent across services and simplifies replay and downstream processing.

### Durable Log

Events are written before dispatch so they survive service restarts and can be replayed later. This is critical when an agent reconnects or when a consumer needs recent history.

### Subscription Flow

Services can expose subscription hooks so interested consumers can listen for specific event types or conditions. Event matching is done with a condition expression, making it easy to subscribe only to relevant events.

### Policy Gate

Actions are not executed blindly. The SDK supports levels such as automatic, approval-required, and blocked. This ensures agent-triggered actions remain safe and auditable.

### Telemetry

The SDK tracks operational timing across emit, read, and action paths so teams can identify latency or broken flows quickly.

## Typical Service Flow

```text
Service code
  -> register event types
  -> emit events
  -> write to durable log
  -> fan out to subscribers
  -> evaluate read tools
  -> enforce action policy
  -> return MCP response
```

## Related Components

- `server.py` — service lifecycle and MCP binding
- `envelope.py` — standard event structure
- `log.py` — durable event storage
- `delivery.py` — event sink behavior
- `policy.py` — gate and action-validation logic
- `telemetry.py` — timing and observability support

## Next Steps

Use the package documentation in this folder for deeper examples and the contract model. For real service integration, start from a reference implementation and follow the same event schema, read tool, and action-tool patterns used by the rest of the Open Edge Platform services.
