# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Base classes for request plugins."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional, Type

from pydantic import BaseModel, ValidationError

from src.models import ChatCompletionRequest, ChatCompletionResponse

if TYPE_CHECKING:
    from fastapi import APIRouter

logger = logging.getLogger(__name__)


class PluginSchemaError(ValueError):
    """Raised when plugin settings fail schema validation."""


class PluginBaseNode(ABC):
    """Base class for request-processing plugins.

    A plugin *type* (subclass) is keyed by :meth:`plugin_type` — the ``node`` in
    config and the API. Each config ``name`` is one instance of that type.
    """

    # Plugin family key. Plugins sharing a group are treated as one family
    plugin_group: str = ""

    def __init__(
        self,
        name: str,
        settings: Dict[str, Any],
        trigger: Literal["prerouting", "postrouting", "postresponse"] = "prerouting",
    ):
        self.name = name
        self.settings = settings
        self.trigger = trigger
        self.parsed_settings = self.validate_settings(settings)
        self.init()

    def init(self) -> None:
        """Hook for plugin-specific initialization.

        Called at the end of ``__init__`` once ``name``, ``settings``,
        ``trigger``, and ``parsed_settings`` are set. Override this to perform
        setup (build clients, register with shared managers, etc.) instead of
        reimplementing ``__init__`` and forwarding its arguments. Raise
        ``PluginSchemaError`` / ``ConfigurationError`` to reject bad config.
        Default: no-op.
        """

    @classmethod
    @abstractmethod
    def plugin_type(cls) -> str:
        """Unique plugin type key used in config."""

    @classmethod
    @abstractmethod
    def settings_model(cls) -> Type[BaseModel]:
        """Plugin-specific settings schema."""

    @classmethod
    def validate_settings(cls, settings: Dict[str, Any]) -> BaseModel:
        """Validate settings against plugin-specific schema."""
        model_cls = cls.settings_model()
        try:
            return model_cls(**settings)
        except ValidationError as exc:
            raise PluginSchemaError(
                f"Invalid settings for plugin type '{cls.plugin_type()}': {exc}"
            ) from exc

    @classmethod
    def node_metadata(cls) -> Dict[str, Any]:
        """Static type metadata for this node (single source of truth).

        Powers ``GET /plugins/nodes`` and the default :meth:`describe_node`.
        The settings schema is best-effort: a model that fails to produce a
        JSON schema degrades to ``{}`` rather than breaking the endpoint.
        """
        try:
            settings_schema = cls.settings_model().model_json_schema()
        except Exception:
            settings_schema = {}
        return {
            "node": cls.plugin_type(),
            "plugin_group": cls.plugin_group,
            "description": (cls.__doc__ or "").strip(),
            "settings_schema": settings_schema,
        }

    @classmethod
    def routes(cls) -> Optional["APIRouter"]:
        """Optional FastAPI router this plugin type contributes to the app.

        Opt-in extension point for the generic plugin endpoint registry: return
        an :class:`fastapi.APIRouter` and the app will mount it under ``/v1`` at
        startup (see ``src.api.app.create_app``). This lets a plugin expose its
        own HTTP API — e.g. metrics or admin endpoints — without any central
        edit to the API layer. Self-namespace the paths to avoid collisions,
        conventionally ``/plugins/{node}/...``. Called once per plugin *type*;
        the router is mounted a single time regardless of how many instances are
        configured. Default: ``None`` (contributes no routes).
        """
        return None

    @classmethod
    def describe_node(cls) -> Dict[str, Any]:
        """Payload returned by ``GET /plugins/{node}`` for this plugin type.

        Default: :meth:`node_metadata`. Override to expose node-level aggregate
        info spanning all instances of the type (e.g. a compressor family node
        returning ``{**node_metadata(), "metrics": ..., "cache_stats": ...}``).
        """
        return cls.node_metadata()

    async def process_request(
        self, request: ChatCompletionRequest, **kwargs: Any
    ) -> ChatCompletionRequest:
        """Process and return the (possibly modified) request.

        Default passthrough; override to act on the request. ``**kwargs``
        carries optional per-call context; subclasses may accept additional
        keyword arguments.
        """
        return request

    async def process_response(
        self, response: ChatCompletionResponse, **kwargs: Any
    ) -> ChatCompletionResponse:
        """Process and return the (possibly modified) response.

        Default passthrough; override to act on the response. ``**kwargs``
        carries optional per-call context.
        """
        return response

    def describe(self) -> Dict[str, Any]:
        """Payload returned by ``GET /plugins/{node}/{name}`` for this instance.

        Default: the instance's own view (``enabled`` is ``True`` because a live
        instance is by definition loaded). Override to fold in per-instance
        runtime info, typically ``{**super().describe(), "metrics": {...}}``.
        """
        return {
            "name": self.name,
            "node": self.plugin_type(),
            "trigger": self.trigger,
            "enabled": True,
            "settings": self.settings,
        }

    def reset(self) -> bool:
        """Reset this instance's own runtime state (e.g. per-instance metrics).

        Return ``True`` if reset, ``False`` if unsupported (the
        ``POST /plugins/{node}/{name}/reset`` endpoint surfaces ``False`` as a
        400). Default: unsupported.
        """
        return False

    @classmethod
    def reset_node(cls) -> bool:
        """Reset node-level (type/group-wide) state for this plugin type.

        Return ``True`` if reset, ``False`` if unsupported (the
        ``POST /plugins/{node}/reset`` endpoint surfaces ``False`` as a 400).
        Default: unsupported.
        """
        return False

    async def health_check(self) -> Dict[str, Any]:
        """Liveness/readiness probe for this plugin's dependencies.

        Default: **skipped**. The base class cannot know how to probe a concrete
        plugin's backing service, so rather than fabricate a healthy verdict it
        logs a warning and reports ``probe: "unavailable"``. Override this to
        perform a real probe (e.g. the compressor pings its Lingua/predictor
        server). Return at least ``{"healthy": bool}``; add detail keys
        (``state``, ``message``, …) as useful.
        """
        logger.warning("no health check probe available for plugin '%s'; skipping", self.name)
        return {
            "healthy": True,
            "probe": "unavailable",
            "message": "no health check probe available",
        }


# Backwards-compatibility alias for the pre-rename class name. ``PluginBaseNode``
# used to be called ``RequestPlugin``; modules synced from upstream (e.g.
# ``src/plugins/compressor.py``) still import the old name. Keep this shim so
# they load unmodified — remove once every caller uses ``PluginBaseNode``.
RequestPlugin = PluginBaseNode
