# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Plugin manager and plugin factory."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Type

from src.config import PluginConfig, ProviderConfig
from src.exceptions import ConfigurationError
from src.models import ChatCompletionRequest, ChatCompletionResponse
from src.plugins.base import PluginSchemaError, PluginBaseNode

logger = logging.getLogger(__name__)

# Modules that live next to the registry itself; importing them as plugins
# would be circular or pointless.
_DISCOVERY_SKIP = {"base", "manager"}


# Per-request id for the current task; set by the API layer, read by plugins.
_REQUEST_ID: ContextVar[Optional[str]] = ContextVar("plugin_request_id", default=None)


def set_request_id(request_id: Optional[str]) -> None:
    """Set the current request id."""
    _REQUEST_ID.set(request_id)


def get_request_id() -> Optional[str]:
    """Current request id, or None outside a request scope."""
    return _REQUEST_ID.get()


class PluginManager:
    """Runs request plugins in configured order.

    Postrouting/postresponse plugins may be scoped to providers: a plugin whose
    name is in ``provider_scopes`` runs only when the request's provider is one
    of the mapped names; unscoped plugins run for every provider. Prerouting
    plugins always run (the provider is not chosen yet).
    """

    def __init__(
        self,
        prerouting_plugins: List[PluginBaseNode],
        postrouting_plugins: List[PluginBaseNode],
        postresponse_plugins: List[PluginBaseNode],
        standalone_plugins: List[PluginBaseNode] | None = None,
        provider_scopes: Dict[str, FrozenSet[str]] | None = None,
    ):
        self.prerouting_plugins = prerouting_plugins
        self.postrouting_plugins = postrouting_plugins
        self.postresponse_plugins = postresponse_plugins
        # ``standalone`` plugins are built and discoverable (routes, settings) but are
        # deliberately absent from every hook list, so no request/response chain
        # ever runs them. They are still in ``self.plugins`` for lookup/finalizers.
        self.standalone_plugins = standalone_plugins or []
        self.plugins = (
            prerouting_plugins
            + postrouting_plugins
            + postresponse_plugins
            + self.standalone_plugins
        )
        # plugin name → providers it is attached to (absent = all providers).
        self.provider_scopes = provider_scopes or {}

    def _runs_for(self, plugin: PluginBaseNode, provider_name: str | None) -> bool:
        """Whether a postrouting/postresponse plugin applies to ``provider_name``."""
        scope = self.provider_scopes.get(plugin.name)
        return scope is None or provider_name in scope

    def plugins_for_provider(
        self, provider_name: str | None, trigger: str
    ) -> List[PluginBaseNode]:
        """The ``postrouting``/``postresponse`` chain run for ``provider_name``."""
        plugins = {
            "postrouting": self.postrouting_plugins,
            "postresponse": self.postresponse_plugins,
        }[trigger]
        return [p for p in plugins if self._runs_for(p, provider_name)]

    async def process_prerouting_request(
        self, request: ChatCompletionRequest, **kwargs: Any
    ) -> ChatCompletionRequest:
        """Run prerouting plugins sequentially in configured order."""
        current = request
        for plugin in self.prerouting_plugins:
            current = await plugin.process_request(current, **kwargs)
        return current

    async def process_postrouting_request(
        self,
        request: ChatCompletionRequest,
        *,
        provider_name: str | None = None,
        **kwargs: Any,
    ) -> ChatCompletionRequest:
        """Run the postrouting plugins for ``provider_name`` in configured order.

        With ``provider_name=None`` only plugins not attached to a provider run.
        """
        current = request
        for plugin in self.plugins_for_provider(provider_name, "postrouting"):
            current = await plugin.process_request(
                current, provider_name=provider_name, **kwargs
            )
        return current

    async def process_postresponse_response(
        self,
        response: ChatCompletionResponse,
        *,
        provider_name: str | None = None,
        **kwargs: Any,
    ) -> ChatCompletionResponse:
        """Run the postresponse plugins for ``provider_name`` in configured order.

        With ``provider_name=None`` only plugins not attached to a provider run.
        """
        current = response
        for plugin in self.plugins_for_provider(provider_name, "postresponse"):
            current = await plugin.process_response(
                current, provider_name=provider_name, **kwargs
            )
        return current

    async def process_request(
        self, request: ChatCompletionRequest, **kwargs: Any
    ) -> ChatCompletionRequest:
        """Run prerouting then postrouting plugins."""
        current = await self.process_prerouting_request(request, **kwargs)
        current = await self.process_postrouting_request(current, **kwargs)
        return current

    def get_plugin_by_name(self, name: str) -> PluginBaseNode | None:
        """Get plugin by name. Returns first match if name exists in multiple lists."""
        for plugin in self.plugins:
            if plugin.name == name:
                return plugin
        return None

    def get_plugin_by_name_and_node(self, name: str, node: str) -> PluginBaseNode | None:
        """Get plugin by name and node type."""
        for plugin in self.plugins:
            if plugin.name == name and plugin.plugin_type() == node:
                return plugin
        return None

    def get_plugins_by_group(self, group: str) -> List[PluginBaseNode]:
        """All loaded plugins sharing the given ``plugin_group``."""
        return [p for p in self.plugins if p.plugin_group == group]

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


_PLUGIN_REGISTRY: Dict[str, Type[PluginBaseNode]] = {}
_DISCOVERED = False

# node key → finalizer run once with all instances of that node.
_NODE_FINALIZERS: Dict[str, Callable[[List[PluginBaseNode]], None]] = {}


def register_plugin(plugin_cls: Type[PluginBaseNode]) -> Type[PluginBaseNode]:
    """Register a plugin class for factory lookup."""
    plugin_type = plugin_cls.plugin_type()
    existing_cls = _PLUGIN_REGISTRY.get(plugin_type)
    if existing_cls is not None and existing_cls is not plugin_cls:
        raise RuntimeError(
            f"Duplicate plugin type '{plugin_type}' registered by "
            f"{plugin_cls.__module__}.{plugin_cls.__name__}; already registered by "
            f"{existing_cls.__module__}.{existing_cls.__name__}"
        )
    _PLUGIN_REGISTRY[plugin_type] = plugin_cls
    return plugin_cls


def register_node_finalizer(node: str) -> Callable:
    """Decorator: register a finalizer run once with all instances of ``node``."""

    def _decorator(fn: Callable[[List[PluginBaseNode]], None]):
        _NODE_FINALIZERS[node] = fn
        return fn

    return _decorator


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


def get_registered_plugin_class(node: str) -> Optional[Type[PluginBaseNode]]:
    """Registered plugin class for ``node`` (a plugin type key), or ``None``.

    Triggers module discovery so the full registry is populated before lookup.
    """
    _discover_plugin_modules()
    return _PLUGIN_REGISTRY.get(node)


def iter_registered_plugin_classes() -> List[Type[PluginBaseNode]]:
    """Every registered plugin *class*, sorted by node key (after discovery).

    Triggers module discovery so the registry is fully populated. Used by the
    app factory to collect plugin-contributed routers (see
    :meth:`PluginBaseNode.routes`).
    """
    _discover_plugin_modules()
    return [plugin_cls for _, plugin_cls in sorted(_PLUGIN_REGISTRY.items())]


def list_registered_plugin_nodes() -> List[Dict[str, Any]]:
    """Metadata for every registered plugin *type* (node), sorted by node key.

    Triggers module discovery so the full registry is populated, then reports
    each type's :meth:`PluginBaseNode.node_metadata`. This describes the plugin
    types available in code, independent of which instances are configured.
    Kept lightweight — it does not call ``describe_node()``, so node-level
    aggregate overrides never run on the list endpoint.
    """
    _discover_plugin_modules()
    return [
        plugin_cls.node_metadata()
        for _, plugin_cls in sorted(_PLUGIN_REGISTRY.items())
    ]


def build_plugin(plugin_config: PluginConfig) -> PluginBaseNode:
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
        )
    except PluginSchemaError as exc:
        raise ConfigurationError(str(exc)) from exc

    return plugin


def _provider_scopes(
    provider_configs: List[ProviderConfig],
) -> Dict[str, FrozenSet[str]]:
    """Invert providers' ``plugins`` lists into plugin name → provider names.

    Disabled providers still claim their plugins, so disabling a provider does
    not turn its attached plugins into run-for-everyone ones.
    """
    scopes: Dict[str, set] = {}
    for provider in provider_configs:
        for plugin_name in provider.plugins:
            scopes.setdefault(plugin_name, set()).add(provider.name)
    return {name: frozenset(providers) for name, providers in scopes.items()}


def create_plugin_manager(
    plugin_configs: List[PluginConfig],
    provider_configs: List[ProviderConfig] | None = None,
) -> PluginManager:
    """Create plugin manager from config while preserving list order.

    ``provider_configs`` supplies the provider → plugin attachments (each
    provider's ``plugins``) that scope postrouting/postresponse plugins.
    """
    _discover_plugin_modules()
    prerouting_plugins: List[PluginBaseNode] = []
    postrouting_plugins: List[PluginBaseNode] = []
    postresponse_plugins: List[PluginBaseNode] = []
    standalone_plugins: List[PluginBaseNode] = []
    trigger_buckets = {
        "prerouting": prerouting_plugins,
        "postrouting": postrouting_plugins,
        "postresponse": postresponse_plugins,
        "standalone": standalone_plugins,
    }
    for plugin_config in plugin_configs:
        if not plugin_config.enabled:
            logger.info("Plugin disabled: %s", plugin_config.name)
            continue

        plugin = build_plugin(plugin_config)
        # Unknown triggers are rejected at config-load time; default to prerouting
        # defensively for any direct caller that bypassed the loader.
        trigger_buckets.get(plugin_config.trigger, prerouting_plugins).append(plugin)
        logger.info(
            "Loaded plugin: %s (%s, trigger=%s)",
            plugin_config.name,
            plugin_config.node,
            plugin_config.trigger,
        )

    # Run each node's finalizer once with all instances of that node.
    all_plugins = (
        prerouting_plugins + postrouting_plugins + postresponse_plugins + standalone_plugins
    )
    by_node: Dict[str, List[PluginBaseNode]] = {}
    for plugin in all_plugins:
        by_node.setdefault(plugin.plugin_type(), []).append(plugin)
    for node, members in by_node.items():
        fn = _NODE_FINALIZERS.get(node)
        if fn is None:
            continue
        try:
            fn(members)
        except Exception as exc:
            logger.warning("Node finalizer failed for %r: %s", node, exc)

    scopes = _provider_scopes(provider_configs or [])
    for plugin in postrouting_plugins + postresponse_plugins:
        if plugin.name in scopes:
            logger.info(
                "Plugin %s (%s) attached to providers: %s",
                plugin.name,
                plugin.trigger,
                sorted(scopes[plugin.name]),
            )

    return PluginManager(
        prerouting_plugins,
        postrouting_plugins,
        postresponse_plugins,
        standalone_plugins,
        provider_scopes=scopes,
    )
