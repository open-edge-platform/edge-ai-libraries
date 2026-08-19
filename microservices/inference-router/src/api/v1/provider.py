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
    """Build a response model, redacting secrets in metadata and settings."""
    return ProviderResponse(
        name=provider["name"],
        type=provider["type"],
        model=provider["model"],
        enabled=provider.get("enabled", True),
        metadata=ProviderMetadataResponse(**redact_sensitive_values(provider.get("metadata", {}))),
        settings=ProviderSettingsResponse(**redact_sensitive_values(provider.get("settings", {}))),
        extra=redact_sensitive_values(provider.get("extra", {})),
    )


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
            "metadata": copy.deepcopy(provider.metadata),
            "settings": copy.deepcopy(provider.settings),
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
    if update_req.metadata is not None:
        payload["metadata"] = update_req.metadata.model_dump(exclude_unset=True)
    if update_req.settings is not None:
        payload["settings"] = update_req.settings.model_dump(exclude_unset=True)
    if update_req.extra is not None:
        payload["extra"] = update_req.extra

    return payload


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
            "metadata": copy.deepcopy(provider.metadata),
            "settings": copy.deepcopy(provider.settings),
            "extra": copy.deepcopy(provider.extra),
        }
        for provider in updated_config.providers
    ]


@router.get("/providers")
async def list_providers(http_request: Request) -> ProviderListResponse:
    """List all configured providers."""
    providers = _iter_provider_configs(http_request)
    return ProviderListResponse(data=[_provider_to_response(provider) for provider in providers])


@router.get("/providers/{name}")
async def get_provider(name: str, http_request: Request) -> ProviderResponse:
    """Get provider configuration by name."""
    provider = _find_provider(http_request, name)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    return _provider_to_response(provider)


@router.post("/providers/{name}")
async def create_or_update_provider(
    name: str, update_req: ProviderConfigUpdateRequest, http_request: Request
) -> ProviderResponse:
    """Create or update provider configuration by name.

    The body accepts the same shape ``GET /providers/{name}`` returns (extra
    keys like ``name`` are ignored), so a GET response round-trips as a POST
    payload. Caveat: GET redacts secrets, so omit or re-supply ``api_key`` and
    friends — re-POSTing a redacted value would persist the mask.
    """
    try:
        async with http_request.app.state.config_lock:
            providers = _raw_provider_entries(http_request)
            existing = _find_in(providers, name)
            updated = _updated_provider_payload(existing, name, update_req)

            if existing is None:
                next_providers = [*providers, updated]
            else:
                next_providers = [
                    updated if provider.get("name") == name else provider
                    for provider in providers
                ]

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
