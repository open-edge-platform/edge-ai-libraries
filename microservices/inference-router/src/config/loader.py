# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Configuration loader for YAML files."""

import logging
import os
import re
from typing import Any, Optional
from pathlib import Path
import yaml

from src.config.base import (
    RouterConfig,
    ProviderConfig,
    PluginConfig,
    TelemetryConfig,
    RoutingConfig,
    TelemetryBackendType,
)
from src.exceptions import ConfigurationError


logger = logging.getLogger(__name__)


# Matches ``${VAR}`` or ``${VAR:-default}`` anywhere in a string.
_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand_env_in_string(value: str) -> Optional[str]:
    """Resolve ``${VAR}`` / ``${VAR:-default}`` references inside a string.

    A string that is exactly a single unset reference (no default) resolves
    to ``None`` so that ``api_key: "${OPENAI_API_KEY}"`` cleanly disappears
    when the variable isn't set, instead of being passed through as the
    literal placeholder.
    """
    match = _ENV_VAR_PATTERN.fullmatch(value.strip())
    if match:
        var_name, default = match.group(1), match.group(2)
        env_val = os.environ.get(var_name)
        if env_val is not None:
            return env_val
        if default is not None:
            return default
        logger.debug(f"Env var {var_name!r} not set; resolving to None")
        return None

    def _sub(m: re.Match) -> str:
        var_name, default = m.group(1), m.group(2)
        env_val = os.environ.get(var_name)
        if env_val is not None:
            return env_val
        if default is not None:
            return default
        logger.debug(f"Env var {var_name!r} not set; substituting empty string")
        return ""

    return _ENV_VAR_PATTERN.sub(_sub, value)


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand ``${VAR}`` references in dicts, lists, and strings."""
    if isinstance(value, str):
        return _expand_env_in_string(value)
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def load_config(config_path: Optional[str] = None) -> RouterConfig:
    """
    Load router configuration from YAML file.

    Args:
        config_path: Path to YAML config file. If None, uses default config.yaml.

    Returns:
        RouterConfig object

    Raises:
        ConfigurationError: If config file not found or invalid
    """
    if config_path is None:
        config_path = "config.yaml"

    config_file = Path(config_path)
    if not config_file.exists():
        raise ConfigurationError(f"Config file not found: {config_path}")

    try:
        with open(config_file) as f:
            config_data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Failed to parse YAML config: {e}")
    except IOError as e:
        raise ConfigurationError(f"Failed to read config file: {e}")

    # Resolve ``${VAR}`` / ``${VAR:-default}`` references everywhere in the
    # config so secrets like API keys can be supplied via the environment.
    config_data = _expand_env_vars(config_data)

    # Build RouterConfig from dict
    return _build_router_config(config_data)


def _build_router_config(config_data: dict) -> RouterConfig:
    """Build RouterConfig from parsed YAML dict."""
    # Parse providers
    providers = []
    for provider_data in config_data.get("providers", []):
        provider = _build_provider_config(provider_data)
        providers.append(provider)

    # Parse plugins - organized by prerouting/postrouting/postresponse sections
    plugins = []
    plugins_data = config_data.get("plugins") or {}

    for plugin_data in plugins_data.get("prerouting") or []:
        plugin = _build_plugin_config(plugin_data, trigger="prerouting")
        plugins.append(plugin)

    for plugin_data in plugins_data.get("postrouting") or []:
        plugin = _build_plugin_config(plugin_data, trigger="postrouting")
        plugins.append(plugin)

    # Parse postresponse plugins
    for plugin_data in plugins_data.get("postresponse") or []:
        plugin = _build_plugin_config(plugin_data, trigger="postresponse")
        plugins.append(plugin)

    # Parse routing
    routing_data = config_data.get("routing", {})
    routing = RoutingConfig(
        policy=routing_data.get("policy"),
        strategy=routing_data.get("strategy"),
    )

    # Parse telemetry
    telemetry_data = config_data.get("telemetry", {})
    backend = telemetry_data.get("backend", "memory")
    try:
        backend_enum = TelemetryBackendType(backend)
    except ValueError:
        raise ConfigurationError(f"Invalid telemetry backend: {backend}")

    telemetry = TelemetryConfig(
        backend=backend_enum,
        file_path=telemetry_data.get("file_path"),
        enabled=telemetry_data.get("enabled", True),
    )

    # Build final config
    router_config = RouterConfig(
        providers=providers,
        plugins=plugins,
        routing=routing,
        telemetry=telemetry,
        log_level=config_data.get("log_level", "INFO"),
        cors_origins=config_data.get("cors_origins", ["*"]),
    )

    return router_config


def _build_provider_config(provider_data: dict) -> ProviderConfig:
    """Build ProviderConfig from dict."""
    name = provider_data.get("name")
    if not name:
        raise ConfigurationError("Provider must have a 'name'")

    provider_type = provider_data.get("type")
    if not provider_type:
        raise ConfigurationError(f"Provider '{name}' must have a 'type'")

    model = provider_data.get("model")
    if not model:
        raise ConfigurationError(f"Provider '{name}' must have a 'model'")

    return ProviderConfig(
        name=name,
        type=provider_type,
        model=model,
        enabled=provider_data.get("enabled", True),
        metadata=provider_data.get("metadata", {}),
        settings=provider_data.get("settings", {}),
    )


def _build_plugin_config(plugin_data: dict, trigger: str = "prerouting") -> PluginConfig:
    """Build PluginConfig from dict.
    
    Args:
        plugin_data: Plugin configuration dict
        trigger: Plugin trigger phase - 'prerouting', 'postrouting', or 'postresponse'
    
    Raises:
        ConfigurationError: If required fields missing or invalid
    """
    if trigger not in {"prerouting", "postrouting", "postresponse"}:
        raise ConfigurationError(
            "Invalid plugin trigger: "
            f"{trigger}. Allowed values are 'prerouting', 'postrouting', and 'postresponse'"
        )
    
    name = plugin_data.get("name")
    if not name:
        raise ConfigurationError("Plugin must have a 'name'")

    plugin_node = plugin_data.get("node")
    if not plugin_node:
        raise ConfigurationError(f"Plugin '{name}' must have a 'node'")

    return PluginConfig(
        name=name,
        node=plugin_node,
        enabled=plugin_data.get("enabled", True),
        trigger=trigger,
        nodes=plugin_data.get("nodes", []),
        settings=plugin_data.get("settings", {}),
    )
