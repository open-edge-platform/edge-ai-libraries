# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared config serialization and runtime swap helpers for v1 config APIs."""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException, Request

from src.api.logging_setup import setup_logging
from src.config import RouterConfig
from src.config.base import TelemetryBackendType, TelemetryConfig
from src.config.loader import _build_router_config, _expand_env_vars
from src.exceptions import ConfigurationError
from src.observability import FileBasedTelemetry, InMemoryTelemetry, Telemetry
from src.router import RouterOrchestrator


logger = logging.getLogger(__name__)


def serialize_router_config(config: RouterConfig) -> dict[str, Any]:
    plugins: dict[str, list[dict[str, Any]]] = {
        "prerouting": [],
        "postrouting": [],
        "postresponse": [],
    }
    for plugin in config.plugins:
        plugins.setdefault(plugin.trigger, []).append(
            {
                "name": plugin.name,
                "node": plugin.node,
                "enabled": plugin.enabled,
                "settings": copy.deepcopy(plugin.settings),
            }
        )

    return {
        "log_level": config.log_level,
        "providers": [
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
        ],
        "plugins": plugins,
        "routing": {
            "policy": config.routing.policy,
            "strategy": config.routing.strategy,
        },
        "telemetry": {
            "backend": config.telemetry.backend.value,
            "enabled": config.telemetry.enabled,
            "file_path": config.telemetry.file_path,
        },
        "cors_origins": list(config.cors_origins),
    }


def redact_sensitive_values(value: Any) -> Any:
    sensitive_keys = {"api_key", "token", "secret", "password"}
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in sensitive_keys and item not in (None, ""):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = redact_sensitive_values(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_values(item) for item in value]
    return value


def config_warnings(config_data: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if "cors_origins" in config_data:
        warnings.append("Changes to cors_origins are persisted but may require an app restart to fully apply.")
    return warnings


def resolve_config_path(http_request: Request) -> Path:
    config_path = getattr(http_request.app.state, "config_path", None)
    if config_path is None:
        raise HTTPException(status_code=503, detail="Config path not configured")
    return Path(config_path)


def _load_raw_document(config_path: Path) -> dict[str, Any]:
    """Parse the on-disk config WITHOUT env-var expansion.

    Returned dict preserves ``${VAR}`` placeholders exactly as written, so the
    persist path can overlay mutated sections without ever materializing the
    resolved secret values held in memory. Returns ``{}`` when the file is
    absent or unreadable.
    """
    try:
        if not config_path.exists():
            return {}
        with config_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError):
        logger.warning("Could not read raw config at %s; rewriting from runtime state", config_path)
        return {}
    return data if isinstance(data, dict) else {}


def load_raw_document(config_path: Path) -> dict[str, Any]:
    """Public accessor for the raw (env-unexpanded) on-disk config document.

    Config APIs that mutate a secret-bearing section (e.g. providers) use this
    to read the file with ``${VAR}`` placeholders intact, so they can overlay
    only the changed entries without resolving secrets to disk. Returns ``{}``
    when the file is absent or unreadable.
    """
    return _load_raw_document(config_path)


def _atomic_write_yaml(config_path: Path, data: dict[str, Any]) -> None:
    """Write ``data`` as YAML crash-safely.

    Dumps to a sibling temp file then atomically renames it over the target, so
    an interrupted write can never leave a truncated / half-written config.yaml.
    """
    tmp_path = config_path.with_name(f"{config_path.name}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False)
        os.replace(tmp_path, config_path)
    except OSError as exc:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to write config file: {exc}")


def _discard_router(router: RouterOrchestrator) -> None:
    """Best-effort shutdown of a freshly-built router we are not adopting."""
    shutdown = getattr(router, "shutdown", None)
    if callable(shutdown):
        try:
            shutdown()
        except Exception:
            logger.warning("Failed to shut down discarded router", exc_info=True)


def _build_telemetry(
    cfg: TelemetryConfig,
    fallback_dir: Path,
    log_dir: Path | None = None,
) -> Telemetry:
    if cfg.enabled and cfg.backend == TelemetryBackendType.FILE:
        if cfg.file_path:
            path = Path(cfg.file_path)
        else:
            base = log_dir if log_dir is not None else fallback_dir
            path = base / "telemetry.jsonl"
        return FileBasedTelemetry(path)
    return InMemoryTelemetry()


async def _prepare_runtime(
    http_request: Request,
    config_data: dict[str, Any],
    config_path: Path,
) -> tuple[RouterConfig, RouterOrchestrator, Telemetry]:
    try:
        new_config = _build_router_config(config_data)
    except ConfigurationError as config_error:
        raise HTTPException(status_code=400, detail=str(config_error))

    state = http_request.app.state
    log_dir = getattr(state, "log_dir", None)
    telemetry = _build_telemetry(new_config.telemetry, fallback_dir=config_path.parent, log_dir=log_dir)

    # Construction can already reject a bad config — e.g. the DecisionEngine
    # validates the routing policy/strategy against policy.yaml here — so keep
    # it inside the try so such errors surface as a 400, not an unhandled 500.
    try:
        new_router = RouterOrchestrator(new_config, telemetry=telemetry)
        await new_router.initialize()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to initialize updated config: {exc}")

    return new_config, new_router, telemetry


def _swap_runtime_state(
    http_request: Request,
    new_config: RouterConfig,
    new_router: RouterOrchestrator,
    telemetry: Telemetry,
) -> None:
    state = http_request.app.state
    old_router = getattr(state, "router", None)
    old_config = getattr(state, "config", None)
    state.router = new_router
    state.plugin_manager = new_router.plugin_manager
    state.telemetry = telemetry
    state.config = new_config

    # Re-apply the logging level so a changed ``log_level`` takes effect at
    # runtime, not just on disk. Only when it actually changed, to avoid
    # tearing down/rebuilding logging handlers on every unrelated edit.
    if old_config is None or old_config.log_level != new_config.log_level:
        try:
            setup_logging(new_config)
        except Exception:
            logger.warning("Failed to re-apply log level after config change", exc_info=True)

    if old_router is not None and old_router is not new_router:
        shutdown = getattr(old_router, "shutdown", None)
        if callable(shutdown):
            shutdown()


async def apply_config(
    http_request: Request,
    config_data: dict[str, Any],
    config_path: Path,
) -> RouterConfig:
    new_config, new_router, telemetry = await _prepare_runtime(
        http_request,
        config_data,
        config_path,
    )
    _swap_runtime_state(http_request, new_config, new_router, telemetry)
    return new_config


async def persist_raw_providers(
    http_request: Request, raw_providers: list[dict[str, Any]]
) -> RouterConfig:
    """Swap the full providers list, rebuild the runtime, and persist to disk.

    ``raw_providers`` are entries in their *raw* (env-unexpanded) form: they are
    written to ``config.yaml`` verbatim so ``${VAR}`` placeholders survive, while
    the runtime is rebuilt from their ``_expand_env_vars`` form so resolved
    secrets never touch disk. The caller MUST already hold
    ``app.state.config_lock`` (``asyncio.Lock`` is not reentrant).

    Shared by the providers CRUD API (``src.api.v1.provider``) and the
    ``provider_management`` plugin, which both replace the providers section
    wholesale after mutating one entry.
    """
    config = getattr(http_request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Router not initialized")

    config_data = serialize_router_config(config)
    # Runtime gets the resolved form; disk keeps the raw placeholders.
    config_data["providers"] = _expand_env_vars(copy.deepcopy(raw_providers))

    config_path = resolve_config_path(http_request)
    return await apply_and_persist_config(
        http_request,
        config_data,
        config_path=config_path,
        persist_overlay={"providers": raw_providers},
    )


async def apply_and_persist_config(
    http_request: Request,
    config_data: dict[str, Any],
    config_path: Path,
    *,
    persist_overlay: dict[str, Any] | None = None,
) -> RouterConfig:
    new_config, new_router, telemetry = await _prepare_runtime(
        http_request,
        config_data,
        config_path,
    )

    # Persist by overlaying the mutated section(s) onto the *raw* on-disk
    # document (parsed without env-var expansion), so provider ``${VAR}``
    # placeholders in the file are preserved verbatim instead of being
    # overwritten with the resolved values held in memory.
    #
    # ``persist_overlay`` lets a caller supply exactly which top-level sections
    # to write and with what (raw) values — e.g. the providers API passes the
    # raw, placeholder-preserving providers list. When omitted, the default is
    # the legacy plugins-only overlay: plugins carry no secrets, so they are
    # taken straight from ``config_data``.
    document = _load_raw_document(config_path)
    if not document:
        # No readable file to preserve (first write / corrupt file): fall back
        # to the full serialized runtime config so the file stays valid.
        document = serialize_router_config(new_config)
    if persist_overlay is None:
        document["plugins"] = config_data.get("plugins", document.get("plugins", {}))
    else:
        for section, value in persist_overlay.items():
            document[section] = value

    try:
        _atomic_write_yaml(config_path, document)
    except HTTPException:
        # File never changed; drop the router we built but won't adopt.
        _discard_router(new_router)
        raise

    _swap_runtime_state(http_request, new_config, new_router, telemetry)
    return new_config