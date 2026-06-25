# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""v1 API endpoints.

These handlers replace the legacy ``src.router.gateway`` endpoints. State is
read from ``http_request.app.state`` (router, plugin_manager, telemetry,
config, verbose flags, log_dir) — no module-level globals.
"""

import logging
import time
import traceback
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.api.concurrency import concurrency_guard
from src.api.v1._chat_helpers import (
    new_request_id,
    record_request_telemetry,
    stream_chat_completions,
)
from src.exceptions import RoutingError
from src.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    PluginConfigUpdateRequest,
    PluginListResponse,
    PluginResponse,
    PluginSettingsResponse,
)
from src.router.logging_utils import (
    is_verbose_full_enabled,
    log_to_gateway_file,
    log_verbose_response,
    sanitize_for_log,
)


logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Chat completions
# ---------------------------------------------------------------------------


@router.post(
    "/chat/completions",
    response_model=Optional[ChatCompletionResponse],
    dependencies=[Depends(concurrency_guard)],
)
async def chat_completions(request: ChatCompletionRequest, http_request: Request):
    """OpenAI-compatible chat completions endpoint."""
    state = http_request.app.state
    orchestrator = state.router
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Router not initialized")

    telemetry = state.telemetry
    verbose = bool(getattr(state, "verbose", False))
    verbose_full = bool(getattr(state, "verbose_full", False))
    log_dir = getattr(state, "log_dir", None)

    request_id = new_request_id()

    logger.info(
        f"Request received: request_id={request_id}, "
        f"model={sanitize_for_log(request.model)}, "
        f"stream={request.stream}"
    )
    logger.debug(
        f"Request details: request_id={request_id}, "
        f"messages={len(request.messages)}, tools={bool(request.tools)}"
    )

    if request.stream:
        async def streaming_wrapper():
            async for chunk in stream_chat_completions(
                orchestrator,
                request,
                request_id,
                telemetry=telemetry,
                verbose=verbose,
                verbose_full=verbose_full,
                log_dir=log_dir,
            ):
                yield chunk

        return StreamingResponse(streaming_wrapper(), media_type="text/event-stream")

    # Non-streaming path
    try:
        if is_verbose_full_enabled(verbose_full):
            body_bytes = await http_request.body()
            raw_body = body_bytes.decode("utf-8", errors="replace")
            log_verbose_response("Raw request", raw_body, request_id, log_dir, verbose)
    except Exception as e:
        msg = f"[log error] Failed to log raw request: {e}"
        print(msg)
        log_to_gateway_file(msg, log_dir)

    try:
        start_time = time.time()
        chat_response, route_info = await orchestrator.chat(request)
        is_direct = route_info.is_direct
        final_provider_name = route_info.provider_name
        routing_reason = route_info.reason

        if is_direct:
            log_verbose_response(
                "Direct provider call",
                {"provider": request.model},
                request_id,
                log_dir,
                verbose,
            )

        total_latency_ms = (time.time() - start_time) * 1000
        log_verbose_response(
            "Raw backend response",
            chat_response.model_dump(),
            request_id,
            log_dir,
            verbose,
        )
    except RoutingError as routing_err:
        logger.error(f"Routing failed: request_id={request_id}, error={routing_err}")
        raise HTTPException(status_code=400, detail=str(routing_err))
    except HTTPException:
        raise
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"Inference error: request_id={request_id}, error={e}")
        logger.debug(f"Traceback: request_id={request_id}, traceback={error_detail}")
        log_verbose_response(
            "Non-streaming error",
            {"error": str(e), "traceback": error_detail},
            request_id,
            log_dir,
            verbose,
        )
        raise HTTPException(status_code=500, detail=f"Inference error (request_id={request_id})")

    # Forward the backend response untouched, only stamping the gateway's
    # request id so clients see a consistent identifier.
    chat_response.id = request_id

    if chat_response.usage is not None:
        try:
            record_request_telemetry(
                telemetry,
                request_id=request_id,
                model_name=chat_response.model,
                prompt_tokens=chat_response.usage.prompt_tokens,
                completion_tokens=chat_response.usage.completion_tokens,
                total_latency_ms=total_latency_ms,
                start_time=start_time,
                first_token_time=None,
                provider_name=final_provider_name,
                is_direct=is_direct,
                is_streaming=False,
            )
        except Exception as telemetry_error:
            logger.warning(
                f"Telemetry recording failed: request_id={request_id}, "
                f"error={telemetry_error}"
            )

    logger.info(
        f"Request completed: request_id={request_id}, "
        f"model={chat_response.model}, provider={final_provider_name}, "
        f"reason={routing_reason}, latency={total_latency_ms:.2f}ms"
    )

    return chat_response


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@router.get("/models")
async def list_models(http_request: Request):
    """List available models.

    One entry per enabled provider, where ``id`` is the backend model name
    (e.g. ``"Qwen/Qwen3.5-9B"``) and ``owned_by`` is the configured provider
    name. Two providers may expose the same ``id``; clients can disambiguate
    via ``owned_by`` and route to the specific provider by passing its name
    in ``request.model`` (legacy fallback path). Plus the ``auto`` virtual
    model that triggers automatic provider selection.
    """
    config = http_request.app.state.config
    if config is None:
        raise HTTPException(status_code=503, detail="Router not initialized")

    models = []
    for prov in config.providers:
        if not prov.enabled:
            continue
        models.append({
            "id": prov.model,
            "object": "model",
            "created": int(time.time()),
            "owned_by": prov.name,
        })

    models.append({
        "id": "auto",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "inference-router",
    })

    return {"object": "list", "data": models}


# ---------------------------------------------------------------------------
# Telemetry / metrics (formerly /v1/stats)
# ---------------------------------------------------------------------------


@router.get("/metrics")
async def get_metrics(http_request: Request):
    """Get statistics including token metrics, bucketed by provider name.

    Replaces the legacy ``/v1/stats`` endpoint. Shape unchanged.
    """
    telemetry = http_request.app.state.telemetry
    if telemetry is None:
        raise HTTPException(status_code=503, detail="Telemetry not initialized")

    metrics = telemetry.get_metrics()
    total_requests = metrics.total_requests
    total_tokens = metrics.total_tokens

    by_provider_tokens = {}
    by_provider_latency = {}
    distribution = {}
    for name, p in metrics.by_provider.items():
        distribution[name] = p.requests
        by_provider_tokens[name] = {
            "input_tokens": p.input_tokens,
            "output_tokens": p.output_tokens,
            "total_tokens": p.total_tokens,
            "request_count": p.requests,
            "avg_tokens_per_request": round(p.avg_tokens_per_request, 1),
            "request_share": round(p.requests / total_requests, 3) if total_requests else 0.0,
            "token_share": round(p.total_tokens / total_tokens, 3) if total_tokens else 0.0,
        }
        by_provider_latency[name] = {
            "avg_latency_ms": round(p.avg_latency_ms, 2),
            "avg_ttft_ms": round(p.avg_ttft_ms, 2),
            "avg_tpot_ms": round(p.avg_tpot_ms, 4),
            "ttft_count": p.ttft_count,
            "tpot_count": p.tpot_count,
        }

    return {
        "routing_stats": {
            "total_requests": total_requests,
            "by_provider": distribution,
        },
        "token_metrics": {
            "by_provider": by_provider_tokens,
            "overall": {
                "total_tokens": total_tokens,
                "total_input_tokens": metrics.total_input_tokens,
                "total_output_tokens": metrics.total_output_tokens,
                "total_requests": total_requests,
                "avg_tokens_per_request": round(metrics.avg_tokens_per_request, 1),
            },
        },
        "latency_metrics": {
            "by_provider": by_provider_latency,
            "overall": {
                "avg_latency_ms": round(metrics.avg_latency_ms, 2),
                "avg_ttft_ms": round(metrics.avg_ttft_ms, 2),
                "avg_tpot_ms": round(metrics.avg_tpot_ms, 4),
                "ttft_count": metrics.ttft_count,
                "tpot_count": metrics.tpot_count,
            },
        },
    }


@router.post("/metrics/reset")
async def reset_metrics(http_request: Request):
    """Reset all telemetry metrics."""
    telemetry = http_request.app.state.telemetry
    if telemetry is None:
        raise HTTPException(status_code=503, detail="Telemetry not initialized")

    telemetry.reset()
    logger.info("Statistics metrics reset via API")

    return {
        "status": "success",
        "message": "All statistics metrics have been reset",
        "timestamp": int(time.time()),
    }


# ---------------------------------------------------------------------------
# Plugin configuration
# ---------------------------------------------------------------------------


@router.get("/plugins")
async def list_plugins(http_request: Request) -> PluginListResponse:
    """List all configured plugins."""
    plugin_manager = http_request.app.state.plugin_manager

    try:
        plugins_config = plugin_manager.get_all_plugins_config()
        plugins_response = []
        for config in plugins_config:
            plugin_resp = PluginResponse(
                name=config["name"],
                node=config["node"],
                enabled=config["enabled"],
                trigger=config["trigger"],
                settings=PluginSettingsResponse(**config["settings"]),
            )
            plugins_response.append(plugin_resp)

        return PluginListResponse(data=plugins_response)
    except Exception as e:
        logger.error(f"Failed to list plugins: {e}")
        raise HTTPException(status_code=500, detail="Failed to list plugins")


@router.get("/plugins/{name}/{node}")
async def get_plugin(name: str, node: str, http_request: Request) -> PluginResponse:
    """Get plugin configuration by name and node type."""
    plugin_manager = http_request.app.state.plugin_manager

    try:
        plugin = plugin_manager.get_plugin_by_name_and_node(name, node)
        if not plugin:
            raise HTTPException(
                status_code=404,
                detail=f"Plugin '{name}' with node '{node}' not found",
            )

        return PluginResponse(
            name=plugin.name,
            node=plugin.plugin_type(),
            enabled=True,
            trigger=plugin.trigger,
            settings=PluginSettingsResponse(
                extra_config=getattr(plugin.parsed_settings, "extra_config", {})
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get plugin {name}/{node}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get plugin configuration")


@router.put("/plugins/{name}/{node}")
async def update_plugin(
    name: str, node: str, update_req: PluginConfigUpdateRequest, http_request: Request
) -> PluginResponse:
    """Update plugin configuration by name and node type."""
    plugin_manager = http_request.app.state.plugin_manager

    try:
        plugin = plugin_manager.get_plugin_by_name_and_node(name, node)
        if not plugin:
            raise HTTPException(
                status_code=404,
                detail=f"Plugin '{name}' with node '{node}' not found",
            )

        if update_req.settings:
            new_settings = update_req.settings.model_dump(exclude_unset=True)
            if not plugin_manager.update_plugin_settings(name, node, new_settings):
                raise HTTPException(status_code=500, detail="Failed to update plugin settings")

        return PluginResponse(
            name=plugin.name,
            node=plugin.plugin_type(),
            enabled=True,
            trigger=plugin.trigger,
            settings=PluginSettingsResponse(
                extra_config=getattr(plugin.parsed_settings, "extra_config", {})
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update plugin {name}/{node}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update plugin configuration")


@router.post("/plugins/{name}/{node}")
async def create_or_update_plugin(
    name: str, node: str, update_req: PluginConfigUpdateRequest, http_request: Request
) -> PluginResponse:
    """Create or update plugin configuration by name and node type."""
    plugin_manager = http_request.app.state.plugin_manager

    try:
        plugin = plugin_manager.get_plugin_by_name_and_node(name, node)
        if plugin:
            if update_req.settings:
                new_settings = update_req.settings.model_dump(exclude_unset=True)
                if not plugin_manager.update_plugin_settings(name, node, new_settings):
                    raise HTTPException(status_code=500, detail="Failed to update plugin settings")

            return PluginResponse(
                name=plugin.name,
                node=plugin.plugin_type(),
                enabled=True,
                trigger=plugin.trigger,
                settings=PluginSettingsResponse(
                    extra_config=getattr(plugin.parsed_settings, "extra_config", {})
                ),
            )

        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{name}' with node '{node}' not found",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create/update plugin {name}/{node}: {e}")
        raise HTTPException(status_code=500, detail="Failed to configure plugin")
