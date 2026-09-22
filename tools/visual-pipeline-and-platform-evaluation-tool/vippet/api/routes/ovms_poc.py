# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Endpoints for the isolated OpenCV-to-OVMS proof of concept."""

import logging

from fastapi import APIRouter, HTTPException, Query

import api.api_schemas as schemas
from managers.ovms_poc_manager import OvmsPocManager


router = APIRouter()
logger = logging.getLogger("api.routes.ovms_poc")


@router.post("/run", response_model=schemas.OvmsPocJobResponse, status_code=202)
def run_ovms_poc(body: schemas.OvmsPocRunRequest) -> schemas.OvmsPocJobResponse:
    """Start a file-to-file KServe gRPC streaming job through OVMS."""
    manager = OvmsPocManager()
    try:
        job_id = manager.start_job(**body.model_dump())
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return schemas.OvmsPocJobResponse(job_id=job_id)


@router.get("/jobs/{job_id}")
def get_ovms_poc_job(job_id: str) -> dict:
    """Return the latest status written by an OVMS POC runner."""
    status = OvmsPocManager().get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"OVMS POC job {job_id} not found")
    return status


@router.get("/jobs/{job_id}/metadata")
def get_ovms_poc_metadata(
    job_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict]:
    """Return a bounded snapshot of JSONL prediction records for a POC job."""
    records = OvmsPocManager().get_metadata(job_id, limit)
    if records is None:
        raise HTTPException(status_code=404, detail=f"OVMS POC job {job_id} not found")
    return records


@router.post("/jobs/{job_id}/stop")
def stop_ovms_poc_job(job_id: str) -> dict[str, str]:
    """Request graceful termination of an active OVMS POC runner."""
    stopped, message = OvmsPocManager().stop_job(job_id)
    if not stopped:
        raise HTTPException(status_code=409, detail=message)
    return {"message": message}
