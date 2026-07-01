# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Router orchestrator for managing providers and routing requests."""

import logging
from dataclasses import dataclass
from typing import AsyncIterator, List, Optional, Tuple

from src.config import RouterConfig, ProviderConfig
from src.models import ChatCompletionRequest, ChatCompletionResponse, ChatCompletionStreamChunk
from src.providers import create_provider, ProviderAdapter
from src.plugins import create_plugin_manager
from src.rsd.decision import DecisionEngine
from src.exceptions import ConfigurationError, RoutingError


logger = logging.getLogger(__name__)


# Sentinel ``request.model`` value that triggers DecisionEngine routing.
ROUTER_MODEL_NAME = "auto"


@dataclass
class RouteInfo:
    """Routing metadata for a completed request, surfaced to the caller."""

    provider_name: str
    reason: str
    # ``True`` when ``request.model`` named a configured provider directly,
    # ``False`` when DecisionEngine picked the provider.
    is_direct: bool


class RouterOrchestrator:
    """Main router orchestrator for managing providers and routing requests."""

    def __init__(
        self,
        config: RouterConfig,
        decision_engine: Optional[DecisionEngine] = None,
        telemetry=None,
    ):
        """
        Initialize router orchestrator.

        Args:
            config: RouterConfig with provider and routing settings
            decision_engine: DecisionEngine instance (default: built from config)
            telemetry: Optional telemetry recorder instance
        """
        self.config = config
        self.decision_engine = decision_engine or DecisionEngine.from_config(self.config.routing)
        self.telemetry = telemetry
        self.providers: List[ProviderAdapter] = []
        self.provider_map = {}  # provider_name -> provider
        # First-match map: backend model name (e.g. "Qwen/Qwen3.5-9B") → provider.
        # When two providers share a model, the earlier-configured one wins.
        # Routing checks model name first, then provider name (see _select_provider).
        self.model_to_provider = {}  # model_name -> provider
        self.plugin_manager = create_plugin_manager(self.config.plugins)

    async def initialize(self) -> None:
        """
        Initialize all configured providers.

        Raises:
            ConfigurationError: If no providers are configured
        """
        if not self.config.providers:
            raise ConfigurationError("No providers configured")

        for provider_config in self.config.providers:
            try:
                provider = create_provider(provider_config)
                if provider:
                    self.providers.append(provider)
                    self.provider_map[provider.name] = provider
                    # First-match wins: skip if another provider already claimed this model.
                    if provider_config.model not in self.model_to_provider:
                        self.model_to_provider[provider_config.model] = provider
                    else:
                        logger.info(
                            f"Model {provider_config.model!r} already mapped to "
                            f"provider {self.model_to_provider[provider_config.model].name!r}; "
                            f"{provider.name!r} reachable only by provider name."
                        )
                    logger.info(
                        f"Loaded provider: {provider.name} "
                        f"(type={provider_config.type}, model={provider_config.model})"
                    )
                else:
                    logger.info(f"Provider disabled: {provider_config.name}")
            except Exception as e:
                logger.error(f"Failed to load provider {provider_config.name}: {e}")
                raise

        if not self.providers:
            raise ConfigurationError("No enabled providers found after initialization")

        logger.info(f"Initialized {len(self.providers)} provider(s)")
        logger.info(
            "Initialized plugins: total=%d, prerouting=%d, postrouting=%d, postresponse=%d",
            len(self.plugin_manager.plugins),
            len(self.plugin_manager.prerouting_plugins),
            len(self.plugin_manager.postrouting_plugins),
            len(self.plugin_manager.postresponse_plugins),
        )

    async def _select_provider(
        self, request: ChatCompletionRequest
    ) -> Tuple[ProviderAdapter, RouteInfo, ChatCompletionRequest]:
        """Resolve which provider handles ``request`` and return it.

        Plugin processing (prerouting → postrouting) runs in both paths; only
        the DecisionEngine call is skipped when the client picked a provider
        by name or model:

        - ``request.model == "auto"`` → prerouting → DecisionEngine →
          postrouting. ``is_direct=False``.
        - ``request.model`` matches a configured backend model name (primary
          path) → prerouting → (skip DecisionEngine) → postrouting.
          ``is_direct=True``. Among providers sharing a model, the
          earlier-configured one wins.
        - ``request.model`` matches a configured provider name (fallback) →
          same as above. ``is_direct=True``.
        - otherwise → raise :class:`RoutingError`.

        Returns ``(provider, route_info, request)``. The request is returned
        because the prerouting/postrouting plugins may have replaced it.
        """
        request = await self.plugin_manager.process_prerouting_request(request)

        if request.model and request.model != ROUTER_MODEL_NAME:
            # Model name takes precedence; provider name is the legacy fallback.
            provider = self.model_to_provider.get(request.model)
            if provider is None:
                provider = self.provider_map.get(request.model)
            if provider is None:
                available_models = list(self.model_to_provider)
                available_providers = list(self.provider_map)
                raise RoutingError(
                    f"Unknown model: {request.model!r}. "
                    f"Available models: {available_models}, "
                    f"providers: {available_providers}, "
                    f"or use {ROUTER_MODEL_NAME!r} for automatic routing."
                )
            request = await self.plugin_manager.process_postrouting_request(request)
            return provider, RouteInfo(
                provider_name=provider.name,
                reason="direct_model_selection",
                is_direct=True,
            ), request

        # Routed path: DecisionEngine picks the provider.
        route_decision = await self.decision_engine.route(request, self.providers)
        request = await self.plugin_manager.process_postrouting_request(request)

        logger.debug(f"Route decision: {route_decision.reason}")
        return route_decision.provider, RouteInfo(
            provider_name=route_decision.provider.name,
            reason=route_decision.reason,
            is_direct=False,
        ), request

    async def chat(
        self, request: ChatCompletionRequest
    ) -> Tuple[ChatCompletionResponse, RouteInfo]:
        """Route ``request`` to a provider and return ``(response, route_info)``.

        Raises:
            RoutingError: If ``request.model`` doesn't match a known provider
                and isn't the ``"auto"`` sentinel.
            ProviderError: If the selected provider's call fails.
        """
        provider, route_info, request = await self._select_provider(request)
        response = await provider.chat(request)

        response = await self.plugin_manager.process_postresponse_response(response)

        if self.telemetry:
            await self._record_chat_event(request, response, route_info.provider_name)

        return response, route_info

    async def chat_stream(
        self, request: ChatCompletionRequest
    ) -> Tuple[AsyncIterator[ChatCompletionStreamChunk], RouteInfo]:
        """Route a streaming request and return ``(chunk_iter, route_info)``.

        The caller iterates the returned async iterator. Routing (including
        plugin processing) happens before the iterator is returned, so the
        caller knows up-front which provider handled the request.
        """
        provider, route_info, request = await self._select_provider(request)

        async def _iter():
            async for chunk in provider.chat_stream(request):
                yield chunk
            if self.telemetry:
                await self._record_chat_event(
                    request, None, route_info.provider_name, streaming=True
                )

        return _iter(), route_info

    async def list_models(self):
        """
        List available models from all providers.

        Returns:
            List of model dicts

        Raises:
            ProviderError: If provider request fails
        """
        all_models = []
        for provider in self.providers:
            try:
                models = await provider.list_models()
                all_models.extend(models)
            except Exception as e:
                logger.warning(f"Failed to list models from {provider.name}: {e}")

        return all_models

    async def health_check(self) -> dict:
        """
        Check health of all providers.

        Returns:
            Dict with health status for each provider
        """
        health_status = {}
        for provider in self.providers:
            try:
                is_healthy = await provider.health_check()
                health_status[provider.name] = {"healthy": is_healthy}
            except Exception as e:
                health_status[provider.name] = {"healthy": False, "error": str(e)}

        return health_status

    async def _record_chat_event(
        self,
        request: ChatCompletionRequest,
        response: Optional[ChatCompletionResponse],
        provider_name: str,
        streaming: bool = False,
    ) -> None:
        """
        Record a chat event in telemetry.

        Args:
            request: The request
            response: The response (None for streaming)
            provider_name: Name of provider used
            streaming: Whether this was a streaming request
        """
        # This will be enhanced when telemetry is implemented
        pass

    def shutdown(self) -> None:
        """Clean up provider resources."""
        # Can be extended for providers that need cleanup
        logger.info("Router orchestrator shutdown")
