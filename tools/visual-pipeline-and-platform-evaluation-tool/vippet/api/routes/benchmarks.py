import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import api.api_schemas as schemas
from database import get_session
from orm_models import (
    Benchmark,
    BenchmarkDensitySetup,
    BenchmarkPerformanceSetup,
    BenchmarkType,
)

router = APIRouter()
logger = logging.getLogger("api.routes.benchmarks")


@router.get(
    "",
    operation_id="get_benchmarks",
    summary="List all benchmark definitions",
    response_model=list[schemas.BenchmarkWithSetup],
    responses={
        200: {
            "description": "List of benchmark definitions with setup rows",
            "model": list[schemas.BenchmarkWithSetup],
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def get_benchmarks(
    session: AsyncSession = Depends(get_session),
):
    """
    Return all benchmark definitions with setup rows selected by benchmark type.

    - performance -> setup rows from BenchmarkPerformanceSetup
    - density -> setup rows from BenchmarkDensitySetup
    """
    try:
        result = await session.execute(select(Benchmark).order_by(Benchmark.id))
        benchmarks = result.scalars().all()

        if not benchmarks:
            return []

        benchmark_ids = [benchmark.id for benchmark in benchmarks]

        performance_rows_result = await session.execute(
            select(BenchmarkPerformanceSetup)
            .where(BenchmarkPerformanceSetup.benchmark_id.in_(benchmark_ids))
            .order_by(BenchmarkPerformanceSetup.id)
        )
        performance_rows = performance_rows_result.scalars().all()

        density_rows_result = await session.execute(
            select(BenchmarkDensitySetup)
            .where(BenchmarkDensitySetup.benchmark_id.in_(benchmark_ids))
            .order_by(BenchmarkDensitySetup.id)
        )
        density_rows = density_rows_result.scalars().all()

        performance_by_benchmark_id: dict[int, list[schemas.BenchmarkPerformanceSetup]] = {}
        for row in performance_rows:
            performance_by_benchmark_id.setdefault(row.benchmark_id, []).append(
                schemas.BenchmarkPerformanceSetup(
                    pipeline_id=row.pipeline_id,
                    variant_id=row.variant_id,
                    streams=row.streams,
                )
            )

        density_by_benchmark_id: dict[int, list[schemas.BenchmarkDensitySetup]] = {}
        for row in density_rows:
            density_by_benchmark_id.setdefault(row.benchmark_id, []).append(
                schemas.BenchmarkDensitySetup(
                    pipeline_id=row.pipeline_id,
                    variant_id=row.variant_id,
                    participation_rate=row.participation_rate,
                )
            )

        response_items: list[schemas.BenchmarkWithSetup] = []
        for benchmark in benchmarks:
            if benchmark.type == BenchmarkType.performance:
                response_items.append(
                    schemas.BenchmarkWithPerformanceSetup(
                        id=benchmark.id,
                        name=benchmark.name,
                        type="performance",
                        setups=performance_by_benchmark_id.get(benchmark.id, []),
                    )
                )
            elif benchmark.type == BenchmarkType.density:
                response_items.append(
                    schemas.BenchmarkWithDensitySetup(
                        id=benchmark.id,
                        name=benchmark.name,
                        type="density",
                        setups=density_by_benchmark_id.get(benchmark.id, []),
                    )
                )
            else:
                logger.warning(
                    "Skipping benchmark id=%s with unsupported type=%s",
                    benchmark.id,
                    benchmark.type,
                )

        return response_items
    except Exception:
        logger.error("Unexpected error while listing benchmarks", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while listing benchmarks."
            ).model_dump(),
            status_code=500,
        )
