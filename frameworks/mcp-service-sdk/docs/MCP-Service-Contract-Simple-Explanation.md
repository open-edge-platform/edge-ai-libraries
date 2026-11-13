# MCP Service Contract: Simple Explanation

This document explains the five common verbs used by `mcp-service-sdk` services:

```text
describe   -> what events/tools/actions this service supports
subscribe  -> how consumers register interest in events
read       -> safe query tools
act        -> controlled action tools through policy gate
emit       -> standard event output path into durable log and delivery
```

The goal is simple: every agent-ready service should speak the same basic language, so Hermes or any MCP client can discover what the service does, listen for important events, query data, and request safe actions in a consistent way.

## 1. `describe`: What This Service Supports

`describe` is the service's self-introduction.

When Hermes connects to a service, it first needs to know:

- What events can this service emit?
- What read tools are available?
- What action tools are available?
- Which actions are automatic, blocked, or approval-gated?

Example:

```text
Hermes: What can you do?
SAD MCP Service: I support LOITERING, FOOD_SAFETY_VIOLATION, read tools for zone activity, and action tools for operator notification.
```

In SDK terms, `describe` returns a capability map. This avoids hardcoding service-specific assumptions into the agent.

## 2. `subscribe`: Notify Me When This Happens

`subscribe` means the agent registers interest in an event once, instead of repeatedly asking whether the event happened.

Simple version:

```text
Instead of Hermes asking again and again:

"Any new loitering event?"
"Any new loitering event?"
"Any new loitering event?"

Hermes tells the service once:

"When a LOITERING event happens, notify me."
```

Then the service watches for that event and sends it to Hermes only when it actually happens.

### Our Kitchen/Retail Use Case Example

In our suspicious activity detection use case:

```text
Scene Understanding Service
  detects a person in a HIGH_VALUE zone for more than the loiter threshold
  -> creates a LOITERING event
  -> notifies the subscribed consumer or agent
```

The flow:

```text
1. Hermes connects to the SAD MCP service.
2. Hermes calls describe:
   "What events do you support?"
3. The service says:
   "I support LOITERING, FOOD_SAFETY_VIOLATION, CONCEALMENT, and other events."
4. Hermes calls subscribe:
   "Notify me when LOITERING happens in a HIGH_VALUE zone."
5. Later, a person loiters in the kitchen-prep zone.
6. Scene Understanding emits LOITERING.
7. The service sends that event to Hermes or a configured callback.
8. Hermes can then call read tools for details or act tools for a response.
```

Example subscription intent:

```text
subscribe(
  event_type="LOITERING",
  condition="zone_type=HIGH_VALUE",
  callback_url="http://hermes/events"
)
```

Meaning:

```text
If someone loiters in a high-value zone, send that event to this callback URL.
```

Why this is better than polling:

| Polling | Subscribe |
|---|---|
| Agent keeps asking repeatedly | Agent asks once |
| Wastes calls when nothing happened | Service sends only real events |
| More noise | Cleaner event flow |
| Agent must remember what to check | Service owns event notification |
| May notice late depending on polling interval | Can notify as soon as the event is emitted |

In our case, Hermes does not need to constantly ask:

```text
"Is there any kitchen loitering?"
```

It subscribes once, then gets notified when the kitchen `LOITERING` event is emitted.

## 3. `read`: Safe Query Tools

`read` tools are safe lookups. They answer questions but do not change anything in the real world.

Examples from our use cases:

```text
Get current person zone activity.
Get recent LOITERING events.
Get order accuracy rate.
Get recent food safety violations.
Get active sessions in a zone.
```

A read tool is like asking:

```text
"What is happening right now?"
"What happened recently?"
"What is the current metric?"
```

Because read tools are safe, the SDK can expose them broadly to the agent. The SDK still wraps them with telemetry and optional timeout handling.

## 4. `act`: Controlled Action Tools Through Policy Gate

`act` tools do something. They may affect operators, systems, workflows, or external services.

Examples:

```text
Notify the operator.
Request a remake.
Trigger a webhook.
Publish an MQTT message.
Create a ticket.
Issue a comp or refund.
```

Because actions can have real consequences, the SDK does not let the LLM execute them directly. Every action goes through a deterministic policy gate.

The flow:

```text
Hermes requests an action
  -> PolicyGate checks whether the action is allowed
  -> If allowed, the action runs
  -> If approval is required, the action does not run automatically
  -> If blocked, the action is refused
```

Example:

```text
notify_operator -> AUTOMATIC
request_remake  -> AUTOMATIC with rate limit
issue_comp      -> NEEDS_APPROVAL
shutdown_camera -> BLOCKED
```

Key point:

```text
The LLM can request an action, but deterministic code decides whether it actually runs.
```

### Safe Action Controls: Simple Meaning

Safe action controls are the brakes and permission checks around anything the agent can do.

The agent can ask for an action, but the service decides whether that action is safe to execute.

This is similar to Copilot asking for permission before it edits a file or runs a terminal command:

```text
Copilot wants to run a command
  -> permission check happens
  -> user approves or rejects
  -> command runs only if approved
```

In SDK terms, this is like an `act` tool with approval control:

```text
act tool -> PolicyGate -> AUTOMATIC / NEEDS_APPROVAL / BLOCKED
```

Our use case examples:

```text
LOITERING event happens in kitchen
  -> Hermes asks to notify the operator
  -> notify_operator is AUTOMATIC
  -> action runs
```

```text
Order mismatch happens
  -> Hermes asks to issue a $20 comp
  -> issue_comp is NEEDS_APPROVAL
  -> action does not run automatically
  -> human approval is required
```

```text
Hermes asks to shut down a camera
  -> shutdown_camera is BLOCKED
  -> service refuses the action
```

So the rule is:

```text
Reading information is usually safe.
Doing something requires control.
```

## 5. `emit`: Standard Event Output Path

`emit` is how the service records that something happened.

Example:

```text
Person loitered in kitchen-prep zone.
Order accuracy mismatch detected.
Food safety violation detected.
```

When a service calls `emit`, the SDK follows a standard path:

```text
emit()
  -> write event to durable log first
  -> dispatch event to configured delivery sinks
```

Log-first is important. If delivery fails because a webhook is down or the agent is offline, the event is still stored and can be inspected or replayed later.

The `ref_id` field helps prevent duplicate events. If the same source event is retried, the SDK can treat it as the same event instead of appending a duplicate.

### Durable Event Logging: Simple Meaning

Durable event logging means important events are saved to storage before the service tries to send them anywhere.

Simple kitchen example:

```text
Person loiters in kitchen-prep zone
  -> service creates LOITERING event
  -> event is written to durable log
  -> service then tries to notify Hermes or alert service
```

Without durable logging:

```text
LOITERING happens
  -> service tries to notify Hermes
  -> Hermes is down
  -> event may be lost
```

With durable logging:

```text
LOITERING happens
  -> event is saved first
  -> delivery fails
  -> event still exists
  -> we can inspect or replay it later
```

In `mcp-service-sdk`, this is the `emit()` path:

```text
emit()
  -> log.append(event)        # save first
  -> delivery.dispatch(event) # notify later
```

The durable log can use SQLite or a JSONL file. For production, that file or database should live on persistent storage, such as a mounted volume.

Why it matters:

| Without durable log | With durable log |
|---|---|
| Events can disappear during restart | Events survive restart |
| Hard to debug missed alerts | We can inspect event history |
| Agent outage can lose data | Agent can catch up later |
| Duplicate retry handling is harder | `ref_id` makes writes idempotent |
| No replay path | Events can be replayed |

Example event stored in the durable log:

```json
{
  "event_type": "LOITERING",
  "service": "suspicious_activity",
  "store_id": "store_001",
  "payload": {
    "zone": "kitchen-prep",
    "person_id": "person-123",
    "dwell_seconds": 6.5
  },
  "ref_id": "scene-001/person-123/kitchen-prep/loitering/1789635869",
  "ts_ms": 1789635869000
}
```

In simple words:

```text
Durable event logging is the service's memory.
It saves important events before sending them anywhere.
```

## How All Five Fit Together

```text
Service side:

pipeline or app event
  -> emit()
  -> durable log
  -> delivery

Agent side:

describe   -> learn what the service supports
subscribe  -> ask to be notified about important events
read       -> query current or historical state
act        -> request controlled action through policy gate
```

End-to-end kitchen example:

```text
1. Scene Understanding detects a person loitering in kitchen-prep.
2. The service emits a LOITERING event.
3. The event is written to the durable log.
4. Hermes receives the event because it subscribed earlier.
5. Hermes calls a read tool to get zone/session details.
6. Hermes calls an act tool to notify the operator.
7. The policy gate allows or blocks that action based on configuration.
```

## One-Line Summary

`describe` tells the agent what the service can do, `subscribe` lets the agent listen for events, `read` lets it ask safe questions, `act` lets it request controlled actions through safe action controls, and `emit` gives the service a durable way to record and deliver events.
