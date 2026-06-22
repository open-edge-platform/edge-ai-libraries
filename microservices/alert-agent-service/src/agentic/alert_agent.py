# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
AlertActionAgent — dispatches tools when an alert fires.

Adapted from live-video-alert-agent/src/agentic/alert_agent.py:
  - stream_id  → source_id  (generic; works for cameras, audio, sensors, etc.)
  - Tools loaded from src.tools.* (not src.agentic.tools.*)
  - ADK instruction is modality-agnostic
  - No frame-callback / VideoCapture dependency
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.config import settings
from src.schemas.monitor import AlertConfig
from src.agentic.mcp_client import get_tool_defaults

logger = logging.getLogger(__name__)

_CONTEXT_TEMPLATE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

_TOOLS_CONFIG_FILE = Path("resources/tools.json")
_TOOL_TIMEOUT = 10.0  # per-tool execution timeout in seconds


def _load_tools_config() -> Tuple[Dict[str, Callable], List[dict]]:
    """
    Load tool registry from resources/tools.json.

    Returns (tool_map, tool_schemas) where:
      - tool_map: {name: async_callable}
      - tool_schemas: OpenAI-compatible function schemas for LLM dispatch
    """
    tool_map: Dict[str, Callable] = {}
    tool_schemas: List[dict] = []

    if not _TOOLS_CONFIG_FILE.exists():
        logger.warning(f"Tools config not found: {_TOOLS_CONFIG_FILE} — using empty registry")
        return {}, []

    try:
        with open(_TOOLS_CONFIG_FILE) as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError) as exc:
        logger.error(f"Failed to load tools.json: {exc} — using empty registry")
        return {}, []

    for tool in config:
        name = tool.get("name")
        if not name:
            continue

        if not tool.get("enabled", True):
            logger.info(f"Tool '{name}' is disabled in config — skipping")
            continue

        requires_env = tool.get("requires_env", [])
        missing = [e for e in requires_env if not os.getenv(e)]
        if missing:
            logger.debug(f"Tool '{name}' missing env vars {missing} — will skip at runtime")

        try:
            module_path = tool.get("module")
            func_name = tool.get("function")
            if not module_path or not func_name:
                logger.warning(f"Tool '{name}' missing module/function — skipping")
                continue

            module = importlib.import_module(module_path)
            fn = getattr(module, func_name)
            tool_map[name] = fn

            tool_schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description", f"Execute {name} action"),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            })
            logger.debug(f"Loaded tool: {name} from {module_path}.{func_name}")

        except (ImportError, AttributeError) as exc:
            logger.error(f"Failed to load tool '{name}': {exc}")
            continue

    logger.info(f"Loaded {len(tool_map)} tools from {_TOOLS_CONFIG_FILE}")
    return tool_map, tool_schemas


_TOOL_MAP, _TOOL_SCHEMAS = _load_tools_config()

_MCP_TOOL_MAP: Dict[str, Callable] = {}
_MCP_TOOL_SCHEMAS: List[dict] = []
_MCP_TOOL_LOCK = threading.Lock()


def register_mcp_tools(tool_map: Dict[str, Callable], tool_schemas: List[dict]):
    """Register MCP tools with the alert agent (called after MCP initialisation)."""
    global _MCP_TOOL_MAP, _MCP_TOOL_SCHEMAS
    with _MCP_TOOL_LOCK:
        _MCP_TOOL_MAP = tool_map
        _MCP_TOOL_SCHEMAS = tool_schemas
    logger.info(f"Registered {len(tool_map)} MCP tools with AlertActionAgent")


def clear_mcp_tools():
    """Clear registered MCP tools (called during MCP shutdown / reload)."""
    global _MCP_TOOL_MAP, _MCP_TOOL_SCHEMAS
    with _MCP_TOOL_LOCK:
        _MCP_TOOL_MAP = {}
        _MCP_TOOL_SCHEMAS = []


def get_all_tools() -> Tuple[Dict[str, Callable], List[dict]]:
    """Return combined tool map and schemas (built-in + MCP)."""
    with _MCP_TOOL_LOCK:
        combined_map = {**_TOOL_MAP, **_MCP_TOOL_MAP}
        combined_schemas = _TOOL_SCHEMAS + _MCP_TOOL_SCHEMAS
    return combined_map, combined_schemas


def reload_tools() -> int:
    """Reload built-in tools from resources/tools.json at runtime."""
    global _TOOL_MAP, _TOOL_SCHEMAS
    _TOOL_MAP, _TOOL_SCHEMAS = _load_tools_config()
    return len(_TOOL_MAP)


def get_available_tools() -> List[dict]:
    """Return list of all available tools with metadata (for GET /api/v1/tools)."""
    result = []
    for schema in _TOOL_SCHEMAS:
        func = schema.get("function", {})
        result.append({
            "name": func.get("name"),
            "description": func.get("description"),
            "enabled": func.get("name") in _TOOL_MAP,
            "source": "builtin",
        })
    for schema in _MCP_TOOL_SCHEMAS:
        func = schema.get("function", {})
        result.append({
            "name": func.get("name"),
            "description": func.get("description"),
            "enabled": func.get("name") in _MCP_TOOL_MAP,
            "source": "mcp",
        })
    return result


class AlertActionAgent:
    """
    Dispatches actions when an alert fires.

    Operates in one of two modes selected at startup:

    ADK mode (AGENT_MODE=true, default)
        Uses Google ADK with a LlmAgent that receives structured alert context
        and calls FunctionTool-wrapped async tool functions.  LLM served via
        OVMS (LLM_URL) using an OpenAI-compatible API endpoint.

    Rule-based mode (AGENT_MODE=false)
        Directly executes the tool list from AlertConfig.tools in order.
        No external LLM required — works fully offline / air-gapped.
    """

    def __init__(self, use_adk: Optional[bool] = None):
        self._use_adk = use_adk if use_adk is not None else settings.AGENT_MODE
        self._adk_runner = None
        self._session_service = None
        self._known_sessions: set = set()
        self._stream_call_counts: Dict[str, int] = {}
        self._stream_last_seen: Dict[str, float] = {}  # source_id → monotonic timestamp
        self._max_session_calls: int = 5
        self._max_tracked_sources: int = 500  # cap to prevent unbounded growth
        self._source_ttl_seconds: float = 600.0  # evict sources idle for 10 minutes

        if self._use_adk:
            self._init_adk()
        else:
            logger.info("AlertActionAgent initialised in rule-based mode")

    def _init_adk(self, preserve_sessions: bool = False):
        """Initialise the Google ADK runner backed by local OVMS via LiteLLM."""
        try:
            from google.adk.agents import LlmAgent
            from google.adk.tools import FunctionTool
            from src.agentic.adk_common import create_adk_model, create_runner

            if not settings.LLM_URL:
                logger.warning(
                    "AGENT_MODE=true but LLM_URL is not set — "
                    "falling back to rule-based mode"
                )
                self._use_adk = False
                return

            adk_model = create_adk_model()
            logger.info(
                f"ADK using local OVMS (url={settings.LLM_URL} "
                f"model={settings.LLM_MODEL})"
            )

            all_tools, _ = get_all_tools()
            tool_names = ", ".join(all_tools.keys()) or "none loaded"

            instruction = (
                "You are an alert action agent that dispatches notifications and actions "
                "for triggered alerts from multimodal sources (cameras, microphones, sensors, etc.).\n\n"
                f"AVAILABLE TOOLS: {tool_names}\n\n"
                "RULES:\n"
                "1. ALWAYS invoke log_alert.\n"
                "2. Invoke the tools from configured_tools that fit the alert context.\n"
                "3. If escalated=true, invoke more tools (webhook, mqtt).\n"
                "4. Use MCP tools (mcp_ prefix) when they can enrich the response.\n"
                "Return a one-line summary of actions taken."
            )

            adk_tools = [FunctionTool(fn) for fn in all_tools.values()]

            agent = LlmAgent(
                name="alert_action_agent",
                model=adk_model,
                description="Processes alert detections and dispatches configured actions",
                instruction=instruction,
                tools=adk_tools,
            )

            reuse_svc = self._session_service if preserve_sessions else None
            self._adk_runner, self._session_service = create_runner(
                agent, "alert-agent-service", session_service=reuse_svc,
            )
            if not preserve_sessions:
                self._known_sessions.clear()

            logger.info(
                f"AlertActionAgent initialised with ADK (model=local:{settings.LLM_MODEL})"
            )

        except ImportError as exc:
            logger.warning(
                f"google-adk not installed or import failed ({exc}) — "
                "falling back to rule-based mode"
            )
            self._use_adk = False
        except Exception as exc:
            logger.error(f"ADK init error: {exc} — falling back to rule-based mode")
            self._use_adk = False

    def reinit_adk(self):
        """Re-initialise the ADK runner with the current tool set (after MCP refresh)."""
        if not self._use_adk:
            return
        logger.info("Re-initialising ADK agent with updated tool set ...")
        self._init_adk(preserve_sessions=True)

    def clear_sessions_for_sources(self, source_ids: set) -> None:
        """Drop ADK session state for the given source IDs."""
        for source_id in source_ids:
            session_id = f"source_{source_id}".replace(" ", "_")
            self._known_sessions.discard(session_id)
            self._stream_call_counts.pop(source_id, None)
            self._stream_last_seen.pop(source_id, None)
        if source_ids:
            logger.debug(f"Cleared ADK sessions for sources: {source_ids}")

    def _evict_stale_sources(self) -> None:
        """Remove source entries that have been idle beyond the TTL or exceed max size."""
        now = time.monotonic()
        # TTL-based eviction
        stale = [
            sid for sid, ts in self._stream_last_seen.items()
            if (now - ts) > self._source_ttl_seconds
        ]
        for sid in stale:
            self._stream_call_counts.pop(sid, None)
            self._stream_last_seen.pop(sid, None)
            session_id = f"source_{sid}".replace(" ", "_")
            self._known_sessions.discard(session_id)

        # Max-size eviction: remove oldest entries if still over the cap
        if len(self._stream_call_counts) > self._max_tracked_sources:
            sorted_sources = sorted(
                self._stream_last_seen.items(), key=lambda x: x[1]
            )
            to_remove = len(self._stream_call_counts) - self._max_tracked_sources
            for sid, _ in sorted_sources[:to_remove]:
                self._stream_call_counts.pop(sid, None)
                self._stream_last_seen.pop(sid, None)
                session_id = f"source_{sid}".replace(" ", "_")
                self._known_sessions.discard(session_id)

        if stale:
            logger.debug(f"Evicted {len(stale)} stale source entries")

    async def dispatch(
        self,
        source_id: str,
        alert_cfg: AlertConfig,
        answer: str,
        reason: str,
        consecutive_count: int = 1,
        escalated: bool = False,
        snapshot_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        original_payload: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Execute actions for a triggered alert.

        Returns a list of tool names that were successfully invoked.
        Only executes when answer == 'YES'.
        """
        if answer != "YES":
            return []

        if self._use_adk and self._adk_runner:
            logger.info(
                f"[DISPATCH] mode=adk source={source_id} alert={alert_cfg.name} "
                f"escalated={escalated}"
            )
            return await self._dispatch_adk(
                source_id, alert_cfg, answer, reason,
                consecutive_count, escalated, snapshot_path, metadata,
                original_payload,
            )
        else:
            logger.info(
                f"[DISPATCH] mode=rule_based source={source_id} alert={alert_cfg.name} "
                f"escalated={escalated}"
            )
            return await self._dispatch_rule_based(
                source_id, alert_cfg, answer, reason,
                consecutive_count, escalated, snapshot_path, metadata,
                original_payload,
            )

    async def _dispatch_rule_based(
        self,
        source_id: str,
        alert_cfg: AlertConfig,
        answer: str,
        reason: str,
        consecutive_count: int,
        escalated: bool,
        snapshot_path: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
        original_payload: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Directly invoke tools listed in alert_cfg.tools without an LLM step."""
        tool_names: List[str] = list(alert_cfg.tools)
        if "log_alert" not in tool_names:
            tool_names.insert(0, "log_alert")
        if escalated and alert_cfg.escalation:
            for t in alert_cfg.escalation.additional_tools:
                if t not in tool_names:
                    tool_names.append(t)
        return await self._execute_tool_list(
            tool_names, source_id, alert_cfg, answer, reason,
            consecutive_count, escalated, snapshot_path, metadata,
            original_payload,
        )

    async def _execute_tool_list(
        self,
        tool_names: List[str],
        source_id: str,
        alert_cfg: AlertConfig,
        answer: str,
        reason: str,
        consecutive_count: int,
        escalated: bool,
        snapshot_path: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
        original_payload: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Execute a specific list of tools, building all kwargs automatically.
        Shared by rule-based and ADK fallback dispatch modes.
        """
        names = list(tool_names)
        if "log_alert" not in names:
            names.insert(0, "log_alert")

        common_ctx = {
            "source_id": source_id,
            "alert_name": alert_cfg.name,
            "answer": answer,
            "reason": reason,
            "consecutive_count": consecutive_count,
            "escalated": escalated,
            "snapshot_path": snapshot_path,
            "metadata": metadata or {},
            "original_payload": original_payload or {},
        }

        all_tools, _ = get_all_tools()

        prepared: List[Tuple[str, Callable, dict]] = []
        for tool_name in names:
            fn = all_tools.get(tool_name)
            if fn is None:
                logger.warning(f"Unknown tool '{tool_name}' — skipped")
                continue
            try:
                if tool_name.startswith("mcp_"):
                    configured_args = alert_cfg.tool_arguments.get(tool_name, {})
                    if configured_args:
                        kwargs = _render_tool_arguments(configured_args, common_ctx)
                    else:
                        kwargs = _render_tool_arguments(
                            get_tool_defaults(tool_name), common_ctx,
                        )
                else:
                    kwargs = _build_tool_kwargs(
                        tool_name, common_ctx, consecutive_count, escalated, snapshot_path,
                    )
                    override_args = _render_tool_arguments(
                        alert_cfg.tool_arguments.get(tool_name, {}),
                        common_ctx,
                    )
                    if override_args:
                        kwargs.update(override_args)
                prepared.append((tool_name, fn, kwargs))
            except Exception as exc:
                logger.error(f"Failed to prepare tool '{tool_name}': {exc}")

        async def _run_one(name: str, fn: Callable, kwargs: dict) -> Tuple[str, bool]:
            for attempt in range(1, settings.RETRY_ATTEMPTS + 1):
                try:
                    result = await asyncio.wait_for(fn(**kwargs), timeout=_TOOL_TIMEOUT)
                    logger.debug(f"Tool '{name}' result: {result}")
                    return name, result.get("status") != "error"
                except asyncio.TimeoutError:
                    logger.error(f"Tool '{name}' timed out after {_TOOL_TIMEOUT}s (attempt {attempt}/{settings.RETRY_ATTEMPTS})")
                    return name, False
                except Exception as exc:
                    logger.warning(f"Tool '{name}' attempt {attempt}/{settings.RETRY_ATTEMPTS} failed: {exc}")
                    if attempt < settings.RETRY_ATTEMPTS:
                        await asyncio.sleep(settings.RETRY_INTERVAL_SECONDS)
            logger.error(f"Tool '{name}' exhausted all retries")
            return name, False

        results = await asyncio.gather(
            *[_run_one(n, f, k) for n, f, k in prepared]
        )
        return [name for name, ok in results if ok]

    async def _dispatch_adk(
        self,
        source_id: str,
        alert_cfg: AlertConfig,
        answer: str,
        reason: str,
        consecutive_count: int,
        escalated: bool,
        snapshot_path: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
        original_payload: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Feed alert context into the ADK agent and let it decide tool calls."""
        from src.agentic.adk_common import run_agent_prompt

        try:
            session_id = f"source_{source_id}".replace(" ", "_")
            count = self._stream_call_counts.get(source_id, 0) + 1
            self._stream_call_counts[source_id] = count
            self._stream_last_seen[source_id] = time.monotonic()

            # Evict stale entries to prevent unbounded growth
            self._evict_stale_sources()

            if count > self._max_session_calls and session_id in self._known_sessions:
                try:
                    await self._session_service.delete_session(
                        app_name="alert-agent-service",
                        user_id="system",
                        session_id=session_id,
                    )
                except Exception:
                    pass
                self._known_sessions.discard(session_id)
                self._stream_call_counts[source_id] = 1
                logger.debug(f"Reset ADK session for source '{source_id}'")

            logger.info(
                f"[ADK] Sending to ADK agent — source={source_id} "
                f"alert={alert_cfg.name} model={settings.LLM_MODEL} "
                f"session={session_id}"
            )

            prompt = (
                f"Alert detection result:\n"
                f"  source_id: {source_id}\n"
                f"  alert_name: {alert_cfg.name}\n"
                f"  answer: {answer}\n"
                f"  reason: {reason}\n"
                f"  consecutive_count: {consecutive_count}\n"
                f"  escalated: {escalated}\n"
                f"  snapshot_path: {snapshot_path or 'none'}\n"
                f"  configured_tools: {alert_cfg.tools}\n"
                f"\nPlease handle this alert appropriately."
            )

            text_response, invoked_tools = await run_agent_prompt(
                runner=self._adk_runner,
                session_service=self._session_service,
                session_id=session_id,
                prompt=prompt,
                timeout=settings.LLM_TIMEOUT,
                known_sessions=self._known_sessions,
            )

            if invoked_tools:
                logger.info(
                    f"ADK agent invoked tools for [{source_id}][{alert_cfg.name}]: "
                    f"{invoked_tools}"
                )
                return invoked_tools

            # ADK returned text only — fall back to configured tools
            all_tools, _ = get_all_tools()
            tool_names = list(alert_cfg.tools)
            if text_response:
                for name in all_tools:
                    if name not in tool_names and name in text_response:
                        tool_names.append(name)
            if escalated and alert_cfg.escalation:
                for t in alert_cfg.escalation.additional_tools:
                    if t not in tool_names:
                        tool_names.append(t)

            logger.info(
                f"ADK model returned no tool_calls for [{source_id}][{alert_cfg.name}] "
                f"— executing configured tools: {tool_names}"
            )
            return await self._execute_tool_list(
                tool_names, source_id, alert_cfg, answer, reason,
                consecutive_count, escalated, snapshot_path, metadata,
                original_payload,
            )

        except asyncio.TimeoutError:
            logger.error(
                f"ADK dispatch timed out after {settings.LLM_TIMEOUT}s "
                f"for [{source_id}][{alert_cfg.name}] — falling back to rule-based"
            )
            return await self._dispatch_rule_based(
                source_id, alert_cfg, answer, reason,
                consecutive_count, escalated, snapshot_path, metadata,
                original_payload,
            )
        except Exception as exc:
            logger.error(
                f"ADK dispatch failed for [{source_id}][{alert_cfg.name}]: "
                f"{type(exc).__name__}: {exc} — falling back to rule-based"
            )
            return await self._dispatch_rule_based(
                source_id, alert_cfg, answer, reason,
                consecutive_count, escalated, snapshot_path, metadata,
                original_payload,
            )


def _build_tool_kwargs(
    tool_name: str,
    ctx: Dict[str, Any],
    consecutive_count: int,
    escalated: bool,
    snapshot_path: Optional[str],
) -> Dict[str, Any]:
    """Map common alert context fields to per-tool keyword arguments."""
    base = {
        "source_id": ctx["source_id"],
        "alert_name": ctx["alert_name"],
    }
    if tool_name == "log_alert":
        return {
            **base,
            "answer": ctx["answer"],
            "reason": ctx["reason"],
            "consecutive_count": consecutive_count,
            "escalated": escalated,
            "snapshot_path": snapshot_path,
        }
    if tool_name == "trigger_webhook":
        return {
            "payload": {
                **ctx,
                "consecutive_count": consecutive_count,
                "escalated": escalated,
                "snapshot_path": snapshot_path,
            }
        }
    if tool_name == "capture_snapshot":
        return base
    if tool_name == "publish_mqtt":
        return {
            **base,
            "answer": ctx["answer"],
            "reason": ctx["reason"],
            "metadata": ctx.get("metadata"),
            "payload": ctx.get("original_payload") or None,
            "timestamp": (ctx.get("metadata") or {}).get("_original_timestamp"),
        }
    return {}


def _render_tool_arguments(value: Any, ctx: Dict[str, Any]) -> Any:
    """Render {{variable}} template placeholders in tool arguments."""
    if isinstance(value, str):
        return _CONTEXT_TEMPLATE_PATTERN.sub(
            lambda m: "" if ctx.get(m.group(1)) is None else str(ctx.get(m.group(1))),
            value,
        )
    if isinstance(value, list):
        return [_render_tool_arguments(item, ctx) for item in value]
    if isinstance(value, dict):
        return {k: _render_tool_arguments(v, ctx) for k, v in value.items()}
    return value
