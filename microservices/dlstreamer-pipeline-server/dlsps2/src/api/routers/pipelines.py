# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Optional

from fastapi import APIRouter, HTTPException, Path

from api.schema import (
    PipelineStatusResponse,
    StartNamedPipelineRequest,
    StartPipelineRequest,
    StartPipelineResponse,
    StopPipelineResponse,
)
from config.compat import apply_destination, apply_source
from config.converter import build_pipeline_string
from config.models import LegacyConfig
from core.pipeline_manager import PipelineManager

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

_pipeline_manager: Optional[PipelineManager] = None
_legacy_config: Optional[LegacyConfig] = None


def set_pipeline_manager(manager: PipelineManager) -> None:
    global _pipeline_manager
    _pipeline_manager = manager


def set_legacy_config(config: LegacyConfig) -> None:
    global _legacy_config
    _legacy_config = config


def _get_manager() -> PipelineManager:
    if _pipeline_manager is None:
        raise HTTPException(status_code=503, detail="Pipeline manager not initialized")
    return _pipeline_manager


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[PipelineStatusResponse])
async def list_pipelines():
    """Return all pipeline instances and their current state."""
    return [i.to_dict() for i in _get_manager().list_all()]


@router.post("", status_code=200, response_model=StartPipelineResponse)
async def run_pipeline(request: StartPipelineRequest):
    """Start a new pipeline instance from an inline GStreamer pipeline description."""
    if not request.pipeline.strip():
        raise HTTPException(status_code=400, detail="pipeline must not be empty")
    instance_id = _get_manager().start(request.pipeline)
    return {"instance_id": instance_id}


@router.get("/status", response_model=list[PipelineStatusResponse])
async def list_pipelines_status():
    """Return status of all pipeline instances."""
    return [i.to_dict() for i in _get_manager().list_all()]


@router.get("/{instance_id}", response_model=PipelineStatusResponse)
async def get_pipeline(instance_id: str = Path(..., description="Pipeline instance identifier")):
    """Return details for a specific pipeline instance."""
    instance = _get_manager().get(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id!r} not found")
    return instance.to_dict()


@router.get("/{instance_id}/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(instance_id: str = Path(..., description="Pipeline instance identifier")):
    """Return status for a specific pipeline instance."""
    instance = _get_manager().get(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id!r} not found")
    return instance.to_dict()


@router.delete("/{instance_id}", response_model=StopPipelineResponse)
async def stop_pipeline(instance_id: str = Path(..., description="Pipeline instance identifier")):
    """Stop a running pipeline instance."""
    manager = _get_manager()
    instance = manager.get(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id!r} not found")
    stopped = manager.stop(instance_id)
    if not stopped:
        raise HTTPException(
            status_code=409,
            detail=f"Instance {instance_id!r} is not running (state: {instance.state.value})",
        )
    return {"instance_id": instance_id}


# ---------------------------------------------------------------------------
# Legacy named-pipeline API  —  POST /pipelines/{name}/{version}
# ---------------------------------------------------------------------------

@router.post("/{name}/{version}", status_code=200, response_model=StartPipelineResponse)
async def run_named_pipeline(
    request: StartNamedPipelineRequest,
    name: str = Path(..., description="Pipeline name"),
    version: str = Path(..., description="Pipeline version (matches config 'name' field)"),
):
    """Start a named pipeline from config.json.

    Looks up the pipeline by *name* (always ``user_defined_pipelines``) and
    *version* (the pipeline's ``name`` field in config.json), builds a
    concrete GStreamer pipeline string from the config plus any ``parameters``
    supplied in the request body, then starts it.
    """
    if _legacy_config is None:
        raise HTTPException(status_code=503, detail="No config.json loaded — named pipeline API unavailable")

    pipeline_cfg = _legacy_config.get_pipeline(version)
    if pipeline_cfg is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline {version!r} not found in config (name={name!r})",
        )

    pipeline_str = build_pipeline_string(pipeline_cfg, parameters=request.parameters)
    pipeline_str = apply_source(pipeline_str, request.source)
    pipeline_str = apply_destination(pipeline_str, request.destination)
    instance_id = _get_manager().start(pipeline_str)
    return {"instance_id": instance_id}


@router.post("/{name}/{version}/{instance_id}", status_code=200, response_model=StartPipelineResponse)
async def update_named_pipeline_instance(
    request: StartNamedPipelineRequest,
    name: str = Path(..., description="Pipeline name"),
    version: str = Path(..., description="Pipeline version"),
    instance_id: str = Path(..., description="Pipeline instance identifier"),
):
    """Re-queue a named pipeline on an existing instance slot (legacy DLSPS API).

    Stops the existing instance if running, then starts a new one with the
    updated parameters, reusing the same instance_id is not supported —
    returns the new instance_id.
    """
    if _legacy_config is None:
        raise HTTPException(status_code=503, detail="No config.json loaded — named pipeline API unavailable")

    pipeline_cfg = _legacy_config.get_pipeline(version)
    if pipeline_cfg is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline {version!r} not found in config (name={name!r})",
        )

    manager = _get_manager()
    # Stop existing instance if it is still running
    manager.stop(instance_id)

    pipeline_str = build_pipeline_string(pipeline_cfg, parameters=request.parameters)
    pipeline_str = apply_source(pipeline_str, request.source)
    pipeline_str = apply_destination(pipeline_str, request.destination)
    new_id = manager.start(pipeline_str)
    return {"instance_id": new_id}


