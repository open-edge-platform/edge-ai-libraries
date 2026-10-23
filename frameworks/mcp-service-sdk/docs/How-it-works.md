# `server.py` — Beginner Explanation

File: `src/mcp_service_sdk/server.py`

This file is the **heart** of the `mcp-service-sdk` library. It defines the
`ServiceServer` class that turns normal Python functions into MCP tools that an
LLM/agent (like Hermes) can call.

Think of it as a **starter kit** for building a service that talks to an AI
agent.

---

## 1. The Big Idea

Without this file, every team writing an MCP service would have to:

- Write their own MCP server setup
- Write their own audit log
- Write their own policy checks
- Write their own event delivery
- Write their own telemetry
- Handle stdio/HTTP transports themselves

With this file, they only write **domain functions**, and `ServiceServer`
handles all the rest.

Mental picture:

```text
Domain team writes:
   - a few Python functions

ServiceServer adds:
   - MCP protocol wiring
   - event log
   - safety gate for actions
   - delivery to webhooks
   - telemetry
   - stdio or HTTP transport
```

---

## 2. What The File Contains

The file has 4 building blocks:

1. `_Tool` — small internal record for a registered tool.
2. `_Subscription` — small internal record for an event subscription.
3. `ServiceConfig` — a plain settings object.
4. `ServiceServer` — the main class doing all the work.

---

## 3. `_Tool` — “what is a tool?”

```python
@dataclass
class _Tool:
    name: str
    fn: Callable[..., Any]
    description: str
    schema: dict[str, Any]
```

A tool is just:

- a name the agent uses (`Get_all_zones`)
- the Python function to call
- a text description shown to the LLM
- an optional JSON schema for input params

---

## 4. `_Subscription` — “someone wants events”

```python
@dataclass
class _Subscription:
    event_type: str
    condition: str
    callback_url: str
```

If the agent says:

> When you emit a `sad_violation` event where `zone = checkout`, POST it to this URL

that request is stored as one `_Subscription`.

---

## 5. `ServiceConfig` — “how do I want my service configured?”

```python
@dataclass
class ServiceConfig:
    service: str
    store_id: str
    log_backend: str = "sqlite"
    log_path: str = ":memory:"
    delivery: str = "off"
    webhook_url: str | None = None
    metrics: str = "memory"
    tool_timeout_s: float | None = None
```

| Setting | What it controls |
|---|---|
| `service` | Service name, for example `sad-mcp` |
| `store_id` | Which store/location |
| `log_backend` | Where events are stored: SQLite, JSONL file, or memory |
| `log_path` | File path for the log |
| `delivery` | Send events out to webhook or not |
| `webhook_url` | If delivery is on, where to send |
| `metrics` | Enable telemetry or use a null one |
| `tool_timeout_s` | Kill a tool if it runs too long |

This is a **façade** — you don’t need to import log/delivery/telemetry classes
yourself.

---

## 6. `ServiceServer` — The Main Class

Fields it holds:

```python
service          # name
store_id         # location
log              # durable event log
delivery         # event fan-out
policy           # safety gate for actions
telemetry        # metrics
tool_timeout_s   # optional timeout

_event_types     # declared event types
_read_tools      # dict of read tools
_act_tools       # dict of action tools
_subscriptions   # who is listening for events
```

You can think of it like this:

```text
ServiceServer =
   MCP server
 + tool registry
 + safety gate
 + event log + delivery
 + telemetry
 + a `run()` button
```

---

## 7. Two Ways To Create A ServiceServer

### Direct

```python
svc = ServiceServer(service="sad", store_id="store-001")
```

`__post_init__()` will:

- default log to `SQLiteLog`
- default delivery to disabled
- default telemetry to enabled

### From config (recommended)

```python
svc = ServiceServer.from_config(
    ServiceConfig(service="sad", store_id="store-001")
)
```

`from_config` reads settings and picks the right log/delivery/telemetry.

Beginner rule: **use `from_config` unless you know why you shouldn’t.**

---

## 8. Registering Tools

`read_tool` and `act_tool` are the two decorators a service uses to expose its
functions to the LLM. They look similar, but they take **different runtime
paths** and exist for different reasons.

Quick rule of thumb:

- `@svc.read_tool(...)` = safe query. Runs as-is.
- `@svc.act_tool(...)` = risky action. Runs **only if the policy gate allows**.

---

### 8.1 `read_tool` — Register A Safe Query

**What it is**

A decorator that says: “this function is a read-only lookup. Publish it to the
LLM and run it directly.”

```python
@svc.read_tool("Get_all_zones")
def get_all_zones() -> dict:
    """Return every zone in the store."""
    return {"zones": ["checkout", "aisle-3"]}
```

**Why we need it**

- Give the LLM a **standard, discoverable** way to ask for data.
- Keep the description close to the code (docstring) so it can’t drift.
- Add uniform **telemetry + optional timeout** without every team reinventing it.
- Separate reads from actions so audit and safety rules are clear.

**How it works**

Inside the decorator:

```python
def deco(fn):
    desc = description if description is not None else _docstring(fn)
    self._read_tools[name] = _Tool(name, fn, desc, schema or {})
    return fn
```

Two things happen:

1. Your function is stored in `self._read_tools[name]`.
2. Your function is returned **unchanged** so you can still call it normally in
   tests.

Later, when `to_mcp()` runs:

```python
for tool in self._read_tools.values():
    app.tool(name=tool.name, description=tool.description)(
        self._wrap_read(tool)
    )
```

`_wrap_read` uses `functools.wraps(tool.fn)` so the MCP SDK still sees the real
parameter types (correct input schema for the LLM), and adds telemetry + timeout.

**Runtime path**

```text
LLM calls Get_all_zones
   ↓
_wrap_read (telemetry span + timeout)
   ↓
your function
   ↓
return
```

**Rules**

- Must have no side effects. If it changes state, use `act_tool` instead.
- Description is auto-taken from the docstring — write a real one.
- Exposed broadly to the LLM.

---

### 8.2 `act_tool` — Register A Guarded Action

**What it is**

A decorator that says: “this function **changes something in the real world**.
Publish it to the LLM, but never let it run without going through the
`PolicyGate` first.”

```python
@svc.act_tool(
    "open_case",
    level=GateLevel.NEEDS_APPROVAL,
    max_calls=5,
    per_seconds=60,
)
def open_case(activity_id: str) -> dict:
    """Open an investigation case."""
    return {"case_id": "case-1", "activity_id": activity_id}
```

**Why we need it**

The LLM decides which tools to call and with what arguments. Without a gate, it
could:

- Refund the wrong customer.
- Delete real records after misreading a chat message.
- Be tricked by a prompt injection into destructive actions.

`act_tool` enforces one rule at the framework level:

> Actions must go through **approval / rate limiting / policy checks** before
> running.

Concretely it gives every service:

- **Safety** — the LLM cannot run the raw function, only the gated wrapper.
- **Governance** — one place to say “refunds always need approval”.
- **Rate limiting** — `max_calls` per `per_seconds` even for allowed actions.
- **Standard response shape** — always `{executed, level, result}` or
  `{executed, level, reason}`.
- **Uniform audit** — every action goes through `call_action`, so logs and
  metrics are consistent across services.

**How it works**

Inside the decorator:

```python
def deco(fn):
    desc = description if description is not None else _docstring(fn)
    self._act_tools[name] = _Tool(name, fn, desc, schema or {})
    self.policy.register(
        ActionSpec(
            name=name,
            level=level,
            max_calls=max_calls,
            per_seconds=per_seconds,
        )
    )
    return fn
```

Two things happen (this is the key difference from `read_tool`):

1. Your function is stored in a **separate** dict, `self._act_tools[name]`.
2. A **policy rule** is registered with `PolicyGate`:
   - `level` — `AUTOMATIC | NOTIFY | NEEDS_APPROVAL | BLOCKED`
   - `max_calls` per `per_seconds` — sliding-window rate limit

When `to_mcp()` runs, it does **not** hand your function to MCP. It binds a
`gated` wrapper via `_bind_gated_action`:

```python
def gated(**args):
    return self.call_action(tool.name, **args)
```

So the LLM can only reach your function through `call_action`, which checks
`PolicyGate` first.

**Runtime path**

```text
LLM calls open_case(activity_id="A-1")
   ↓
gated wrapper
   ↓
svc.call_action("open_case", activity_id="A-1")
   ↓
PolicyGate.evaluate("open_case", args)
   ├── BLOCKED             → {"executed": False, "level": "blocked"}
   ├── NEEDS_APPROVAL      → {"executed": False, "reason": "..."}
   ├── rate limit exceeded → {"executed": False, "reason": "rate_limited"}
   ├── NOTIFY              → allow + notify
   └── AUTOMATIC           → allow
   ↓ (only if allowed)
your function runs
   ↓
{"executed": True, "level": "...", "result": ...}
```

**Rules**

- Must include a `level` — the framework refuses to guess.
- Never call the raw function through MCP. It’s only reachable via
  `call_action`.
- The service (not the LLM) decides whether the action runs.

---

### 8.3 `read_tool` vs `act_tool` — Side By Side

| Aspect | `read_tool` | `act_tool` |
|---|---|---|
| Purpose | Query, no side effects | Do something that changes state |
| Storage bucket | `_read_tools` | `_act_tools` |
| Policy gate | No | Yes, mandatory |
| Rate limit | No | Optional (`max_calls`, `per_seconds`) |
| Level required | No | Yes (`GateLevel`) |
| Runtime path | `_wrap_read` → your fn | `_bind_gated_action` → `call_action` → gate → your fn |
| Description source | Arg or docstring | Arg or docstring |
| Response shape | Whatever your function returns | `{executed, level, result | reason}` |
| Exposed to LLM | Yes, directly | Yes, but only via gated wrapper |

**One-line summary**

> `read_tool` is the safe fast lane; `act_tool` is the guarded lane through the
> policy gate.

---

## 9. Why `GateLevel` Matters

Each action tool is labeled with:

- `AUTOMATIC` — allowed without approval
- `NOTIFY` — allowed but notify humans
- `NEEDS_APPROVAL` — must be approved
- `BLOCKED` — cannot run

Even if the LLM tries to call the tool directly, it goes through
`call_action(...)`, which checks the gate first.

Beginner rule: **the LLM cannot bypass the gate.**

---

## 10. Emitting Events

```python
svc.emit(
    "sad_violation",
    {"zone": "checkout", "activity": "concealment"},
)
```

Internally:

```text
build event envelope
   ↓
log.append(event)          # durable first
   ↓
delivery.dispatch(event)   # fan out to webhooks etc.
```

Order matters: **log first, then send.** So an event is never lost even if the
webhook fails.

---

## 11. `describe()` — “what tools do you have?”

The agent can ask the service for its contract and gets:

```json
{
  "service": "...",
  "store_id": "...",
  "event_types": {...},
  "read_tools": {...},
  "act_tools": {..., "gate": "NEEDS_APPROVAL"}
}
```

This helps the LLM plan without hardcoded knowledge.

---

## 12. `to_mcp()` — “become a real MCP server”

Steps:

1. Pick an MCP backend by import order:
   1. `fastmcp` (standalone FastMCP 2.x, https://gofastmcp.com)
   2. `mcp.server.MCPServer` (official `mcp >= 2.0`)
   3. `mcp.server.fastmcp.FastMCP` (official `mcp` 1.x)
2. Create an MCP `app`.
3. Register built-in tools: `describe`, `subscribe`.
4. Register every read tool.
5. Register every action tool, but wrapped through the safety gate.

All three backends expose the same `.tool()` / `.run()` API and speak the same
MCP protocol on the wire, so the LLM can’t tell them apart. Install one:

```bash
pip install mcp-service-sdk[mcp]       # official SDK
pip install mcp-service-sdk[fastmcp]   # standalone FastMCP 2.x
```

The backend imports happen **lazily** inside `to_mcp()`, so the rest of the
library can be used in tests **without installing any MCP backend**.

---

## 13. `_wrap_read` and `_bind_gated_action`

### `_wrap_read`

- Adds telemetry span
- Adds optional timeout
- Preserves the original signature via `functools.wraps`, so MCP still shows
  correct arguments to the LLM

### `_bind_gated_action`

- Never calls the raw action directly
- Routes through `call_action` → policy gate → real function

---

## 14. `run()` — start the server

```python
svc.run()                                    # stdio, default
svc.run(transport="streamable-http",         # HTTP mode
        host="0.0.0.0", port=9000)
```

Two common modes:

- **stdio** — a local subprocess launched by Hermes/agent.
- **streamable-http** — a long-lived HTTP MCP server, good for containers.

---

## 15. Full Beginner Example

```python
from mcp_service_sdk import GateLevel, ServiceConfig, ServiceServer

svc = ServiceServer.from_config(
    ServiceConfig(service="sad", store_id="store-001")
)

svc.register_event_type(
    "sad_violation",
    {"zone": "str", "activity": "str"},
)

@svc.read_tool("Get_all_zones")
def get_all_zones() -> dict:
    """List all zones."""
    return {"zones": ["checkout", "aisle-3"]}

@svc.act_tool("open_case", level=GateLevel.NEEDS_APPROVAL)
def open_case(activity_id: str) -> dict:
    """Open a case for a suspicious activity."""
    return {"case_id": "case-1", "activity_id": activity_id}

if __name__ == "__main__":
    svc.run()
```

This gives you:

- an MCP server named `sad`
- built-in tools `describe`, `subscribe`
- a read tool `Get_all_zones`
- an action tool `open_case` protected by the policy gate
- durable event log with `SQLiteLog`
- ready to be launched by any MCP client (stdio) or run as HTTP

---

## 16. One-Sentence Summary

`server.py` defines the reusable **`ServiceServer`** class that lets any service
register read/action tools as decorators, and then automatically become a full
MCP server with policy safety, event log, delivery, and telemetry — so your
service team only writes domain code, not MCP plumbing.