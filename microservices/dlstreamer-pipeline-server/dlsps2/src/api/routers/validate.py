# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Path

from api.schema import ValidateRequest, ValidateResponse, ValidationStatus
from core.pipeline_manager import PipelineManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/validate", tags=["validation"])

_pipeline_manager: Optional[PipelineManager] = None


def set_pipeline_manager(manager: PipelineManager) -> None:
    global _pipeline_manager
    _pipeline_manager = manager


def _get_manager() -> PipelineManager:
    if _pipeline_manager is None:
        raise HTTPException(status_code=503, detail="Pipeline manager not initialized")
    return _pipeline_manager


@router.post("", response_model=ValidateResponse)
async def validate_pipeline(request: ValidateRequest):
    """Validate a GStreamer pipeline without starting it.

    Runs the pipeline through the validator in the background and returns
    a validation_id immediately. Poll GET /validate/status/{validation_id}
    to get the result.
    """
    if not request.pipeline.strip():
        raise HTTPException(status_code=400, detail="pipeline must not be empty")
    validation_id = _get_manager().validate(request.pipeline, request.timeout)
    return {"validation_id": validation_id}


@router.get("/status", response_model=list[ValidationStatus])
async def list_validations():
    """Return the status of all validation requests."""
    return [
        {
            "validation_id": v.validation_id,
            "state": v.state.value,
            "message": v.message or "",
        }
        for v in _get_manager().list_validations()
    ]


@router.get("/status/{validation_id}", response_model=ValidationStatus)
async def get_validation_status(validation_id: str = Path(..., description="Validation request identifier")):
    """Return the status of a specific validation request."""
    validation = _get_manager().get_validation(validation_id)
    if not validation:
        raise HTTPException(status_code=404, detail=f"Validation {validation_id!r} not found")
    return {
        "validation_id": validation.validation_id,
        "state": validation.state.value,
        "message": validation.message or "",
    }
