# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Path

from api.schema import (
    PipelineDefinitionResponse,
    PipelineStatusResponse,
    PipelineSummaryResponse,
    StartNamedPipelineRequest,
    StartPipelineRequest,
    StartPipelineResponse,
    StopPipelineResponse,
)
from config.compat import apply_destination, apply_source
from config.converter import build_pipeline_string
from config.models import LegacyConfig
from core.pipeline_manager import PipelineManager

logger = logging.getLogger(__name__)

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


def start_named_pipeline(
    pipeline_cfg,
    *,
    name: str,
    version: str,
    request: StartNamedPipelineRequest,
) -> str:
    """Build a concrete pipeline string from a config entry + request body and start it.

    Shared by the ``POST /pipelines/{name}/{version}`` route and by
    :func:`autostart_pipelines` (server-startup autostart), so both go through
    the exact same source/destination/parameters translation.
    """
    pipeline_str = build_pipeline_string(pipeline_cfg, parameters=request.parameters)
    pipeline_str = apply_source(pipeline_str, request.source)
    pipeline_str = apply_destination(pipeline_str, request.destination)
    return _get_manager().start(
        pipeline_str,
        name=name,
        version=version,
        request=request.model_dump(exclude_none=True),
    )


def autostart_pipelines() -> None:
    """Start every config.json pipeline with ``auto_start: true`` (legacy parity).

    Called once from the app's startup lifespan, after :func:`set_legacy_config`.
    Each pipeline's optional ``payload`` field (source/destination/parameters/tags)
    is used as the request body, exactly as if it had been POSTed to
    ``/pipelines/{name}/{version}``. A pipeline that fails to start (e.g. bad
    payload, validation failure) is logged and skipped rather than aborting
    server startup or the remaining autostart pipelines.
    """
    if _legacy_config is None:
        return

    for pipeline_cfg in _legacy_config.pipelines:
        if not pipeline_cfg.auto_start:
            continue
        try:
            request = StartNamedPipelineRequest.model_validate(pipeline_cfg.payload or {})
            instance_id = start_named_pipeline(
                pipeline_cfg,
                name="user_defined_pipelines",
                version=pipeline_cfg.name,
                request=request,
            )
            logger.info(
                "Autostarted pipeline %r as instance %s", pipeline_cfg.name, instance_id
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to autostart pipeline %r", pipeline_cfg.name)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[PipelineDefinitionResponse])
async def list_pipelines():
    """Return the loaded pipeline definitions from config.json (legacy API parity).

    This is the pipeline "catalog" — the named pipelines available to start via
    ``POST /pipelines/{name}/{version}`` — NOT running instances. See
    ``GET /pipelines/status`` for the list of pipeline instances and their state.
    """
    if _legacy_config is None:
        return []
    return [
        {
            "name": "user_defined_pipelines",
            "version": pipeline_cfg.name,
            "type": "gstreamer",
            "parameters": (
                pipeline_cfg.parameters.model_dump() if pipeline_cfg.parameters else None
            ),
        }
        for pipeline_cfg in _legacy_config.pipelines
    ]


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
    return [i.to_status_dict() for i in _get_manager().list_all()]


@router.get("/{instance_id}", response_model=PipelineSummaryResponse)
async def get_pipeline(instance_id: str = Path(..., description="Pipeline instance identifier")):
    """Return details (status + pipeline config) for a specific pipeline instance."""
    instance = _get_manager().get(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id!r} not found")
    return instance.to_dict()


@router.get("/{instance_id}/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(instance_id: str = Path(..., description="Pipeline instance identifier")):
    """Return status only (no pipeline config) for a specific pipeline instance."""
    instance = _get_manager().get(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id!r} not found")
    return instance.to_status_dict()


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

    instance_id = start_named_pipeline(pipeline_cfg, name=name, version=version, request=request)
    return {"instance_id": instance_id}


