# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""v1 provider management endpoints.

Providers are the set of backends the router can dispatch to (see
``config.example.yaml``). This module exposes list/get/create-update/delete
over them, rebuilding the runtime and persisting to ``config.yaml`` on every
mutation — mirroring the plugin API in :mod:`src.api.v1.plugin`.

Providers are uniquely identified by ``name`` (unlike plugins, which are keyed
by name + node), so paths are ``/providers/{name}``.

Secret handling: a provider's ``settings.auth.api_key`` may be a ``${VAR}``
placeholder. Mutations are applied against the *raw* on-disk document so
placeholders survive on disk (see ``_persist_providers``), the runtime is
rebuilt from the env-expanded form, and API responses redact secrets.
"""

import copy
import logging

from fastapi import APIRouter, HTTPException, Request

from src.api.v1._config_runtime import (
    load_raw_document,
    persist_raw_providers,
    redact_sensitive_values,
    resolve_config_path,
)
from src.models import (
    ProviderConfigUpdateRequest,
    ProviderListResponse,
    ProviderMetadataResponse,
    ProviderResponse,
    ProviderSettingsResponse,
)
from src.router.logging_utils import sanitize_for_log


logger = logging.getLogger(__name__)
router = APIRouter()


def _provider_to_response(provider: dict) -> ProviderResponse:
    """Build a response model, redacting secrets in metadata and settings.

    ``metadata`` may carry the live view (see :func:`_live_metadata`): when a
    provider is running, probes mutate its in-memory ``ProviderMetadata`` and
    those values — the very ones routing reads — are surfaced here. This is a
    read-only reflection; nothing is written back to ``config.yaml``.
    """
    return ProviderResponse(
        name=provider["name"],
        type=provider["type"],
        model=provider["model"],
        enabled=provider.get("enabled", True),
        fallback=provider.get("fallback", False),
        metadata=ProviderMetadataResponse(**redact_sensitive_values(provider.get("metadata", {}))),
        settings=ProviderSettingsResponse(**redact_sensitive_values(provider.get("settings", {}))),
        plugins=list(provider.get("plugins") or []),
        extra=redact_sensitive_values(provider.get("extra", {})),
    )


def _live_metadata(http_request: Request, name: str) -> dict | None:
    """Live routing metadata for a running provider, or ``None``.

    Returns ``provider.metadata.to_dict()`` for the in-memory provider instance
    held by the orchestrator — the same object probes mutate and the strategy
    layer reads on every route — so the API reflects exactly what routing sees
    (e.g. ``performance.num_requests_waiting`` published by a probe). Only
    enabled providers have a live instance; disabled/unknown providers return
    ``None`` so the caller falls back to the static config metadata.
    """
    router_runtime = getattr(http_request.app.state, "router", None)
    provider_map = getattr(router_runtime, "provider_map", None)
    if not provider_map:
        return None
    provider = provider_map.get(name)
    metadata = getattr(provider, "metadata", None)
    to_dict = getattr(metadata, "to_dict", None)
    if not callable(to_dict):
        return None
    return to_dict()


def _with_live_metadata(http_request: Request, provider: dict) -> dict:
    """Overlay the live routing metadata onto a config provider dict (read path).

    Deliberately applied only when building GET responses — never in
    ``_iter_provider_configs`` / ``_raw_provider_entries``, which feed the
    persist path, so volatile probe values can never leak into ``config.yaml``.
    """
    live = _live_metadata(http_request, provider.get("name", ""))
    if live is None:
        return provider
    return {**provider, "metadata": live}


def _probe_published_paths(http_request: Request, name: str) -> set[tuple[str, ...]]:
    """Metadata paths the running provider's probes have written (may be empty)."""
    router_runtime = getattr(http_request.app.state, "router", None)
    provider_map = getattr(router_runtime, "provider_map", None) or {}
    published = getattr(provider_map.get(name), "probe_published_paths", None)
    if not callable(published):
        return set()
    return set(published())


def _lookup_path(mapping: object, path: tuple[str, ...]) -> tuple[bool, object]:
    """Return ``(found, value)`` for a nested key path in ``mapping``."""
    node = mapping
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return False, None
        node = node[key]
    return True, node


def _strip_probe_path(metadata: dict, path: tuple[str, ...], static: dict) -> None:
    """Undo one probe-written ``path`` in ``metadata`` (in place).

    The value goes back to its on-disk ``static`` value when the config has one
    (a probe may overwrite a static seed such as ``performance.ttft_ms``);
    otherwise it is removed, along with any container left empty that the
    config never had (e.g. the ``performance`` dict a probe created).
    """
    parents: list[tuple[dict, str]] = []
    node = metadata
    for key in path[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            return
        parents.append((node, key))
        node = child
    if path[-1] not in node:
        return

    found, value = _lookup_path(static, path)
    if found:
        node[path[-1]] = copy.deepcopy(value)
        return
    del node[path[-1]]

    for depth in range(len(parents) - 1, -1, -1):
        parent, key = parents[depth]
        if parent[key]:
            break
        found, value = _lookup_path(static, path[: depth + 1])
        if not found:
            del parent[key]
        else:
            # Keep an empty dict the config already had; restore a scalar the
            # probe promoted to a dict (``performance: 0.5`` → ``{...}``).
            if not isinstance(value, dict):
                parent[key] = copy.deepcopy(value)
            break


def _strip_probe_metadata(
    metadata: dict, static: dict | None, paths: set[tuple[str, ...]]
) -> dict:
    """Drop live probe output from a POSTed ``metadata`` before it is persisted.

    GET overlays live probe values onto ``metadata`` (see
    :func:`_with_live_metadata`), so a client that edits and re-POSTs a GET body
    — the UI's edit dialog does exactly that — echoes those values back. Left
    alone they would be written to ``config.yaml`` as static metadata, outlive
    the probe that produced them, and keep steering routing with a frozen value.

    Only paths the provider's running probes have actually written are touched,
    and only when present in the payload: anything else the client sent,
    including a deliberate deletion, is kept as-is. ``static`` is the provider's
    on-disk metadata, used to restore a static value a probe overwrote.
    """
    stripped = copy.deepcopy(metadata)
    for path in sorted(paths):
        _strip_probe_path(stripped, path, static or {})
    return stripped


def _iter_provider_configs(http_request: Request) -> list[dict]:
    """Snapshot the in-memory providers as plain dicts (resolved values)."""
    config = getattr(http_request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Router not initialized")

    return [
        {
            "name": provider.name,
            "type": provider.type,
            "model": provider.model,
            "enabled": provider.enabled,
            "fallback": provider.fallback,
            "metadata": copy.deepcopy(provider.metadata),
            "settings": copy.deepcopy(provider.settings),
            "plugins": list(provider.plugins),
            "extra": copy.deepcopy(provider.extra),
        }
        for provider in config.providers
    ]


def _find_in(providers: list[dict], name: str) -> dict | None:
    for provider in providers:
        if provider.get("name") == name:
            return provider
    return None


def _find_provider(http_request: Request, name: str) -> dict | None:
    return _find_in(_iter_provider_configs(http_request), name)


def _raw_provider_entries(http_request: Request) -> list[dict]:
    """Provider entries from the *raw* on-disk document (placeholders intact).

    Falls back to the resolved in-memory providers when the file has no usable
    ``providers`` section (first write / corrupt file) — matching the raw-doc
    fallback in ``apply_and_persist_config``. This is the list mutations are
    applied to so untouched providers keep their ``${VAR}`` placeholders on disk.
    """
    config_path = resolve_config_path(http_request)
    document = load_raw_document(config_path)
    raw_providers = document.get("providers")
    if isinstance(raw_providers, list):
        return copy.deepcopy(raw_providers)
    return _iter_provider_configs(http_request)


def _updated_provider_payload(
    existing_provider: dict | None,
    name: str,
    update_req: ProviderConfigUpdateRequest,
) -> dict:
    """Apply the request onto the existing (raw) entry, or build a new one.

    Fields present in the request overwrite the corresponding fields verbatim
    (``settings``/``metadata`` are replaced wholesale, matching plugin
    semantics). Creating a provider requires ``type`` and ``model`` because the
    config loader mandates them.
    """
    if existing_provider is None:
        if not update_req.type or not update_req.model:
            raise HTTPException(
                status_code=400,
                detail=f"Creating provider '{name}' requires both 'type' and 'model'",
            )
        payload = {
            "name": name,
            "type": update_req.type,
            "model": update_req.model,
            "enabled": True,
            "fallback": False,
            "metadata": {},
            "settings": {},
            "extra": {},
        }
    else:
        payload = copy.deepcopy(existing_provider)
        payload["name"] = name

    if update_req.type is not None:
        payload["type"] = update_req.type
    if update_req.model is not None:
        payload["model"] = update_req.model
    if update_req.enabled is not None:
        payload["enabled"] = update_req.enabled
    if update_req.fallback is not None:
        payload["fallback"] = update_req.fallback
    if update_req.metadata is not None:
        payload["metadata"] = update_req.metadata.model_dump(exclude_unset=True)
    if update_req.settings is not None:
        payload["settings"] = update_req.settings.model_dump(exclude_unset=True)
    if update_req.plugins is not None:
        payload["plugins"] = list(update_req.plugins)
    if update_req.extra is not None:
        payload["extra"] = update_req.extra

    return payload


def _clear_other_fallbacks(providers: list[dict], name: str) -> list[dict]:
    """Return ``providers`` with ``fallback: false`` on every entry except ``name``.

    Only one provider may be the routing fallback at a time, so designating a
    new one demotes the previous holder. Entries that never set the flag are
    left untouched (it already defaults to ``false``) to keep the on-disk diff
    minimal.
    """
    cleared = []
    for provider in providers:
        if provider.get("name") != name and provider.get("fallback"):
            logger.info(
                "Provider %s is no longer the routing fallback (replaced by %s)",
                sanitize_for_log(provider.get("name", "")),
                sanitize_for_log(name),
            )
            provider = {**provider, "fallback": False}
        cleared.append(provider)
    return cleared


async def _persist_providers(http_request: Request, raw_providers: list[dict]) -> list[dict]:
    """Rebuild + persist the runtime with ``raw_providers`` swapped in.

    Thin wrapper over :func:`persist_raw_providers` that shapes the resulting
    runtime providers back into plain dicts for the response layer. The caller
    MUST already hold ``app.state.config_lock`` (``asyncio.Lock`` is not
    reentrant), exactly like ``src.api.v1.plugin._persist_plugins``.
    """
    updated_config = await persist_raw_providers(http_request, raw_providers)

    return [
        {
            "name": provider.name,
            "type": provider.type,
            "model": provider.model,
            "enabled": provider.enabled,
            "fallback": provider.fallback,
            "metadata": copy.deepcopy(provider.metadata),
            "settings": copy.deepcopy(provider.settings),
            "plugins": list(provider.plugins),
            "extra": copy.deepcopy(provider.extra),
        }
        for provider in updated_config.providers
    ]


@router.get("/providers")
async def list_providers(http_request: Request) -> ProviderListResponse:
    """List all configured providers."""
    providers = _iter_provider_configs(http_request)
    return ProviderListResponse(
        data=[_provider_to_response(_with_live_metadata(http_request, provider)) for provider in providers]
    )


@router.get("/providers/{name}")
async def get_provider(name: str, http_request: Request) -> ProviderResponse:
    """Get provider configuration by name."""
    provider = _find_provider(http_request, name)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    return _provider_to_response(_with_live_metadata(http_request, provider))


@router.post("/providers/{name}")
async def create_or_update_provider(
    name: str, update_req: ProviderConfigUpdateRequest, http_request: Request
) -> ProviderResponse:
    """Create or update provider configuration by name.

    The body accepts the same shape ``GET /providers/{name}`` returns (extra
    keys like ``name`` are ignored), so a GET response round-trips as a POST
    payload. Caveat: GET redacts secrets, so omit or re-supply ``api_key`` and
    friends — re-POSTing a redacted value would persist the mask. GET also
    reflects *live* probe metadata (e.g. ``performance.num_requests_waiting``);
    when a posted ``metadata`` echoes those values back they are stripped (or
    reset to their on-disk static value) before persisting — see
    :func:`_strip_probe_metadata` — so only the client's own edits reach
    ``config.yaml``.

    ``fallback`` is exclusive: setting it ``true`` on this provider sets it
    ``false`` on whichever provider held it before, in both the runtime and
    ``config.yaml``.
    """
    try:
        async with http_request.app.state.config_lock:
            providers = _raw_provider_entries(http_request)
            existing = _find_in(providers, name)
            updated = _updated_provider_payload(existing, name, update_req)
            if update_req.metadata is not None:
                updated["metadata"] = _strip_probe_metadata(
                    updated["metadata"],
                    (existing or {}).get("metadata"),
                    _probe_published_paths(http_request, name),
                )

            if existing is None:
                next_providers = [*providers, updated]
            else:
                next_providers = [
                    updated if provider.get("name") == name else provider
                    for provider in providers
                ]

            if update_req.fallback:
                next_providers = _clear_other_fallbacks(next_providers, name)

            persisted_providers = await _persist_providers(http_request, next_providers)
        persisted = next(
            provider for provider in persisted_providers if provider["name"] == name
        )
        return _provider_to_response(persisted)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create/update provider {sanitize_for_log(name)}: {e}")
        raise HTTPException(status_code=500, detail="Failed to configure provider")


@router.delete("/providers/{name}")
async def delete_provider(name: str, http_request: Request) -> dict:
    """Delete provider configuration by name."""
    try:
        async with http_request.app.state.config_lock:
            providers = _raw_provider_entries(http_request)
            remaining_providers = [
                provider for provider in providers if provider.get("name") != name
            ]
            if len(remaining_providers) == len(providers):
                raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

            await _persist_providers(http_request, remaining_providers)
        return {"status": "success", "message": f"Provider '{name}' deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete provider {sanitize_for_log(name)}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete provider")
