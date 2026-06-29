# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Plugin manager and plugin factory."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Any, Dict, List, Type

from src.config import PluginConfig
from src.exceptions import ConfigurationError
from src.models import ChatCompletionRequest, ChatCompletionResponse
from src.plugins.base import PluginSchemaError, RequestPlugin

logger = logging.getLogger(__name__)

# Modules that live next to the registry itself; importing them as plugins
# would be circular or pointless.
_DISCOVERY_SKIP = {"base", "manager"}


class PluginManager:
    """Runs request plugins in configured order."""

    def __init__(
        self,
        prerouting_plugins: List[RequestPlugin],
        postrouting_plugins: List[RequestPlugin],
        postresponse_plugins: List[RequestPlugin],
    ):
        self.prerouting_plugins = prerouting_plugins
        self.postrouting_plugins = postrouting_plugins
        self.postresponse_plugins = postresponse_plugins
        self.plugins = prerouting_plugins + postrouting_plugins + postresponse_plugins

    async def process_prerouting_request(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionRequest:
        """Run prerouting plugins sequentially in configured order."""
        current = request
        for plugin in self.prerouting_plugins:
            current = await plugin.process_request(current)
        return current

    async def process_postrouting_request(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionRequest:
        """Run postrouting plugins sequentially in configured order."""
        current = request
        for plugin in self.postrouting_plugins:
            current = await plugin.process_request(current)
        return current

    async def process_postresponse_response(
        self, response: ChatCompletionResponse
    ) -> ChatCompletionResponse:
        """Run postresponse plugins sequentially in configured order."""
        current = response
        for plugin in self.postresponse_plugins:
            current = await plugin.process_response(current)
        return current

    async def process_request(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        """Run prerouting then postrouting plugins."""
        current = await self.process_prerouting_request(request)
        current = await self.process_postrouting_request(current)
        return current

    def get_plugin_by_name(self, name: str) -> RequestPlugin | None:
        """Get plugin by name. Returns first match if name exists in multiple lists."""
        for plugin in self.plugins:
            if plugin.name == name:
                return plugin
        return None

    def get_plugin_by_name_and_node(self, name: str, node: str) -> RequestPlugin | None:
        """Get plugin by name and node type."""
        for plugin in self.plugins:
            if plugin.name == name and plugin.plugin_type() == node:
                return plugin
        return None

    def get_all_plugins_config(self) -> List[Dict[str, Any]]:
        """Get all plugins with their configuration."""
        configs = []
        for plugin in self.plugins:
            config = {
                "name": plugin.name,
                "node": plugin.plugin_type(),
                "enabled": True,  # Plugins in manager are always enabled
                "trigger": plugin.trigger,
                "settings": {
                    "extra_config": getattr(plugin.parsed_settings, "extra_config", {})
                },
            }
            configs.append(config)
        return configs

    def update_plugin_settings(
        self, name: str, node: str, new_settings: Dict[str, Any]
    ) -> bool:
        """
        Update plugin settings at runtime.

        Args:
            name: Plugin name
            node: Plugin node type
            new_settings: New settings dict with 'extra_config' key

        Returns:
            True if update succeeded, False if plugin not found
        """
        plugin = self.get_plugin_by_name_and_node(name, node)
        if not plugin:
            return False

        # Update the extra_config in parsed_settings if it exists
        if hasattr(plugin.parsed_settings, "extra_config"):
            if "extra_config" in new_settings:
                plugin.parsed_settings.extra_config = new_settings["extra_config"]
        return True


_PLUGIN_REGISTRY: Dict[str, Type[RequestPlugin]] = {}
_DISCOVERED = False


def register_plugin(plugin_cls: Type[RequestPlugin]) -> Type[RequestPlugin]:
    """Register a plugin class for factory lookup."""
    plugin_type = plugin_cls.plugin_type()
    _PLUGIN_REGISTRY[plugin_type] = plugin_cls
    return plugin_cls


def _discover_plugin_modules() -> None:
    """Import every module under ``src.plugins`` so ``@register_plugin`` runs.

    Idempotent: subsequent calls are no-ops. Plugin authors only need to drop
    a file (or subpackage) under ``src/plugins/`` — no central edit required.
    """
    global _DISCOVERED
    if _DISCOVERED:
        return

    package_dir = Path(__file__).parent
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name in _DISCOVERY_SKIP or module_info.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"src.plugins.{module_info.name}")
        except Exception as exc:
            logger.error("Failed to import plugin module '%s': %s", module_info.name, exc)
            raise

    _DISCOVERED = True


def build_plugin(plugin_config: PluginConfig) -> RequestPlugin:
    """Build a plugin instance from config."""
    plugin_node = plugin_config.node
    plugin_cls = _PLUGIN_REGISTRY.get(plugin_node)
    if plugin_cls is None:
        raise ConfigurationError(
            f"Unknown plugin node '{plugin_node}' for plugin '{plugin_config.name}'"
        )

    try:
        plugin = plugin_cls(
            name=plugin_config.name,
            settings=plugin_config.settings,
            trigger=plugin_config.trigger,
            nodes=plugin_config.nodes,
        )
    except PluginSchemaError as exc:
        raise ConfigurationError(str(exc)) from exc

    return plugin


def create_plugin_manager(plugin_configs: List[PluginConfig]) -> PluginManager:
    """Create plugin manager from config while preserving list order."""
    _discover_plugin_modules()
    prerouting_plugins: List[RequestPlugin] = []
    postrouting_plugins: List[RequestPlugin] = []
    postresponse_plugins: List[RequestPlugin] = []
    for plugin_config in plugin_configs:
        if not plugin_config.enabled:
            logger.info("Plugin disabled: %s", plugin_config.name)
            continue

        plugin = build_plugin(plugin_config)
        if plugin_config.trigger == "prerouting":
            prerouting_plugins.append(plugin)
        elif plugin_config.trigger == "postrouting":
            postrouting_plugins.append(plugin)
        else:
            postresponse_plugins.append(plugin)
        logger.info(
            "Loaded plugin: %s (%s, trigger=%s)",
            plugin_config.name,
            plugin_config.node,
            plugin_config.trigger,
        )

    return PluginManager(prerouting_plugins, postrouting_plugins, postresponse_plugins)
