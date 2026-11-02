# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Provider management plugin: drive a Local Provider Manager from the router.

The router talks to a single external **Local Provider Manager** service that
starts/stops local serving containers and exposes an HTTP API (``POST
/providers`` to start, ``DELETE /providers/{name}`` to stop). The manager's base
URL is a plugin-instance setting::

    plugins:
      standalone:                                  # non-hook stage: routes only,
        - name: "provmgr"                          # never run in a request chain
          node: "provider_management"
          settings:
            manager_url: "http://localhost:9900"   # base URL of the manager
            # timeout: 1200   # optional; seconds, for slow cold starts

The plugin controls the provider **services** (containers) only. It never
changes the router config (``config.yaml``): whether the router routes to a
backend is governed by its provider entry, which the user manages through the
providers API (``POST /v1/providers/{name}`` — e.g. ``{"enabled": true}`` once
the service is up — and ``DELETE /v1/providers/{name}``).

To start a service, POST the manager's ``StartProviderRequest`` (docker params:
``name`` / ``image`` / ``command`` / ``volumes`` / ``docker_args`` / …) to
``/v1/providers/manage``. ``name`` travels in the body (the manager keys the
container on it), so it is not repeated in the path. The plugin forwards the
docker params to ``POST {manager_url}/providers`` (the manager just runs ``docker
run -d`` and records the result) and returns the manager's response.

The manager does not wait for the service to come up. Pass ``health_endpoint``
(a URL reachable from the router, e.g. ``http://localhost:24680/health``) and the
plugin polls it until it answers 2xx before responding; if the container stops
first, or ``management_timeout`` elapses, the container is removed through the
manager and an error is returned.

To stop a service, ``DELETE /v1/providers/manage?name=<name>``; the plugin
forwards ``DELETE {manager_url}/providers/{name}``.

To inspect what is actually running, ``GET /v1/providers/manage`` proxies the
manager's ``GET /providers`` (all started backends) — or ``?name=<name>`` for a
single one. This is the manager's *live* view (recorded ``docker run`` result and
container state), distinct from ``GET /v1/providers`` which reports the router's
provider config.

To hot-swap LoRA adapters on a running vLLM backend, ``POST
/v1/providers/manage/load_lora_adapter`` / ``.../unload_lora_adapter`` with the
vLLM body (``lora_name`` / ``lora_path``) plus ``provider`` (a provider name in
the router config). These bypass the manager: the plugin strips ``provider`` and
forwards the rest to ``{endpoint}/v1/load_lora_adapter`` (resp. ``unload``) on
that provider's ``settings.endpoint``, applying its configured auth. The vLLM
server must run with ``VLLM_ALLOW_RUNTIME_LORA_UPDATING=True``. Router config is
not changed.

Per request the manager URL / timeout can be overridden with ``manager_url`` /
``management_timeout`` in the start body. These and ``health_endpoint`` are
stripped before the request is forwarded to the manager.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional, Type

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config.loader import validate_name
from src.models import ChatCompletionRequest
from src.plugins.base import PluginBaseNode
from src.plugins.manager import register_plugin
from src.router.logging_utils import sanitize_for_log

logger = logging.getLogger(__name__)

# Bounds both the manager's ``docker run`` (an image pull can take minutes) and
# the readiness wait on ``health_endpoint`` (first-time kernel compiles can too).
# Overridable via the plugin ``timeout`` setting or a per-request
# ``management_timeout`` in the start body.
_DEFAULT_MANAGE_TIMEOUT = 1200.0

# Reads (list/status) are quick queries at the manager, so they use a short fixed
# timeout rather than the generous start timeout.
_READ_TIMEOUT = 30.0

# Readiness wait: poll interval, per-probe timeout, and the manager-reported
# container states that mean "still coming up" (anything else = it stopped).
_READY_POLL_INTERVAL = 2.0
_PROBE_TIMEOUT = 5.0
_LIVE_STATES = ("running", "created", "restarting")

# Our own fields in the start body — consumed by the plugin and stripped before
# the request is forwarded to the manager (which only wants docker params).
_CONTROL_FIELDS = ("manager_url", "management_timeout", "health_endpoint")

# Runtime LoRA load/unload is a vLLM-only API (``/v1/{load,unload}_lora_adapter``),
# so it is only offered for providers registered under the vLLM router type.
_LORA_PROVIDER_TYPES = ("hosted_vllm",)


class ProviderManagementSettings(BaseModel):
    """Settings for one provider-management plugin instance.

    ``manager_url`` is the base URL of the Local Provider Manager this instance
    drives (e.g. ``http://localhost:9900``); it can be overridden per request.
    ``timeout`` is the default forward timeout (seconds) for manager calls.
    """

    manager_url: Optional[str] = None
    timeout: float = _DEFAULT_MANAGE_TIMEOUT


def _normalize_manager_base(url: str) -> str:
    """Reduce a manager URL to its bare base (scheme://host:port).

    Accepts the base itself (``http://host:9900``), a trailing slash, or a URL
    that already points at the ``/providers`` collection, so operators can be
    loose about which form they configure.
    """
    base = url.strip().rstrip("/")
    if base.endswith("/providers"):
        base = base[: -len("/providers")]
    return base


def _plugin_setting(http_request: Request, attr: str) -> Any:
    """Read ``attr`` off the first configured provider_management instance.

    Route handlers are class-level and have no ``self``; the live instance (and
    thus its validated settings) is looked up from the plugin manager. Returns
    ``None`` when no instance is configured or the manager is unavailable.
    """
    manager = getattr(http_request.app.state, "plugin_manager", None)
    if manager is None:
        return None
    for plugin in getattr(manager, "plugins", []):
        if plugin.plugin_type() == ProviderManagementPlugin.plugin_type():
            return getattr(plugin.parsed_settings, attr, None)
    return None


def _resolve_manager_base(http_request: Request, override: Optional[str]) -> str:
    """Pick the manager base URL: request override first, else the setting."""
    candidate = override or _plugin_setting(http_request, "manager_url")
    if not isinstance(candidate, str) or not candidate.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "No provider manager URL: set 'manager_url' in the "
                "provider_management plugin settings or pass it in the request body"
            ),
        )
    return _normalize_manager_base(candidate)


def _resolve_timeout(http_request: Request, override: Any) -> float:
    """Resolve the forward timeout: request override, else setting, else default."""
    for candidate in (override, _plugin_setting(http_request, "timeout")):
        if candidate is None:
            continue
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return _DEFAULT_MANAGE_TIMEOUT


def _find_provider(http_request: Request, name: str):
    """Return the live provider config named ``name`` or raise 404/503."""
    config = getattr(http_request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Router not initialized")
    provider = next((p for p in config.providers if p.name == name), None)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    return provider


async def _await_ready(
    manager_base: str, name: str, health_url: str, timeout: float
) -> Optional[tuple[int, str]]:
    """Poll ``health_url`` until it answers 2xx.

    Between probes the manager's record is checked so a container that stopped
    (``exited``, or ``missing`` when run with ``--rm``) fails fast. Returns
    ``None`` once ready, else ``(http_status, reason)``: 502 if the container
    stopped, 504 if ``timeout`` elapsed.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
        while True:
            try:
                probe = await client.request("GET", health_url)
                if 200 <= probe.status_code < 300:
                    return None
            except httpx.HTTPError:
                pass  # not listening yet

            state = None
            try:
                record = await client.request("GET", f"{manager_base}/providers/{name}")
                if record.status_code == 200:
                    state = record.json().get("state")
            except (httpx.HTTPError, ValueError, AttributeError):
                pass  # manager hiccup: keep probing until the deadline
            if state and state not in _LIVE_STATES:
                return 502, f"container is '{state}' before {health_url} became ready"

            if loop.time() >= deadline:
                return 504, f"{health_url} did not become ready within {timeout:g}s"
            await asyncio.sleep(_READY_POLL_INTERVAL)


def _parse_start_body(body: bytes) -> dict:
    """Parse and validate the start request body into a docker-params dict."""
    if not body:
        return {}
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Start body must be a JSON object")
    return payload


async def _forward(
    method: str,
    url: str,
    timeout: float,
    *,
    target: str = "provider manager",
    **kwargs: Any,
) -> httpx.Response:
    """Forward a request to ``target`` (the manager by default), mapping transport errors."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(method, url, **kwargs)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail=f"{target.capitalize()} timed out: {exc}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach {target}: {exc}") from exc


def _vllm_base(endpoint: str) -> str:
    """Reduce a provider's OpenAI-compatible endpoint to the vLLM server root.

    Registered endpoints usually carry the ``/v1`` suffix
    (``http://host:8000/v1``); the LoRA routes live at ``/v1/...`` on the root.
    """
    base = endpoint.strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base


def _provider_auth_headers(settings: dict) -> dict:
    """Build request headers from a provider's ``settings.auth`` block.

    Mirrors LitellmProvider: scheme in {"bearer" (default), "api_key", "none"},
    with ``custom_headers`` always merged in (and winning).
    """
    auth = settings.get("auth") or {}
    scheme = (auth.get("scheme") or "bearer").lower()
    api_key = None if scheme == "none" else auth.get("api_key")
    headers: dict = {}
    if api_key:
        if scheme == "bearer":
            headers["authorization"] = f"Bearer {api_key}"
        elif scheme == "api_key":
            headers["api-key"] = api_key
    headers.update(auth.get("custom_headers") or {})
    return headers


async def _forward_lora(http_request: Request, action: str) -> JSONResponse:
    """Forward a LoRA load/unload request to a registered vLLM provider.

    The body is vLLM's (``lora_name`` / ``lora_path``) plus our ``provider``
    field naming the target, which is stripped before forwarding. vLLM answers a
    success with a plain-text message, so a 2xx is wrapped into a JSON body; an
    error is passed through with vLLM's status.
    """
    payload = _parse_start_body(await http_request.body())
    provider_name = payload.pop("provider", None)
    if not isinstance(provider_name, str) or not provider_name:
        raise HTTPException(
            status_code=400, detail=f"{action} request must include 'provider'"
        )
    lora_name = payload.get("lora_name")
    if not isinstance(lora_name, str) or not lora_name:
        raise HTTPException(
            status_code=400, detail=f"{action} request must include 'lora_name'"
        )
    if action == "load_lora_adapter" and not payload.get("lora_path"):
        raise HTTPException(
            status_code=400, detail="load_lora_adapter request must include 'lora_path'"
        )

    provider = _find_provider(http_request, provider_name)
    if provider.type not in _LORA_PROVIDER_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Provider '{provider_name}' has type '{provider.type}'; runtime LoRA "
                f"adapters are only supported on {', '.join(_LORA_PROVIDER_TYPES)} providers"
            ),
        )
    settings = provider.settings or {}
    endpoint = settings.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise HTTPException(
            status_code=503,
            detail=f"Provider '{provider_name}' has no endpoint configured",
        )

    upstream = await _forward(
        "POST",
        f"{_vllm_base(endpoint)}/v1/{action}",
        _resolve_timeout(http_request, None),
        target="vLLM backend",
        json=payload,
        headers=_provider_auth_headers(settings),
    )
    if not (200 <= upstream.status_code < 300):
        return JSONResponse(
            content=_response_json(upstream), status_code=upstream.status_code
        )
    logger.info(
        "Provider '%s' %s '%s'",
        sanitize_for_log(provider_name), action, sanitize_for_log(lora_name),
    )
    return JSONResponse(
        content={
            "provider": provider_name,
            "lora_name": lora_name,
            "message": upstream.text,
        },
        status_code=upstream.status_code,
    )


def _response_json(upstream: httpx.Response) -> Any:
    """Best-effort JSON parse of a manager response, else its text under ``detail``."""
    try:
        return upstream.json()
    except ValueError:
        return {"detail": upstream.text}


def _passthrough(upstream: httpx.Response) -> JSONResponse:
    """Return the manager's response body and status code as-is."""
    return JSONResponse(content=_response_json(upstream), status_code=upstream.status_code)


def _validate_service_name(name: str) -> None:
    """400 unless ``name`` is a safe name (it is interpolated into manager URLs)."""
    try:
        validate_name(name, "Provider")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _parse_start_body(body: bytes) -> dict:
    """Parse and validate the start request body into a docker-params dict."""
    if not body:
        return {}
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Start body must be a JSON object")
    return payload


async def _forward(method: str, url: str, timeout: float, **kwargs: Any) -> httpx.Response:
    """Forward a request to the provider manager, mapping transport errors."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(method, url, **kwargs)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail=f"Provider manager timed out: {exc}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach provider manager: {exc}") from exc


def _response_json(upstream: httpx.Response) -> Any:
    """Best-effort JSON parse of a manager response, else its text under ``detail``."""
    try:
        return upstream.json()
    except ValueError:
        return {"detail": upstream.text}


async def _react_and_respond(
    http_request: Request,
    name: str,
    lifecycle: str,
    upstream: httpx.Response,
    **reaction_kwargs: Any,
) -> JSONResponse:
    """Apply the router-state reaction for a 2xx manager result, then respond.

    A registration failure never fails the whole call — the manager already
    changed container state, so it is surfaced as a ``router_registration`` note
    on the (dict) response body instead.
    """
    upstream_json = _response_json(upstream)
    if not (200 <= upstream.status_code < 300):
        return JSONResponse(content=upstream_json, status_code=upstream.status_code)

    try:
        warning = await _apply_reaction(http_request, name, lifecycle, **reaction_kwargs)
        if warning:
            logger.warning(
                "Provider '%s' %s: %s",
                sanitize_for_log(name), sanitize_for_log(lifecycle), sanitize_for_log(warning),
            )
            if isinstance(upstream_json, dict):
                upstream_json = {
                    **upstream_json,
                    "router_registration": {"ok": True, "warning": warning},
                }
    except HTTPException as exc:
        # e.g. rebuilding with zero enabled providers (stopping the last one).
        # The manager already changed state, so surface a warning, don't fail.
        logger.warning(
            "Provider '%s' %s succeeded but router registration failed: %s",
            sanitize_for_log(name), sanitize_for_log(lifecycle), exc.detail,
        )
        if isinstance(upstream_json, dict):
            upstream_json = {
                **upstream_json,
                "router_registration": {"ok": False, "error": str(exc.detail)},
            }
    except Exception as exc:
        logger.warning(
            "Provider '%s' %s succeeded but router registration failed: %s",
            sanitize_for_log(name), sanitize_for_log(lifecycle), exc,
        )
        if isinstance(upstream_json, dict):
            # Don't leak raw exception internals to the caller (CWE-209); it's
            # logged above.
            upstream_json = {
                **upstream_json,
                "router_registration": {
                    "ok": False,
                    "error": "internal error during router registration",
                },
            }

    return JSONResponse(content=upstream_json, status_code=upstream.status_code)


@register_plugin
class ProviderManagementPlugin(PluginBaseNode):
    """Drives a Local Provider Manager: starts/stops/inspects provider services."""

    @classmethod
    def plugin_type(cls) -> str:
        return "provider_management"

    @classmethod
    def settings_model(cls) -> Type[BaseModel]:
        return ProviderManagementSettings

    @classmethod
    def routes(cls) -> APIRouter:
        router = APIRouter()

        @router.post("/providers/manage")
        async def start_provider(http_request: Request) -> JSONResponse:
            # The provider name lives in the body — it is what the manager keys
            # the container on, and it is echoed back in the response, so there
            # is no need to repeat it in the path.
            payload = _parse_start_body(await http_request.body())

            body_name = payload.get("name")
            if not isinstance(body_name, str) or not body_name:
                raise HTTPException(
                    status_code=400, detail="Start request must include 'name'"
                )
            _validate_service_name(body_name)

            # Peel off our control fields so only docker params reach the manager.
            control = {field: payload.pop(field, None) for field in _CONTROL_FIELDS}
            health_endpoint = control["health_endpoint"]
            if health_endpoint is not None and (
                not isinstance(health_endpoint, str) or not health_endpoint.strip()
            ):
                raise HTTPException(
                    status_code=400, detail="'health_endpoint' must be a non-empty string"
                )

            manager_base = _resolve_manager_base(http_request, control["manager_url"])
            timeout = _resolve_timeout(http_request, control["management_timeout"])

            upstream = await _forward(
                "POST", f"{manager_base}/providers", timeout, json=payload
            )
            if 200 <= upstream.status_code < 300 and health_endpoint:
                failure = await _await_ready(manager_base, body_name, health_endpoint, timeout)
                if failure is not None:
                    status_code, reason = failure
                    logger.warning(
                        "Provider '%s' not ready (%s); removing its container",
                        sanitize_for_log(body_name), sanitize_for_log(reason),
                    )
                    try:  # free the name so a retry can start cleanly
                        await _forward(
                            "DELETE", f"{manager_base}/providers/{body_name}", _READ_TIMEOUT
                        )
                    except HTTPException:
                        pass
                    return JSONResponse(
                        content={
                            "detail": f"Provider '{body_name}' not started: {reason}; "
                                      "its container was removed",
                            "provider": _response_json(upstream),
                        },
                        status_code=status_code,
                    )

            return _passthrough(upstream)

        @router.delete("/providers/manage")
        async def stop_provider(name: str, http_request: Request) -> JSONResponse:
            # ``name`` is a query parameter (``?name=...``): keep the path stable
            # at ``/providers/manage`` for both lifecycle verbs.
            _validate_service_name(name)
            manager_base = _resolve_manager_base(http_request, None)
            upstream = await _forward(
                "DELETE", f"{manager_base}/providers/{name}",
                _resolve_timeout(http_request, None),
            )
            return _passthrough(upstream)

        @router.get("/providers/manage")
        async def list_managed_providers(
            http_request: Request, name: Optional[str] = None
        ) -> JSONResponse:
            # Read-only proxy of the manager's *live* view of started backends:
            # ``GET /providers`` (all) or ``GET /providers/{name}`` (one, via the
            # ``?name=`` query). Unlike ``GET /v1/providers`` (the router's config
            # view), this reflects what is actually running at the manager. No
            # config lookup; the manager URL is the plugin setting.
            if name:
                _validate_service_name(name)
            manager_base = _resolve_manager_base(http_request, None)
            path = f"/providers/{name}" if name else "/providers"
            upstream = await _forward("GET", f"{manager_base}{path}", _READ_TIMEOUT)
            return _passthrough(upstream)

        @router.post("/providers/manage/load_lora_adapter")
        async def load_lora_adapter(http_request: Request) -> JSONResponse:
            # Direct to the provider's vLLM server, not the manager.
            return await _forward_lora(http_request, "load_lora_adapter")

        @router.post("/providers/manage/unload_lora_adapter")
        async def unload_lora_adapter(http_request: Request) -> JSONResponse:
            return await _forward_lora(http_request, "unload_lora_adapter")

        return router

    async def process_request(
        self, request: ChatCompletionRequest, **kwargs: Any
    ) -> ChatCompletionRequest:
        return request
