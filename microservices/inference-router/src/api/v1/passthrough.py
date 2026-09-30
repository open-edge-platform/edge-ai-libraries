# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""v1 pass-through endpoints.

One POST route is generated per entry in ``PASSTHROUGH_SERVICES`` (the registry
in :mod:`src.providers.passthrough_provider`). Each route forwards the request
verbatim to the pass-through provider configured for that service and returns
its response untouched — audio transcription/speech, embeddings, rerank, OCR.

The backing provider is looked up per-request from the live orchestrator
(``app.state.router``), so enabling/disabling a provider via the ``/v1/providers``
API takes effect immediately (absent → 404). All routes are gated by
``concurrency_guard`` so they share the global ``max_concurrency`` limit with
``/v1/chat/completions``. Adding a new service kind is a single registry entry —
this module needs no change.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.concurrency import concurrency_guard
from src.providers import PASSTHROUGH_SERVICES


logger = logging.getLogger(__name__)
router = APIRouter()


def _make_handler(service: str):
    """Build the request handler bound to a specific service name."""

    async def handler(http_request: Request):
        orchestrator = getattr(http_request.app.state, "router", None)
        if orchestrator is None:
            raise HTTPException(status_code=503, detail="Router not initialized")

        provider = orchestrator.passthrough_for(service)
        if provider is None:
            raise HTTPException(
                status_code=404, detail=f"{service} service not configured"
            )
        return await provider.forward(http_request)

    return handler


# Register one route per service from the registry.
for _service, _spec in PASSTHROUGH_SERVICES.items():
    router.add_api_route(
        _spec.route,
        _make_handler(_service),
        methods=["POST"],
        name=f"passthrough_{_service}",
        summary=f"{_service} pass-through",
        dependencies=[Depends(concurrency_guard)],
    )
