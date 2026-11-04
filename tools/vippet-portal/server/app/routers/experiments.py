"""Benchmark suite runs launched from the portal across several machines."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from .. import aggregator, schemas
from ..db import get_session

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("", response_model=list[schemas.Experiment], operation_id="get_experiments")
async def get_experiments(session: AsyncSession = Depends(get_session)):
    """Experiments started from the portal, with live per-machine progress."""
    return await aggregator.experiments(session)


@router.get(
    "/pipelines", response_model=list[schemas.Pipeline], operation_id="get_pipeline_catalog"
)
async def get_pipeline_catalog(session: AsyncSession = Depends(get_session)):
    """Pipelines and variants that can be used as a test workload."""
    return await aggregator.pipeline_catalog(session)


@router.get(
    "/tests/{kind}",
    response_model=list[schemas.TestExperiment],
    operation_id="get_test_experiments",
)
async def get_test_experiments(
    kind: schemas.TestKind, session: AsyncSession = Depends(get_session)
):
    return await aggregator.test_experiments(session, kind)


@router.post(
    "/tests/{kind}",
    response_model=schemas.TestExperiment,
    status_code=status.HTTP_201_CREATED,
    operation_id="start_test_experiment",
)
async def start_test_experiment(
    kind: schemas.TestKind,
    payload: schemas.TestExperimentCreate,
    session: AsyncSession = Depends(get_session),
):
    """Start one workload on every selected machine and group the resulting jobs."""
    try:
        return await aggregator.start_test_experiment(session, kind, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/tests/{experiment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_test_experiment",
)
async def delete_test_experiment(
    experiment_id: int, session: AsyncSession = Depends(get_session)
) -> Response:
    try:
        await aggregator.delete_test_experiment(session, experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "",
    response_model=schemas.Experiment,
    status_code=status.HTTP_201_CREATED,
    operation_id="start_experiment",
)
async def start_experiment(
    payload: schemas.ExperimentCreate, session: AsyncSession = Depends(get_session)
):
    """Start one suite on every selected machine and group the resulting runs."""
    try:
        return await aggregator.start_experiment(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/{experiment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_experiment",
)
async def delete_experiment(
    experiment_id: int, session: AsyncSession = Depends(get_session)
) -> Response:
    try:
        await aggregator.delete_experiment(session, experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
