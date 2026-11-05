# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Path

from api.schema import (
    OptimizeRequest,
    OptimizeResponse,
    OptimizeResultResponse,
    OptimizeStatusResponse,
)
from core.optimizer_manager import OptimizerBusyError, OptimizerManager

router = APIRouter(prefix="/optimize", tags=["optimization"])

_optimizer_manager: Optional[OptimizerManager] = None


def set_optimizer_manager(manager: OptimizerManager) -> None:
    global _optimizer_manager
    _optimizer_manager = manager


def _get_manager() -> OptimizerManager:
    if _optimizer_manager is None:
        raise HTTPException(status_code=503, detail="Optimizer manager not initialized")
    return _optimizer_manager


def _get_job(job_id: str):
    job = _get_manager().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Optimizer job {job_id} not found")
    return job


@router.post("", response_model=OptimizeResponse)
async def start_optimization(request: OptimizeRequest):
    """Start an asynchronous pipeline optimization job.

    Only one optimizer job may run at a time (409 otherwise). Do not run
    optimization while other pipelines are running, because their load skews
    the measured FPS.
    """
    if not request.pipeline.strip():
        raise HTTPException(status_code=400, detail="pipeline must not be empty")
    try:
        job_id = _get_manager().submit(
            request.pipeline,
            search_duration=request.search_duration,
            sample_duration=request.sample_duration,
            allowed_devices=request.allowed_devices,
        )
    except OptimizerBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"job_id": job_id}


@router.get("/status", response_model=List[OptimizeStatusResponse])
async def list_optimization_status():
    """Return the status of all optimizer jobs."""
    return [job.status_dict() for job in _get_manager().list_jobs()]


@router.get("/status/{job_id}", response_model=OptimizeStatusResponse)
async def get_optimization_status(job_id: str = Path(..., description="Optimizer job ID")):
    """Return the progress of an optimizer job."""
    return _get_job(job_id).status_dict()


@router.get("/result/{job_id}", response_model=OptimizeResultResponse)
async def get_optimization_result(job_id: str = Path(..., description="Optimizer job ID")):
    """Return the optimizer result.

    While the job is running (``final`` is false) the best pipeline found so far
    and the candidates evaluated so far are returned as partial results.
    """
    return _get_job(job_id).result_dict()


@router.delete("/{job_id}")
async def cancel_optimization(job_id: str = Path(..., description="Optimizer job ID")):
    """Cancel a running optimizer job. Partial results remain available via /optimize/result/{job_id}."""
    _get_job(job_id)
    if not _get_manager().cancel(job_id):
        raise HTTPException(status_code=409, detail=f"Optimizer job {job_id} is not running")
    return {"job_id": job_id, "message": "cancel requested"}
