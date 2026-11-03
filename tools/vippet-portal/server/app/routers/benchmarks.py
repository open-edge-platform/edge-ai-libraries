"""Aggregated benchmark suite runs across all instances."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from .. import aggregator, schemas
from ..db import get_session
from ..vippet_client import VippetUnavailable

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("/runs", response_model=list[schemas.BenchmarkRun], operation_id="get_benchmark_runs")
async def get_benchmark_runs(session: AsyncSession = Depends(get_session)):
    """Every benchmark suite run known to every enabled instance."""
    return await aggregator.benchmark_runs(session)


@router.get(
    "/suites", response_model=list[schemas.BenchmarkSuite], operation_id="get_benchmark_suites"
)
async def get_benchmark_suites(session: AsyncSession = Depends(get_session)):
    """Suites that can be launched, merged across the enabled instances."""
    return await aggregator.benchmark_suites(session)


@router.get("/compare", response_model=schemas.Comparison, operation_id="compare_benchmark_runs")
async def compare_benchmark_runs(
    refs: list[str] = Query(default_factory=list, description="Run refs: <instance>:<slug>:<id>"),
    session: AsyncSession = Depends(get_session),
):
    """Align selected runs row-by-row so machines can be compared directly."""
    if not refs:
        raise HTTPException(status_code=400, detail="At least one run ref is required")
    return await aggregator.compare_benchmarks(session, refs)


@router.get("/runs/{ref}", operation_id="get_benchmark_run_details")
async def get_benchmark_run_details(
    ref: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    try:
        instance, details = await aggregator.benchmark_run_details(session, ref)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VippetUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return details | {
        "ref": ref,
        "instance_id": instance.id,
        "instance_name": instance.name,
        "instance_url": instance.url,
        "cpu": instance.cpu,
    }
