# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""v1 configuration management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from src.api.v1._config_runtime import (
    apply_and_persist_config,
    config_warnings,
    redact_sensitive_values,
    resolve_config_path,
    serialize_router_config,
)
from src.models import (
    ConfigResponse,
    RoutingConfigResponse,
    RoutingConfigUpdateRequest,
)


logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/config", response_model=ConfigResponse)
async def get_config(http_request: Request) -> ConfigResponse:
    """Return the current in-memory router configuration."""
    config = getattr(http_request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Router not initialized")

    config_data = serialize_router_config(config)
    config_path = getattr(http_request.app.state, "config_path", None)
    return ConfigResponse(
        data=redact_sensitive_values(config_data),
        path=str(config_path) if config_path is not None else None,
        warnings=config_warnings(config_data),
    )


@router.get("/routing", response_model=RoutingConfigResponse)
async def get_routing(http_request: Request) -> RoutingConfigResponse:
    """Return the current routing policy."""
    config = getattr(http_request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Router not initialized")

    return RoutingConfigResponse(policy=config.routing.policy)


@router.post("/routing", response_model=RoutingConfigResponse)
async def update_routing(
    update_req: RoutingConfigUpdateRequest, http_request: Request
) -> RoutingConfigResponse:
    """Update the routing policy, rebuild the runtime, and persist to disk.

    Only ``policy`` is managed here; an existing ``strategy`` value is preserved.
    An unknown policy name is rejected (the runtime rebuild validates it against
    ``policy.yaml``). The routing section carries no secrets, so — like the
    plugins API — it is overlaid onto the raw on-disk document, leaving provider
    ``${VAR}`` placeholders intact.
    """
    try:
        async with http_request.app.state.config_lock:
            config = getattr(http_request.app.state, "config", None)
            if config is None:
                raise HTTPException(status_code=503, detail="Router not initialized")

            routing: dict = {
                "policy": update_req.policy
                if update_req.policy is not None
                else config.routing.policy,
            }
            # Preserve an existing strategy fallback without injecting a null key
            # into the on-disk config when it isn't set.
            if config.routing.strategy is not None:
                routing["strategy"] = config.routing.strategy

            config_data = serialize_router_config(config)
            config_data["routing"] = routing

            updated_config = await apply_and_persist_config(
                http_request,
                config_data,
                config_path=resolve_config_path(http_request),
                persist_overlay={"routing": routing},
            )
        return RoutingConfigResponse(policy=updated_config.routing.policy)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update routing config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update routing configuration")
