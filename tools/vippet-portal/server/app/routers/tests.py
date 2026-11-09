"""Aggregated individual performance and density test runs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from .. import aggregator, schemas
from ..db import get_session

router = APIRouter(prefix="/tests", tags=["tests"])


@router.get("/{kind}", response_model=list[schemas.TestJob], operation_id="get_test_jobs")
async def get_test_jobs(
    kind: schemas.TestKind, session: AsyncSession = Depends(get_session)
):
    return await aggregator.test_jobs(session, kind)


@router.get(
    "/{kind}/compare", response_model=schemas.Comparison, operation_id="compare_test_jobs"
)
async def compare_test_jobs(
    kind: schemas.TestKind,
    refs: list[str] = Query(default_factory=list, description="Job refs: <instance>:<job_id>"),
    session: AsyncSession = Depends(get_session),
):
    if not refs:
        raise HTTPException(status_code=400, detail="At least one job ref is required")
    return await aggregator.compare_tests(session, kind, refs)
