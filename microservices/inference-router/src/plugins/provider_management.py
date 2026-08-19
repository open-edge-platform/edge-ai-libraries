# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Provider management plugin: drive a Local Provider Manager from the router.

A provider that can be started/stopped by an external Local Provider Manager
(see ``agentic-sdk/third_party/provider_manager``) declares the manager URL in
its generic ``extra`` mapping::

    - name: "qwen3-local"
      type: "hosted_vllm"
      model: "Qwen/Qwen3.5-4B"
      enabled: false
      extra:
        management_endpoint: "http://localhost:9900/providers"

Callers then POST a tool-schema payload to ``/v1/providers/{name}/manage``; the
body is forwarded **verbatim** (the router does not build or validate the tool
schema — the caller owns it). What the router *does* own is reacting to the
result: on a successful ``start`` the provider is registered into the running
config (enabled, with ``settings.endpoint`` / ``model`` / ``type`` taken from
the manager's ``router_provider`` block); on a successful ``stop`` it is
un-registered by flipping ``enabled`` to ``false`` (the entry — and its
``extra`` — is kept so it can be restarted later).
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, Optional, Type

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.v1._config_runtime import (
    load_raw_document,
    persist_raw_providers,
    resolve_config_path,
)
from src.models import ChatCompletionRequest
from src.plugins.base import PluginBaseNode
from src.plugins.manager import register_plugin
from src.router.logging_utils import sanitize_for_log

logger = logging.getLogger(__name__)

# The manager blocks on backend readiness during ``start`` (first-time model
# downloads can take minutes), so allow a generous request timeout. Per provider,
# override via ``extra.management_timeout`` (seconds) — raise it for slow cold
# starts, or lower it to fail faster.
_DEFAULT_MANAGE_TIMEOUT = 1200.0


def _manage_timeout(provider) -> float:
    """Resolve the forward timeout for this provider, defaulting sanely."""
    raw = provider.extra.get("management_timeout", _DEFAULT_MANAGE_TIMEOUT)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MANAGE_TIMEOUT
    return value if value > 0 else _DEFAULT_MANAGE_TIMEOUT


class ProviderManagementSettings(BaseModel):
    """The manage route requires no plugin-instance settings."""


def _find_provider(http_request: Request, name: str):
    """Return the live provider config named ``name`` or raise 404/503."""
    config = getattr(http_request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Router not initialized")
    provider = next((p for p in config.providers if p.name == name), None)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    return provider


def _register_from_start(entry: dict, router_provider: dict) -> list[str]:
    """Overlay a manager ``router_provider`` block onto a raw provider entry.

    Refreshes the fields the manager decided at launch (``type`` / ``model`` /
    ``settings.endpoint``) and enables the provider, while preserving everything
    the operator configured locally — notably ``extra`` (so it stays manageable)
    and ``metadata`` (routing labels/cost/capability).

    Returns the names of the correctness-critical fields that could **not** be
    reconciled from the response (empty when everything was refreshed). A
    management tool that omits ``router_provider`` leaves the entry advertising
    its declared ``model``/``endpoint``, which may not match what actually
    started — the caller surfaces this as a warning.
    """
    entry["enabled"] = True
    if router_provider.get("type"):
        entry["type"] = router_provider["type"]

    unreconciled: list[str] = []
    if router_provider.get("model"):
        entry["model"] = router_provider["model"]
    else:
        unreconciled.append("model")

    upstream_settings = router_provider.get("settings") or {}
    endpoint = upstream_settings.get("endpoint")
    if endpoint:
        settings = dict(entry.get("settings") or {})
        settings["endpoint"] = endpoint
        entry["settings"] = settings
    else:
        unreconciled.append("settings.endpoint")
    return unreconciled


async def _apply_reaction(
    http_request: Request, name: str, command: str, upstream_json: Any
) -> Optional[str]:
    """Register (start) or un-register (stop) the provider after a 2xx result.

    Mutates the raw providers document and swaps in the rebuilt runtime under the
    app config lock. Raises on failure; the caller decides how to surface it.
    Returns a warning message when a ``start`` succeeded but the response didn't
    let us fully reconcile the entry (so config may not match the running
    backend); otherwise ``None``.
    """
    warning: Optional[str] = None
    async with http_request.app.state.config_lock:
        config_path = resolve_config_path(http_request)
        document = load_raw_document(config_path)
        raw_providers = document.get("providers")
        if not isinstance(raw_providers, list):
            # No usable on-disk providers section (first write / corrupt file):
            # fall back to the resolved in-memory providers so the rebuild has a
            # complete list to persist.
            config = http_request.app.state.config
            raw_providers = [
                {
                    "name": p.name,
                    "type": p.type,
                    "model": p.model,
                    "enabled": p.enabled,
                    "metadata": copy.deepcopy(p.metadata),
                    "settings": copy.deepcopy(p.settings),
                    "extra": copy.deepcopy(p.extra),
                }
                for p in config.providers
            ]
        else:
            raw_providers = copy.deepcopy(raw_providers)

        entry = next((p for p in raw_providers if p.get("name") == name), None)
        if entry is None:
            raise RuntimeError(f"Provider '{name}' vanished from config before registration")

        if command == "start":
            router_provider = {}
            if isinstance(upstream_json, dict):
                router_provider = upstream_json.get("router_provider") or {}
            unreconciled = _register_from_start(entry, router_provider)
            if unreconciled:
                warning = (
                    f"manager returned no {', '.join(unreconciled)} for '{name}'; the "
                    "router enabled it but its config may not match the running backend"
                )
        else:  # stop
            entry["enabled"] = False

        await persist_raw_providers(http_request, raw_providers)
    return warning


@register_plugin
class ProviderManagementPlugin(PluginBaseNode):
    """Forwards lifecycle commands to a provider's manager and syncs router state."""

    @classmethod
    def plugin_type(cls) -> str:
        return "provider_management"

    @classmethod
    def settings_model(cls) -> Type[BaseModel]:
        return ProviderManagementSettings

    @classmethod
    def routes(cls) -> APIRouter:
        router = APIRouter()

        @router.post("/providers/{name}/manage")
        async def manage_provider(name: str, http_request: Request) -> JSONResponse:
            provider = _find_provider(http_request, name)

            endpoint = provider.extra.get("management_endpoint")
            if not isinstance(endpoint, str) or not endpoint.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"Provider '{name}' extra.management_endpoint is not configured",
                )

            body = await http_request.body()

            # Best-effort: learn the command (so we know how to react) and the
            # payload's own ``name``. A body we cannot parse is still forwarded —
            # we just skip both the name guard and the reaction.
            command: Optional[str] = None
            payload_name: Any = None
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    command = parsed.get("command")
                    payload_name = parsed.get("name")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

            # The manager keys its container on the payload ``name``, while the
            # router keys this provider on the URL segment. If they diverge,
            # start/stop desync the router entry from the actual container (e.g.
            # a stop disables the entry while the container keeps running), so
            # reject rather than allow that.
            if isinstance(payload_name, str) and payload_name and payload_name != name:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"payload 'name' ({payload_name!r}) must match the provider named "
                        f"in the URL ({name!r})"
                    ),
                )

            content_type = http_request.headers.get("content-type", "application/json")
            try:
                async with httpx.AsyncClient(timeout=_manage_timeout(provider)) as client:
                    upstream = await client.post(
                        endpoint, content=body, headers={"content-type": content_type}
                    )
            except httpx.TimeoutException as exc:
                raise HTTPException(
                    status_code=504,
                    detail=f"Provider manager timed out for '{name}': {exc}",
                ) from exc
            except httpx.RequestError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to reach provider manager for '{name}': {exc}",
                ) from exc

            try:
                upstream_json = upstream.json()
            except ValueError:
                # Manager should return JSON; if it didn't, pass the text back
                # rather than 500, and never attempt a reaction on it.
                return JSONResponse(
                    content={"detail": upstream.text},
                    status_code=upstream.status_code,
                )

            # Only mutate router state when the manager reports success for a
            # lifecycle command; list/status and failures leave config untouched.
            if 200 <= upstream.status_code < 300 and command in ("start", "stop"):
                try:
                    warning = await _apply_reaction(http_request, name, command, upstream_json)
                    if warning:
                        logger.warning(
                            "Provider '%s' %s: %s",
                            sanitize_for_log(name), sanitize_for_log(command), warning,
                        )
                        if isinstance(upstream_json, dict):
                            upstream_json = {
                                **upstream_json,
                                "router_registration": {"ok": True, "warning": warning},
                            }
                except HTTPException as exc:
                    # e.g. rebuilding with zero enabled providers (stopping the
                    # last one). The manager already changed state, so surface a
                    # warning instead of failing the whole call.
                    logger.warning(
                        "Provider '%s' %s succeeded but router registration failed: %s",
                        sanitize_for_log(name), sanitize_for_log(command), exc.detail,
                    )
                    if isinstance(upstream_json, dict):
                        upstream_json = {
                            **upstream_json,
                            "router_registration": {"ok": False, "error": str(exc.detail)},
                        }
                except Exception as exc:
                    logger.warning(
                        "Provider '%s' %s succeeded but router registration failed: %s",
                        sanitize_for_log(name), sanitize_for_log(command), exc,
                    )
                    if isinstance(upstream_json, dict):
                        # Don't surface the raw exception text (stack-trace-derived
                        # internals) to the caller — it's logged above. CWE-209.
                        upstream_json = {
                            **upstream_json,
                            "router_registration": {
                                "ok": False,
                                "error": "internal error during router registration",
                            },
                        }

            return JSONResponse(content=upstream_json, status_code=upstream.status_code)

        return router

    async def process_request(
        self, request: ChatCompletionRequest, **kwargs: Any
    ) -> ChatCompletionRequest:
        return request
