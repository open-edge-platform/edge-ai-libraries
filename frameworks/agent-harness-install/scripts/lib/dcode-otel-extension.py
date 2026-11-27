# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Managed by agent-harness-install (metrics)
"""dcode extension: export the agent's LangChain/LangGraph runs as OpenTelemetry spans.

Installed by './install.sh observability enable' as
<DEEPAGENTS_HOME>/extensions/agent_harness_otel.py and driven by the settings
file <DEEPAGENTS_HOME>/agent-harness-otel.json (written by the same command):

    {"enabled": true, "endpoint": "http://127.0.0.1:4319/v1/traces", "content": "off"}

dcode has native tracing for LangSmith only. This extension attaches one
LangChain callback handler to every run of the agent and turns the runs into
spans (graph nodes, model calls, tool calls) following the OpenTelemetry GenAI
conventions (gen_ai.*), with the langfuse.observation.* attributes alongside so
the same spans can be ingested by Langfuse's OTLP endpoint. They go over
OTLP/HTTP protobuf to a loopback receiver (SQLite) or to Jaeger. Nothing is
sent anywhere else, and prompt/response text is only attached when "content"
is "preview" or "full".

Needs only packages dcode already ships with (langchain-core and the
OpenTelemetry SDK/OTLP-HTTP exporter pulled in by langgraph-api). dcode loads
extensions only with DEEPAGENTS_CODE_EXPERIMENTAL=1 (the installer sets it in
the dcode profile's .env); changes take effect when dcode is restarted.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import OrderedDict
from contextvars import ContextVar
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError:  # dcode environment without langchain-core: extension() then does nothing
    BaseCallbackHandler = object  # type: ignore[assignment,misc]

logger = logging.getLogger("agent_harness_otel")

CONFIG_NAME = "agent-harness-otel.json"
# Spans still open when this many are tracked are ended and dropped (a run
# that never reports completion would otherwise be held forever).
_MAX_OPEN = 5000
_PREVIEW_CHARS = 200
_FULL_CHARS = 32768
_HIDDEN_TAG = "langsmith:hidden"


def _config_path() -> Path:
    override = os.environ.get("HARNESS_DCODE_OTEL_CONFIG")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / CONFIG_NAME


def _load_config() -> dict[str, Any] | None:
    try:
        cfg = json.loads(_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(cfg, dict) or cfg.get("enabled") is not True:
        return None
    endpoint = cfg.get("endpoint")
    if not isinstance(endpoint, str) or urlparse(endpoint).scheme not in ("http", "https"):
        return None
    content = cfg.get("content")
    return {"endpoint": endpoint, "content": content if content in ("preview", "full") else "off"}


def _is_loopback(url: str) -> bool:
    return urlparse(url).hostname in ("127.0.0.1", "localhost", "::1")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def _shrink(value: Any, limit: int) -> Any:
    """Clip every string inside `value`, so the JSON written for it stays valid."""
    if isinstance(value, str):
        return _clip(value, limit)
    if isinstance(value, list):
        return [_shrink(v, limit) for v in value]
    if isinstance(value, dict):
        return {k: _shrink(v, limit) for k, v in value.items()}
    return value


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _message_dict(message: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "role": getattr(message, "type", type(message).__name__),
        "content": _jsonable(getattr(message, "content", message)),
    }
    calls = getattr(message, "tool_calls", None)
    if calls:
        entry["tool_calls"] = [
            {"name": c.get("name"), "args": _jsonable(c.get("args"))} for c in calls if isinstance(c, dict)
        ]
    return entry


class _OtelHandler(BaseCallbackHandler):
    """Maps LangChain run callbacks to OpenTelemetry spans."""

    # Run in the caller's context so span parenting never depends on a thread hop.
    run_inline = True

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spans: OrderedDict[Any, Any] = OrderedDict()
        # run_id -> run_id of the nearest recorded ancestor, for runs that get no span of their own.
        self._alias: dict[Any, Any] = {}
        self._roots: set[Any] = set()
        self._provider: Any = None
        self._tracer: Any = None
        self._endpoint = ""
        self.content = "off"

    # -- setup ---------------------------------------------------------------

    def configure(self, cfg: dict[str, Any] | None) -> None:
        """Apply the settings file; `None` switches the handler off."""
        with self._lock:
            if cfg is None:
                self._tracer = None
                self.content = "off"
                return
            self.content = cfg["content"]
            if cfg["endpoint"] != self._endpoint or self._tracer is None:
                self._build_exporter(cfg["endpoint"])

    def _build_exporter(self, endpoint: str) -> None:
        import requests
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        session = requests.Session()
        loopback = _is_loopback(endpoint)
        # Loopback collectors must not be sent through a corporate proxy.
        session.trust_env = not loopback
        provider = TracerProvider(resource=Resource.create({"service.name": "dcode"}))
        provider.add_span_processor(
            BatchSpanProcessor(
                # A short timeout keeps a dead local collector from delaying dcode's exit.
                OTLPSpanExporter(endpoint=endpoint, session=session, timeout=3 if loopback else 10),
                schedule_delay_millis=500,
            )
        )
        old = self._provider
        # The provider is private: the process-wide OpenTelemetry one (if any) is left alone.
        self._provider = provider
        self._tracer = provider.get_tracer("agent-harness-install.dcode")
        self._endpoint = endpoint
        if old is not None:
            # Runs still open end on the old provider, so it is shut down only after a grace period.
            timer = threading.Timer(60.0, self._shutdown_provider, args=(old,))
            timer.daemon = True
            timer.start()

    @staticmethod
    def _shutdown_provider(provider: Any) -> None:
        try:
            provider.shutdown()
        except Exception:  # noqa: BLE001
            logger.debug("previous exporter shutdown failed", exc_info=True)

    def flush(self) -> None:
        provider = self._provider
        if provider is not None:
            try:
                provider.force_flush(3000)
            except Exception:  # noqa: BLE001
                logger.debug("flush failed", exc_info=True)

    # -- span bookkeeping ----------------------------------------------------

    def _parent_context(self, parent_run_id: Any) -> Any:
        from opentelemetry import trace

        run_id = parent_run_id
        with self._lock:
            while run_id is not None and run_id not in self._spans:
                run_id = self._alias.get(run_id)
            span = self._spans.get(run_id) if run_id is not None else None
        return trace.set_span_in_context(span) if span is not None else None

    def _start(self, run_id: Any, parent_run_id: Any, name: str, attrs: dict[str, Any]) -> None:
        tracer = self._tracer
        if tracer is None:
            return
        span = tracer.start_span(name, context=self._parent_context(parent_run_id), attributes=attrs)
        evicted = None
        with self._lock:
            self._spans[run_id] = span
            if parent_run_id is None:
                self._roots.add(run_id)
            if len(self._spans) > _MAX_OPEN:
                evicted_id, evicted = self._spans.popitem(last=False)
                self._roots.discard(evicted_id)
                self._alias.pop(evicted_id, None)
        if evicted is not None:
            evicted.end()

    def _skip(self, run_id: Any, parent_run_id: Any) -> None:
        """Run without a span of its own: its children attach to the nearest recorded ancestor."""
        if parent_run_id is not None:
            with self._lock:
                if len(self._alias) > 4 * _MAX_OPEN:
                    self._alias.clear()
                self._alias[run_id] = parent_run_id

    def _end(self, run_id: Any, attrs: dict[str, Any] | None = None, error: BaseException | None = None) -> None:
        from opentelemetry.trace import Status, StatusCode

        with self._lock:
            span = self._spans.pop(run_id, None)
            self._alias.pop(run_id, None)
            is_root = run_id in self._roots
            self._roots.discard(run_id)
        if span is None:
            return
        if attrs:
            span.set_attributes(attrs)
        if error is not None:
            span.set_attribute("error.type", type(error).__name__)
            detail = _clip(str(error), _PREVIEW_CHARS) if self.content != "off" else None
            span.set_status(Status(StatusCode.ERROR, detail))
        span.end()
        if is_root:
            # A short session (dcode -n) ends right after its last run: do not wait for the batch timer.
            threading.Thread(target=self.flush, name="agent-harness-otel-flush", daemon=True).start()

    def _capture(self, text: str) -> str | None:
        if self.content == "off":
            return None
        return _clip(text, _PREVIEW_CHARS if self.content == "preview" else _FULL_CHARS)

    def _capture_json(self, value: Any) -> str | None:
        if self.content == "off":
            return None
        if self.content == "preview":
            return json.dumps(_shrink(value, _PREVIEW_CHARS), default=str)
        return _clip(json.dumps(value, default=str), _FULL_CHARS)

    # -- chains (graph nodes) ------------------------------------------------

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, tags=None, metadata=None, name=None, **kwargs):  # noqa: ANN001, ANN003, ARG002
        if self._tracer is None:
            return
        metadata = metadata or {}
        node = metadata.get("langgraph_node")
        run_name = name or (serialized or {}).get("name") or "chain"
        recorded = parent_run_id is None or (node is not None and run_name == node)
        if not recorded or _HIDDEN_TAG in (tags or ()):
            self._skip(run_id, parent_run_id)
            return
        attrs: dict[str, Any] = {"langfuse.observation.type": "span", "langchain.run.type": "chain"}
        if node is not None:
            attrs["langgraph.node"] = node
        thread = metadata.get("thread_id")
        if thread is not None:
            attrs["session.id"] = str(thread)
        self._start(run_id, parent_run_id, run_name, attrs)

    def on_chain_end(self, outputs, *, run_id, **kwargs):  # noqa: ANN001, ANN003, ARG002
        self._end(run_id)

    def on_chain_error(self, error, *, run_id, **kwargs):  # noqa: ANN001, ANN003, ARG002
        self._end(run_id, error=error)

    # -- model calls ---------------------------------------------------------

    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, tags=None, metadata=None, **kwargs):  # noqa: ANN001, ANN003, ARG002
        flat = messages[0] if messages else []
        self._llm_start(run_id, parent_run_id, metadata or {}, kwargs.get("invocation_params") or {}, flat)

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, tags=None, metadata=None, **kwargs):  # noqa: ANN001, ANN003, ARG002
        self._llm_start(run_id, parent_run_id, metadata or {}, kwargs.get("invocation_params") or {}, [{"role": "user", "content": p} for p in prompts[:1]])

    def _llm_start(self, run_id: Any, parent_run_id: Any, metadata: dict, params: dict, messages: list) -> None:
        if self._tracer is None:
            return
        model = metadata.get("ls_model_name") or params.get("model") or params.get("model_name") or "unknown"
        attrs: dict[str, Any] = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": str(model),
            "langfuse.observation.type": "generation",
            "langchain.run.type": "llm",
        }
        provider = metadata.get("ls_provider")
        if provider:
            attrs["gen_ai.system"] = str(provider)
        for key, attr in (("ls_temperature", "gen_ai.request.temperature"), ("ls_max_tokens", "gen_ai.request.max_tokens")):
            if metadata.get(key) is not None:
                attrs[attr] = metadata[key]
        thread = metadata.get("thread_id")
        if thread is not None:
            attrs["session.id"] = str(thread)
        if self.content != "off" and messages:
            if self.content == "preview":
                messages = messages[-1:]
            dicts = [m if isinstance(m, dict) else _message_dict(m) for m in messages]
            attrs["gen_ai.input.messages"] = self._capture_json(dicts)
            attrs["langfuse.observation.input"] = attrs["gen_ai.input.messages"]
        self._start(run_id, parent_run_id, f"chat {model}", attrs)

    def on_llm_end(self, response, *, run_id, **kwargs):  # noqa: ANN001, ANN003, ARG002
        attrs: dict[str, Any] = {}
        try:
            generation = response.generations[0][0]
            message = getattr(generation, "message", None)
            usage = getattr(message, "usage_metadata", None) or {}
            meta = getattr(message, "response_metadata", None) or {}
            llm_output = response.llm_output or {}
            tokens = llm_output.get("token_usage") or {}
            in_tok = usage.get("input_tokens", tokens.get("prompt_tokens"))
            out_tok = usage.get("output_tokens", tokens.get("completion_tokens"))
            if in_tok is not None:
                attrs["gen_ai.usage.input_tokens"] = int(in_tok)
            if out_tok is not None:
                attrs["gen_ai.usage.output_tokens"] = int(out_tok)
            model = meta.get("model_name") or llm_output.get("model_name")
            if model:
                attrs["gen_ai.response.model"] = str(model)
            reason = meta.get("finish_reason")
            if reason:
                attrs["gen_ai.response.finish_reasons"] = [str(reason)]
            if self.content != "off":
                out = _message_dict(message) if message is not None else {"role": "assistant", "content": generation.text}
                attrs["gen_ai.output.messages"] = self._capture_json([out])
                attrs["langfuse.observation.output"] = attrs["gen_ai.output.messages"]
        except Exception:  # noqa: BLE001
            logger.debug("could not read the model response", exc_info=True)
        self._end(run_id, attrs)

    def on_llm_error(self, error, *, run_id, **kwargs):  # noqa: ANN001, ANN003, ARG002
        self._end(run_id, error=error)

    # -- tools ---------------------------------------------------------------

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, tags=None, metadata=None, inputs=None, name=None, **kwargs):  # noqa: ANN001, ANN003, ARG002
        if self._tracer is None:
            return
        tool = name or (serialized or {}).get("name") or "tool"
        attrs: dict[str, Any] = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": str(tool),
            "langfuse.observation.type": "tool",
            "langchain.run.type": "tool",
        }
        thread = (metadata or {}).get("thread_id")
        if thread is not None:
            attrs["session.id"] = str(thread)
        args = self._capture_json(_jsonable(inputs)) if inputs is not None else self._capture(str(input_str))
        if args is not None:
            attrs["gen_ai.tool.call.arguments"] = args
            attrs["langfuse.observation.input"] = args
        self._start(run_id, parent_run_id, f"execute_tool {tool}", attrs)

    def on_tool_end(self, output, *, run_id, **kwargs):  # noqa: ANN001, ANN003, ARG002
        attrs: dict[str, Any] = {}
        if self.content != "off":
            text = getattr(output, "content", output)
            result = self._capture(text if isinstance(text, str) else json.dumps(_jsonable(text), default=str))
            if result is not None:
                attrs["gen_ai.tool.call.result"] = result
                attrs["langfuse.observation.output"] = result
        self._end(run_id, attrs)

    def on_tool_error(self, error, *, run_id, **kwargs):  # noqa: ANN001, ANN003, ARG002
        self._end(run_id, error=error)


# Hook registration is process-global and cannot be undone, so it happens once
# per process; a /restart re-runs the extension and only re-reads the settings.
_handler: _OtelHandler | None = None


async def extension(d) -> None:  # noqa: ANN001, RUF029  # Extension factories are async by contract.
    """Attach the OpenTelemetry handler to every agent run.

    Args:
        d: The dcode extension API.
    """
    global _handler  # noqa: PLW0603

    if BaseCallbackHandler is object:
        logger.warning("agent-harness OpenTelemetry export disabled: langchain-core is not installed")
        return
    cfg = _load_config()
    if _handler is None:
        if cfg is None:
            return
        from langchain_core.tracers.context import register_configure_hook

        _handler = _OtelHandler()
        # The default (not .set()) is what every run context sees, as in dcode's cost recorder.
        register_configure_hook(ContextVar("agent_harness_otel_handler", default=_handler), inheritable=True)
        d.on_shutdown(_handler.flush)
    try:
        _handler.configure(cfg)
    except Exception:  # noqa: BLE001
        # Telemetry must never keep dcode from starting.
        logger.warning("agent-harness OpenTelemetry export disabled: could not set up the exporter", exc_info=True)
        _handler.configure(None)
