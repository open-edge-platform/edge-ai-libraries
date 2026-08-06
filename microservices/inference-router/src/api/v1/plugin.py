# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""v1 plugin management endpoints."""

import copy
import logging

from fastapi import APIRouter, HTTPException, Request

from src.api.v1._config_runtime import apply_and_persist_config, resolve_config_path
from src.models import (
    PluginConfigUpdateRequest,
    PluginListResponse,
    PluginNodeListResponse,
    PluginNodeResponse,
    PluginResponse,
    PluginSettingsResponse,
)
from src.plugins.manager import (
    get_registered_plugin_class,
    list_registered_plugin_nodes,
)


logger = logging.getLogger(__name__)
router = APIRouter()


def _plugin_to_response(plugin_config: dict) -> PluginResponse:
    return PluginResponse(
        name=plugin_config["name"],
        node=plugin_config["node"],
        enabled=plugin_config.get("enabled", True),
        trigger=plugin_config.get("trigger", "prerouting"),
        settings=PluginSettingsResponse(**copy.deepcopy(plugin_config.get("settings", {}))),
    )


def _iter_plugin_configs(http_request: Request) -> list[dict]:
    config = getattr(http_request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Router not initialized")

    return [
        {
            "name": plugin.name,
            "node": plugin.node,
            "enabled": plugin.enabled,
            "trigger": plugin.trigger,
            "settings": copy.deepcopy(plugin.settings),
        }
        for plugin in config.plugins
    ]


def _find_in(plugins: list[dict], name: str, node: str) -> dict | None:
    for plugin in plugins:
        if plugin["name"] == name and plugin["node"] == node:
            return plugin
    return None


def _find_plugin(http_request: Request, name: str, node: str) -> dict | None:
    return _find_in(_iter_plugin_configs(http_request), name, node)


def _group_plugins(plugins: list[dict]) -> dict[str, list[dict]]:
    grouped = {
        "prerouting": [],
        "postrouting": [],
        "postresponse": [],
    }
    for plugin in plugins:
        grouped.setdefault(plugin["trigger"], []).append(
            {
                "name": plugin["name"],
                "node": plugin["node"],
                "enabled": plugin.get("enabled", True),
                "settings": copy.deepcopy(plugin.get("settings", {})),
            }
        )
    return grouped


def _updated_plugin_payload(
    existing_plugin: dict | None,
    name: str,
    node: str,
    update_req: PluginConfigUpdateRequest,
) -> dict:
    current = existing_plugin or {
        "name": name,
        "node": node,
        "enabled": True,
        "trigger": "prerouting",
        "settings": {},
    }
    payload = copy.deepcopy(current)

    if update_req.enabled is not None:
        payload["enabled"] = update_req.enabled
    if update_req.trigger is not None:
        payload["trigger"] = update_req.trigger
    if update_req.settings is not None:
        payload["settings"] = update_req.settings.model_dump(exclude_unset=True)

    return payload


async def _persist_plugins(http_request: Request, plugins: list[dict]) -> list[dict]:
    """Rebuild + persist the runtime with ``plugins`` swapped in.

    The caller MUST already hold ``app.state.config_lock`` so the surrounding
    read-modify-write stays atomic against concurrent config changes; this
    helper does not acquire the lock itself (``asyncio.Lock`` is not reentrant).
    """
    config = getattr(http_request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Router not initialized")

    config_data = {
        "log_level": config.log_level,
        "providers": [
            {
                "name": provider.name,
                "type": provider.type,
                "model": provider.model,
                "enabled": provider.enabled,
                "metadata": copy.deepcopy(provider.metadata),
                "settings": copy.deepcopy(provider.settings),
            }
            for provider in config.providers
        ],
        "plugins": _group_plugins(plugins),
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

    config_path = resolve_config_path(http_request)
    updated_config = await apply_and_persist_config(
        http_request,
        config_data,
        config_path=config_path,
    )

    return [
        {
            "name": plugin.name,
            "node": plugin.node,
            "enabled": plugin.enabled,
            "trigger": plugin.trigger,
            "settings": copy.deepcopy(plugin.settings),
        }
        for plugin in updated_config.plugins
    ]


@router.get("/plugins")
async def list_plugins(http_request: Request) -> PluginListResponse:
    """List all configured plugins."""
    plugins = _iter_plugin_configs(http_request)
    return PluginListResponse(data=[_plugin_to_response(plugin) for plugin in plugins])


@router.get("/plugins/nodes")
async def list_plugin_nodes() -> PluginNodeListResponse:
    """List all registered plugin types (nodes) available in code."""
    return PluginNodeListResponse(
        data=[PluginNodeResponse(**node) for node in list_registered_plugin_nodes()]
    )


@router.get("/plugins/{node}")
async def get_plugin_node(node: str) -> dict:
    """Node-level view of a plugin type, as defined by the plugin class.

    Returns whatever ``PluginBaseNode.describe_node()`` produces for the type
    (default: its metadata; overrides may add aggregate info). 404 if the node
    is not a registered plugin type.
    """
    plugin_cls = get_registered_plugin_class(node)
    if plugin_cls is None:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin node '{node}' not registered",
        )
    try:
        return plugin_cls.describe_node()
    except Exception as e:
        logger.error(f"Failed to describe plugin node {node}: {e}")
        raise HTTPException(status_code=500, detail="Failed to describe plugin node")


def _live_plugin_or_none(http_request: Request, name: str, node: str):
    """Live plugin instance from the manager, or ``None`` if absent/unavailable."""
    manager = getattr(http_request.app.state, "plugin_manager", None)
    getter = getattr(manager, "get_plugin_by_name_and_node", None)
    if getter is None:
        return None
    return getter(name, node)


@router.get("/plugins/{node}/{name}")
async def get_plugin(node: str, name: str, http_request: Request) -> dict:
    """Instance view of a plugin, as defined by ``PluginBaseNode.describe()``.

    Prefers the live instance (so per-instance runtime info such as metrics is
    included); falls back to the static config view for configured-but-disabled
    plugins that are not loaded. 404 if neither is found.
    """
    live = _live_plugin_or_none(http_request, name, node)
    if live is not None:
        try:
            return live.describe()
        except Exception as e:
            logger.error(f"Failed to describe plugin {node}/{name}: {e}")
            raise HTTPException(status_code=500, detail="Failed to describe plugin")

    plugin = _find_plugin(http_request, name, node)
    if plugin is None:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{name}' with node '{node}' not found",
        )
    return _plugin_to_response(plugin).model_dump()


def _live_plugin(http_request: Request, name: str, node: str):
    """Resolve a live plugin instance from the manager (not the config list).

    Per-instance reset acts on runtime state, so it must target the loaded
    plugin rather than ``app.state.config``.
    """
    manager = getattr(http_request.app.state, "plugin_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Router not initialized")
    plugin = manager.get_plugin_by_name_and_node(name, node)
    if plugin is None:
        # Configured-but-disabled plugins are absent from the manager.
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{name}' with node '{node}' not loaded",
        )
    return plugin


@router.post("/plugins/{node}/{name}/reset")
async def reset_plugin_instance(node: str, name: str, http_request: Request) -> dict:
    """Reset a single plugin instance's own runtime state (e.g. metrics)."""
    plugin = _live_plugin(http_request, name, node)
    if not plugin.reset():
        raise HTTPException(
            status_code=400,
            detail=f"Plugin '{name}' with node '{node}' does not support reset",
        )
    return {"status": "success", "message": f"Reset plugin '{name}'"}


@router.post("/plugins/{node}/reset")
async def reset_plugin_node(node: str) -> dict:
    """Reset node-level (type/group-wide) state for a plugin type.

    Declared before ``POST /plugins/{node}/{name}`` so the literal ``reset``
    segment is matched here rather than captured as an instance ``{name}``
    (an instance literally named ``reset`` is therefore unreachable).
    """
    plugin_cls = get_registered_plugin_class(node)
    if plugin_cls is None:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin node '{node}' not registered",
        )
    if not plugin_cls.reset_node():
        raise HTTPException(
            status_code=400,
            detail=f"Plugin node '{node}' does not support reset",
        )
    return {"status": "success", "message": f"Reset plugin node '{node}'"}


@router.post("/plugins/{node}/{name}")
async def create_or_update_plugin(
    node: str, name: str, update_req: PluginConfigUpdateRequest, http_request: Request
) -> PluginResponse:
    """Create or update plugin configuration by node type and name."""
    try:
        async with http_request.app.state.config_lock:
            plugins = _iter_plugin_configs(http_request)
            existing = _find_in(plugins, name, node)
            updated = _updated_plugin_payload(existing, name, node, update_req)

            if existing is None:
                next_plugins = [*plugins, updated]
            else:
                next_plugins = [
                    updated if plugin["name"] == name and plugin["node"] == node else plugin
                    for plugin in plugins
                ]

            persisted_plugins = await _persist_plugins(http_request, next_plugins)
        persisted = next(
            plugin for plugin in persisted_plugins if plugin["name"] == name and plugin["node"] == node
        )
        return _plugin_to_response(persisted)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create/update plugin {name}/{node}: {e}")
        raise HTTPException(status_code=500, detail="Failed to configure plugin")


@router.delete("/plugins/{node}/{name}")
async def delete_plugin(node: str, name: str, http_request: Request) -> dict:
    """Delete plugin configuration by node type and name."""
    try:
        async with http_request.app.state.config_lock:
            plugins = _iter_plugin_configs(http_request)
            remaining_plugins = [
                plugin for plugin in plugins if not (plugin["name"] == name and plugin["node"] == node)
            ]
            if len(remaining_plugins) == len(plugins):
                raise HTTPException(
                    status_code=404,
                    detail=f"Plugin '{name}' with node '{node}' not found",
                )

            await _persist_plugins(http_request, remaining_plugins)
        return {"status": "success", "message": f"Plugin '{name}' deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete plugin {name}/{node}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete plugin")