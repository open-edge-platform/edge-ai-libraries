"""ServiceServer — the MCP scaffolding that ties the contract together.

A service creates one ``ServiceServer``, registers its event types and its
read/act tools, and calls ``run()``. The core wires in the durable log, delivery
fan-out, policy gate, and telemetry so the service only writes domain code.

MCP capabilities exposed to the agent (walkthrough §3):
- describe   — event types, payload schemas, available tools.
- subscribe  — event name + condition + callback address.
- read tools — broadly exposed (registered via @read_tool).
- act tools  — narrowly allow-listed and gated (registered via @act_tool).

The ``mcp`` SDK is imported lazily inside :meth:`to_mcp`, so the rest of the
library (emit, describe, log, policy) works and is testable without it installed.
"""

from __future__ import annotations

import functools
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from .delivery import Delivery, DisabledSink, WebhookSink
from .envelope import EventEnvelope, new_event
from .log import DurableLog, JSONLFileLog, SQLiteLog
from .policy import ActionSpec, GateLevel, PolicyGate
from .telemetry import MetricsBackend, NullTelemetry, Telemetry


@dataclass
class _Tool:
    name: str
    fn: Callable[..., Any]
    description: str
    schema: dict[str, Any]


def _docstring(fn: Callable[..., Any]) -> str:
    """First paragraph of a function's docstring, used as the tool description."""
    import inspect

    return inspect.getdoc(fn) or ""


def _condition_matches(condition: str, event: EventEnvelope) -> bool:
    """Evaluate the small declarative condition language used by subscribe."""
    condition = condition.strip()
    if not condition or condition.lower() in {"*", "true", "all"}:
        return True
    if "==" not in condition:
        return False
    field, expected = (part.strip() for part in condition.split("==", 1))
    expected = expected.strip("\"'").lower()
    if field == "event_type":
        actual = event.event_type
    else:
        actual = event.payload.get(field)
    return str(actual).lower() == expected


def _post_subscription_event(callback_url: str, event: EventEnvelope) -> bool:
    body = json.dumps({
        "type": "mcp_event",
        "event": json.loads(event.to_json()),
    }).encode("utf-8")
    request = urllib.request.Request(
        callback_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(3):
        try:
            with opener.open(request, timeout=5) as response:
                if 200 <= response.status < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                return False
        time.sleep(0.5 * (2**attempt))
    return False


@dataclass
class _Subscription:
    event_type: str
    condition: str
    callback_url: str


@dataclass
class ServiceConfig:
    """Façade config — build a ServiceServer without touching internal classes.

    Selects the log strategy, delivery strategy, metrics strategy, and timeout.
    """

    service: str
    store_id: str
    log_backend: str = "sqlite"   # sqlite | jsonl | memory
    log_path: str = ":memory:"
    delivery: str = "off"          # off | webhook
    webhook_url: str | None = None
    metrics: str = "memory"        # memory | null
    tool_timeout_s: float | None = None
    expose_subscribe: bool = True


@dataclass
class ServiceServer:
    """One per service. Domain code registers tools; the core does the plumbing.

    This is the **façade**: services use ``read_tool``/``act_tool``/``emit``/``run``
    and never touch the log, delivery, policy, or metrics classes directly. Use
    :meth:`from_config` to select backends without importing internals.
    """

    service: str
    store_id: str
    log: DurableLog = field(default=None)  # type: ignore[assignment]
    delivery: Delivery = field(default=None)  # type: ignore[assignment]
    policy: PolicyGate = field(default_factory=PolicyGate)
    telemetry: MetricsBackend = field(default=None)  # type: ignore[assignment]
    # Soft per-tool timeout (seconds); None disables. Runs the tool in a worker
    # thread and raises TimeoutError if it overruns.
    tool_timeout_s: float | None = None
    expose_subscribe: bool = True

    _event_types: dict[str, dict] = field(default_factory=dict)
    _read_tools: dict[str, _Tool] = field(default_factory=dict)
    _act_tools: dict[str, _Tool] = field(default_factory=dict)
    _subscriptions: list[_Subscription] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.log is None:
            self.log = SQLiteLog(service=self.service)
        if self.delivery is None:
            self.delivery = Delivery(sinks=[DisabledSink()])
        if self.telemetry is None:
            self.telemetry = Telemetry(service=self.service)

    @classmethod
    def from_config(cls, cfg: ServiceConfig) -> "ServiceServer":
        """Build a ServiceServer from config, selecting log/delivery/metrics strategies."""
        if cfg.log_backend in ("sqlite", "memory"):
            path = ":memory:" if cfg.log_backend == "memory" else cfg.log_path
            log: DurableLog = SQLiteLog(path=path, service=cfg.service)
        elif cfg.log_backend == "jsonl":
            log = JSONLFileLog(path=cfg.log_path, service=cfg.service)
        else:
            raise ValueError(f"unknown log_backend: {cfg.log_backend}")

        if cfg.delivery == "off":
            delivery = Delivery(sinks=[DisabledSink()])
        elif cfg.delivery == "webhook":
            if not cfg.webhook_url:
                raise ValueError("delivery='webhook' requires webhook_url")
            delivery = Delivery(sinks=[WebhookSink(cfg.webhook_url)])
        else:
            raise ValueError(f"unknown delivery: {cfg.delivery}")

        telemetry: MetricsBackend = (
            NullTelemetry(cfg.service) if cfg.metrics == "null" else Telemetry(cfg.service)
        )
        return cls(
            service=cfg.service,
            store_id=cfg.store_id,
            log=log,
            delivery=delivery,
            telemetry=telemetry,
            tool_timeout_s=cfg.tool_timeout_s,
            expose_subscribe=cfg.expose_subscribe,
        )

    # -- internal invocation (timeout strategy) ---------------------------

    def _invoke(self, fn: Callable[..., Any], args: dict[str, Any]) -> Any:
        """Call a tool, enforcing the soft timeout when configured."""
        if self.tool_timeout_s is None:
            return fn(**args)
        fut = self._get_executor().submit(fn, **args)
        return fut.result(timeout=self.tool_timeout_s)

    def _get_executor(self):
        ex = getattr(self, "_executor_obj", None)
        if ex is None:
            from concurrent.futures import ThreadPoolExecutor

            ex = ThreadPoolExecutor(max_workers=8, thread_name_prefix=self.service)
            self._executor_obj = ex
        return ex

    # -- registration -----------------------------------------------------

    def register_event_type(self, name: str, schema: dict[str, Any]) -> None:
        self._event_types[name] = schema

    def read_tool(
        self, name: str, description: str | None = None, schema: dict | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a broadly-exposed read tool.

        If ``description`` is omitted, the function's docstring is used (the
        standard MCP convention).
        """

        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            desc = description if description is not None else _docstring(fn)
            self._read_tools[name] = _Tool(name, fn, desc, schema or {})
            return fn

        return deco

    def act_tool(
        self,
        name: str,
        level: GateLevel,
        description: str | None = None,
        schema: dict | None = None,
        max_calls: int | None = None,
        per_seconds: float = 60.0,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register an action tool and its policy-gate level + rate limit.

        If ``description`` is omitted, the function's docstring is used.
        """

        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
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

        return deco

    # -- runtime ----------------------------------------------------------

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any],
        ref_id: str | None = None,
    ) -> EventEnvelope:
        """Emit-to-log-first, then fan out to enabled sinks (walkthrough §4)."""
        event = new_event(event_type, self.service, self.store_id, payload, ref_id)
        with self.telemetry.span(f"emit:{event_type}"):
            self.log.append(event)
            self.delivery.dispatch(event)
            self._notify_subscribers(event)
        return event

    def call_action(self, name: str, **args: Any) -> dict[str, Any]:
        """Run an act tool THROUGH the policy gate. The only path to acting."""
        decision = self.policy.evaluate(name, args)
        if not decision.allowed:
            return {
                "executed": False,
                "level": decision.level.value,
                "reason": decision.reason,
            }
        with self.telemetry.span(f"act:{name}"):
            result = self._invoke(self._act_tools[name].fn, args)
        return {"executed": True, "level": decision.level.value, "result": result}

    def subscribe(self, event_type: str, condition: str, callback_url: str) -> None:
        self._subscriptions.append(_Subscription(event_type, condition, callback_url))

    def _notify_subscribers(self, event: EventEnvelope) -> None:
        for subscription in self._subscriptions:
            if subscription.event_type != event.event_type:
                continue
            if not _condition_matches(subscription.condition, event):
                continue
            _post_subscription_event(subscription.callback_url, event)

    def describe(self) -> dict[str, Any]:
        """Self-description rich enough for a coding agent to use unassisted."""
        return {
            "service": self.service,
            "store_id": self.store_id,
            "event_types": self._event_types,
            "read_tools": {
                t.name: {"description": t.description, "schema": t.schema}
                for t in self._read_tools.values()
            },
            "act_tools": {
                t.name: {
                    "description": t.description,
                    "schema": t.schema,
                    "gate": self.policy._actions[t.name].level.value,
                }
                for t in self._act_tools.values()
            },
        }

    # -- MCP binding (lazy import) ----------------------------------------

    def to_mcp(self):  # noqa: ANN201 - returns an MCP server instance
        """Build an MCP server exposing describe/subscribe/read/act.

        Backend is auto-selected in this order:
        1. ``fastmcp`` (standalone FastMCP 2.x, https://gofastmcp.com)
        2. ``mcp.server.MCPServer`` (official mcp >= 2.0)
        3. ``mcp.server.fastmcp.FastMCP`` (official mcp 1.x)

        All three expose the same ``.tool()`` decorator and ``.run()`` API and
        speak the same MCP protocol on the wire. Install one of:

        - ``pip install mcp-service-base[mcp]``      (official SDK)
        - ``pip install mcp-service-base[fastmcp]``  (standalone FastMCP 2.x)
        """
        try:
            from fastmcp import FastMCP as _Server  # standalone fastmcp 2.x
        except ImportError:
            try:
                from mcp.server import MCPServer as _Server  # mcp >= 2.0
            except ImportError:
                try:
                    from mcp.server.fastmcp import FastMCP as _Server  # mcp 1.x
                except ImportError as exc:  # pragma: no cover - env-dependent
                    raise RuntimeError(
                        "No MCP backend found. Install one of: "
                        "'pip install mcp-service-base[mcp]' or "
                        "'pip install mcp-service-base[fastmcp]'"
                    ) from exc

        app = _Server(self.service)

        @app.tool(name="describe", description="Describe this service's contract.")
        def _describe() -> dict:
            return self.describe()

        if self.expose_subscribe:
            @app.tool(name="subscribe", description="Subscribe to an event type.")
            def _subscribe(event_type: str, condition: str, callback_url: str) -> dict:
                self.subscribe(event_type, condition, callback_url)
                return {"subscribed": event_type, "condition": condition}

        for tool in self._read_tools.values():
            app.tool(name=tool.name, description=tool.description)(
                self._wrap_read(tool)
            )

        # Action tools are exposed but routed through the gate, never called raw.
        for tool in self._act_tools.values():
            self._bind_gated_action(app, tool)

        return app

    def _wrap_read(self, tool: _Tool) -> Callable[..., Any]:
        """Wrap a read tool with telemetry + timeout, preserving its signature.

        ``functools.wraps`` sets ``__wrapped__`` so the MCP SDK still derives the
        input schema from the original function's typed parameters.
        """

        @functools.wraps(tool.fn)
        def wrapper(**args: Any) -> Any:
            with self.telemetry.span(f"read:{tool.name}"):
                return self._invoke(tool.fn, args)

        return wrapper

    def _bind_gated_action(self, app, tool: _Tool) -> None:
        gate_level = self.policy._actions[tool.name].level.value

        # functools.wraps preserves the signature so the SDK exposes the params.
        @functools.wraps(tool.fn)
        def gated(**args: Any) -> dict:
            return self.call_action(tool.name, **args)

        app.tool(
            name=tool.name,
            description=f"[gate={gate_level}] {tool.description}",
        )(gated)

    def run(
        self,
        transport: str = "stdio",
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        """Start the MCP server.

        transport: ``stdio`` (default, local/CLI) or ``streamable-http`` / ``sse``
        for a long-lived networked server (containers, so the agent can reach it).
        host/port apply only to the HTTP transports.
        """
        app = self.to_mcp()
        if transport == "stdio":
            app.run("stdio")
            return
        kwargs: dict[str, Any] = {}
        if host is not None:
            kwargs["host"] = host
        if port is not None:
            kwargs["port"] = port
        app.run(transport, **kwargs)

