# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Chat-completion helpers shared by the v1 endpoints.

The streaming generator and telemetry recorder are factored out of the
endpoint module so the route handlers stay readable. Both helpers are
parameterised on a ``Telemetry`` instance and the verbose-logging settings;
they do not read globals.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from src.exceptions import RoutingError
from src.models import ChatCompletionRequest
from src.observability import RequestCompletedEvent, Telemetry
from src.observability.token_accounting import TokenBreakdown, compute_token_breakdown
from src.router.logging_utils import log_verbose_response
from src.router.orchestrator import RouterOrchestrator


logger = logging.getLogger("gateway")


def record_request_telemetry(
    telemetry: Optional[Telemetry],
    *,
    request_id: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_latency_ms: float,
    start_time: float,
    first_token_time: float | None,
    forward_time: float | None = None,
    provider_name: str | None,
    is_direct: bool,
    is_streaming: bool = True,
    before_router: "TokenBreakdown | None" = None,
    after_router: "TokenBreakdown | None" = None,
) -> bool:
    """Record a ``RequestCompletedEvent``.

    ``route_path`` is set to ``"direct"`` when the client picked the provider
    by name, ``"routed"`` when DecisionEngine selected it. The function is a
    no-op (returns ``False``) when both token counts are zero or telemetry is
    not configured. ``before_router`` / ``after_router`` carry the token
    breakdown of the raw vs compressed request (same tiktoken unit).
    """
    if telemetry is None:
        return False
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return False

    if is_streaming:
        # Reported TTFT is vLLM-only: measured from forward_time (the instant
        # the upstream request is issued, after all pre-forward processing) to
        # the first token. Falls back to start_time if forward_time is absent.
        ttft_base = forward_time if forward_time is not None else start_time
        ttft_ms = (first_token_time - ttft_base) * 1000 if first_token_time is not None else None
        tpot_ms = None
        # TPOT = decode wall time / decode tokens. Decode time = final - first
        # token = total_latency_ms - (first_token - start_time); compute it from
        # start_time (not the reported ttft_ms) so excluding pre-forward time
        # from TTFT does not leak into TPOT. Needs at least 2 output tokens.
        if completion_tokens > 1 and first_token_time is not None:
            ttft_from_start_ms = (first_token_time - start_time) * 1000
            time_after_first_token = total_latency_ms - ttft_from_start_ms
            if time_after_first_token > 0:
                tpot_ms = time_after_first_token / (completion_tokens - 1)
    else:
        # Non-streaming: the client receives the whole response in one shot, so
        # there is no "first token" event and no per-token decode timing the
        # gateway can observe. TTFT/TPOT are streaming-only — leave them unset
        # so they don't pollute the averages with full-response latencies.
        ttft_ms = None
        tpot_ms = None

    telemetry.record_event(RequestCompletedEvent(
        request_id=request_id,
        route_path="direct" if is_direct else "routed",
        provider_name=provider_name or "unknown",
        models_used=[model_name],
        final_model=model_name,
        total_input_tokens=prompt_tokens,
        total_output_tokens=completion_tokens,
        before_router_system_tokens=before_router.system if before_router else 0,
        before_router_tool_tokens=before_router.tool if before_router else 0,
        before_router_context_tokens=before_router.context if before_router else 0,
        before_router_overall_tokens=before_router.overall if before_router else 0,
        after_router_system_tokens=after_router.system if after_router else 0,
        after_router_tool_tokens=after_router.tool if after_router else 0,
        after_router_context_tokens=after_router.context if after_router else 0,
        after_router_overall_tokens=after_router.overall if after_router else 0,
        total_latency_ms=total_latency_ms,
        ttft_ms=ttft_ms,
        tpot_ms=tpot_ms,
    ))

    logger.debug(
        f"Recorded telemetry: request_id={request_id}, provider={provider_name}, "
        f"input={prompt_tokens}, output={completion_tokens}"
        + (
            f", ttft={ttft_ms:.2f}ms, tpot={tpot_ms:.4f}ms"
            if ttft_ms is not None and tpot_ms is not None
            else ""
        )
    )
    return True


async def stream_chat_completions(
    orchestrator: RouterOrchestrator,
    request: ChatCompletionRequest,
    request_id: str,
    *,
    telemetry: Optional[Telemetry] = None,
    verbose: bool = False,
    verbose_full: bool = False,
    log_dir: Optional[Path] = None,
) -> AsyncIterator[str]:
    """Stream OpenAI-compatible SSE chunks for ``request``.

    The router forwards backend chunks verbatim — only the ``id`` is rewritten
    to the gateway's request id so clients see a consistent identifier across
    routed retries. Telemetry is recorded the first time any chunk carries
    ``usage`` (works whether the backend emits it on the final content chunk
    or as a separate empty-choices chunk).
    """
    if verbose_full:
        log_verbose_response(
            "Raw streaming request", request.model_dump(), request_id, log_dir, verbose
        )

    before_router = compute_token_breakdown(request)
    after_router: TokenBreakdown | None = None
    start_time = time.time()

    try:
        try:
            chunk_iter, route_info = await orchestrator.chat_stream(request)
            if route_info.processed_request is not None:
                # Same tiktoken unit as before_router → the delta is the saving.
                after_router = compute_token_breakdown(route_info.processed_request)
                if verbose_full:
                    log_verbose_response(
                        "Processed request",
                        route_info.processed_request.model_dump(),
                        request_id,
                        log_dir,
                        verbose,
                    )
        except RoutingError as routing_err:
            logger.error(f"Routing failed: request_id={request_id}, error={routing_err}")
            error_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "error",
                "choices": [{
                    "index": 0,
                    "delta": {"content": "[ERROR] Routing failed"},
                    "finish_reason": "error",
                }],
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"
            yield "data: [DONE]\n\n"
            return

        is_direct = route_info.is_direct
        final_provider_name: str | None = route_info.provider_name
        routing_reason: str | None = route_info.reason

        completion_logged = False
        telemetry_recorded = False
        final_model_name: str | None = None
        first_token_time: float | None = None

        async for raw_chunk in chunk_iter:
            chunk = raw_chunk.model_dump()

            if not final_model_name and chunk.get("model"):
                final_model_name = chunk["model"]

            # TTFT marker: first chunk that carries content or a tool_call delta.
            # Set this BEFORE recording telemetry so that a backend which emits
            # ``usage`` on the same chunk as the first content (rather than on a
            # trailing empty-choices chunk) still gets a valid TTFT.
            if first_token_time is None and chunk.get("choices"):
                delta = chunk["choices"][0].get("delta") or {}
                if delta.get("content") or delta.get("tool_calls"):
                    first_token_time = time.time()

            # Record telemetry on the first chunk carrying ``usage``. vLLM
            # emits it on the final content chunk; OpenAI puts it on a
            # separate empty-choices chunk when ``include_usage`` is set.
            if chunk.get("usage") and not telemetry_recorded:
                try:
                    usage_data = chunk["usage"]
                    telemetry_recorded = record_request_telemetry(
                        telemetry,
                        request_id=request_id,
                        model_name=final_model_name or final_provider_name or "unknown",
                        prompt_tokens=usage_data.get("prompt_tokens", 0),
                        completion_tokens=usage_data.get("completion_tokens", 0),
                        total_latency_ms=(time.time() - start_time) * 1000,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        forward_time=route_info.forward_time,
                        provider_name=final_provider_name,
                        is_direct=is_direct,
                        before_router=before_router,
                        after_router=after_router,
                    )
                except Exception as telemetry_error:
                    logger.warning(
                        f"Telemetry recording failed: request_id={request_id}, "
                        f"error={telemetry_error}"
                    )

            finish_reason = None
            if chunk.get("choices"):
                finish_reason = chunk["choices"][0].get("finish_reason")
            if finish_reason and not completion_logged:
                total_latency_ms = (time.time() - start_time) * 1000
                logger.info(
                    f"Streaming request completed: request_id={request_id}, "
                    f"provider={final_provider_name or 'unknown'}, "
                    f"model={final_model_name or 'unknown'}, "
                    f"reason={routing_reason or 'unknown'}, "
                    f"latency={total_latency_ms:.2f}ms"
                )
                completion_logged = True

            # Pass the backend chunk through, only stamping our request id.
            chunk["id"] = request_id
            log_verbose_response("Stream chunk", chunk, request_id, log_dir, verbose)
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0)

        yield "data: [DONE]\n\n"

    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"Streaming error: request_id={request_id}, error={e}")
        logger.debug(f"Traceback: request_id={request_id}, traceback={error_detail}")
        log_verbose_response(
            "Streaming error",
            {"error": str(e), "traceback": error_detail},
            request_id,
            log_dir,
            verbose,
        )

        error_chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "error",
            "choices": [{
                "index": 0,
                "delta": {"content": "[ERROR] Internal server error"},
                "finish_reason": "error",
            }],
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"


def new_request_id() -> str:
    """Generate a chat-completion request id matching the gateway's format."""
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"
