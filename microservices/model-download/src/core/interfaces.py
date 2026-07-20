# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

class DownloadTask:
    """
    Represents a sub-task in a model download process.
    Used for parallel downloading of model files.
    """
    def __init__(self, file_id: str, url: str, destination: str):
        self.file_id = file_id
        self.url = url
        self.destination = destination


@dataclass(frozen=True)
class PluginConfigKey:
    """
    Declares one configuration value a plugin consumes.

    A configuration key maps to an environment variable of the same ``name``.
    Callers may override it per request; the environment variable stays as the
    fallback default. Keys flagged ``sensitive`` (tokens/passwords) must never
    be logged. Keys sharing a ``group`` are resolved together: if a request
    overrides any key in the group, the whole group is taken from the request
    (env values are not mixed in), and every ``required`` key in that group
    must be supplied.
    """
    name: str
    description: str = ""
    sensitive: bool = False
    required: bool = False
    group: Optional[str] = None


class ListingNotSupportedError(NotImplementedError):
    """Raised when a hub/plugin does not support listing models."""


class ListingAuthError(Exception):
    """Raised when listing fails because credentials are missing or invalid."""

class ModelDownloadPlugin(ABC):
    @property
    def plugin_name(self) -> str:
        """Return the name of the plugin"""
        return self.__class__.__name__.lower()
        
    @property
    def plugin_type(self) -> str:
        """Return the type of the plugin (downloader/converter)"""
        return "downloader"
    
    def can_handle(self, model_name: str,hub: str, **kwargs) -> bool:
        """
        Check if this plugin can handle the given model name.
        Plugins should override this to implement their specific logic.
        """
        return False

    def config_keys(self) -> List[PluginConfigKey]:
        """
        Return the connection/configuration keys this plugin consumes.

        Each key can be overridden per request; the matching environment
        variable is the fallback default. Plugins that need credentials or
        external-service settings override this so the keys are discoverable
        through GET /plugins and eligible for per-request overrides for free.
        """
        return []

    def resolve_config(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Resolve this plugin's declared config keys for a single request.

        Per-request ``overrides`` win over environment variables (the fallback).
        The returned mapping is a fresh local dict scoped to the caller, so
        values never persist globally or leak between requests. Unknown keys are
        rejected, and grouped keys are resolved together (see PluginConfigKey).
        """
        overrides = overrides or {}
        declared = {key.name: key for key in self.config_keys()}

        # Reject any override key the plugin does not understand.
        for name in overrides:
            if name not in declared:
                allowed = ", ".join(sorted(declared)) or "(none)"
                raise ValueError(
                    f"Unknown override key '{name}' for plugin '{self.plugin_name}'. "
                    f"Allowed keys: {allowed}."
                )

        # Groups that the request is overriding (any member supplied).
        touched_groups = {
            declared[name].group
            for name in overrides
            if overrides[name] is not None and declared[name].group
        }

        resolved: Dict[str, Any] = {}
        for key in self.config_keys():
            if key.name in overrides and overrides[key.name] is not None:
                resolved[key.name] = overrides[key.name]
            elif key.group and key.group in touched_groups:
                # The group is being overridden; never mix in the env value.
                if key.required:
                    raise ValueError(
                        f"When overriding '{key.group}' credentials, '{key.name}' "
                        f"must also be provided in the request."
                    )
                continue
            else:
                env_value = os.environ.get(key.name)
                if env_value is not None:
                    resolved[key.name] = env_value
        return resolved

    @property
    def supports_listing(self) -> bool:
        """Whether this plugin can list models available on its hub."""
        return False

    @property
    def listing_filter_fields(self) -> List[str]:
        """Filter fields supported by ``list_models`` for this plugin."""
        return []

    def _validate_listing_filters(self, filters: Optional[Dict[str, Any]]) -> None:
        """Reject any filter key not declared in ``listing_filter_fields``.

        Plugins with a fixed set of supported filters should call this at the
        start of ``list_models`` so unsupported keys fail loudly (raising
        ValueError) instead of being silently ignored.
        """
        if not filters:
            return
        allowed = set(self.listing_filter_fields)
        unknown = [key for key in filters if key not in allowed]
        if unknown:
            allowed_list = ", ".join(sorted(allowed)) or "(none)"
            raise ValueError(
                f"Unsupported filter(s): {', '.join(sorted(unknown))}. "
                f"Allowed filter(s): {allowed_list}."
            )

    def list_models(self, filters: Optional[Dict[str, Any]] = None, limit: int = 50, offset: int = 0, **kwargs) -> Dict[str, Any]:
        """
        List models available on this hub.

        Args:
            filters: Hub-specific filters (e.g. author/owner, search).
            limit: Maximum number of models to return.
            offset: Number of models to skip (pagination).

        Returns:
            A dict with ``items`` (list of model dicts) and ``total`` (int or None).

        Raises:
            ListingNotSupportedError: If the plugin does not support listing.
            ListingAuthError: If credentials are missing or invalid.
        """
        raise ListingNotSupportedError(
            f"Plugin '{self.plugin_name}' does not support listing models"
        )
        
    def get_download_tasks(self, model_name: str, **kwargs) -> List[DownloadTask]:
        """
        Get list of download tasks for a model.
        Used for parallel downloading.
        """
        raise NotImplementedError("This plugin does not support task-based downloading")
    
    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        """
        Download a single task file.
        Used for parallel downloading.
        """
        raise NotImplementedError("This plugin does not support task-based downloading")
    
    async def post_process(self, model_name: str, output_dir: str, downloaded_paths: List[str], **kwargs) -> Dict[str, Any]:
        """
        Post-process downloaded files.
        Called after all files have been downloaded.
        """
        # Default implementation just returns basic info
        return {
            "model_name": model_name,
            "download_path": output_dir,
            "success": True
        }
    
    @abstractmethod
    async def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        pass