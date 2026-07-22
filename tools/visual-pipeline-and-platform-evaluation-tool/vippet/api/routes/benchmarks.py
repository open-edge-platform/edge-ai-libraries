import csv
import io
import logging
import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import api.api_schemas as schemas
from database import get_session
from managers.benchmark_manager import BenchmarkManager
from managers.pipeline_manager import PipelineManager
from orm_models import (
    BenchmarkSuite,
    BenchmarkSuiteRun,
    BenchmarkTestCase,
    BenchmarkTestCaseRun,
    BenchmarkWorkload,
    BenchmarkWorkloadRun,
)

router = APIRouter()
logger = logging.getLogger("api.routes.benchmarks")

def _build_pipeline_name_by_id_map() -> dict[str, str]:
    """Best-effort map of pipeline id to display name."""
    # TODO: Read pipeline names from the pipelines table once pipelines are persisted in DB.
    try:
        return {pipeline.id: pipeline.name for pipeline in PipelineManager().get_pipelines()}
    except Exception:
        logger.warning("Failed to resolve pipeline names for CSV export", exc_info=True)
        return {}


@router.get(
    "",
    operation_id="get_benchmarks",
    summary="List all benchmark suites",
    response_model=list[schemas.BenchmarkSuite],
    responses={
        200: {
            "description": "List of benchmark suites with workloads and test cases",
            "model": list[schemas.BenchmarkSuite],
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
    """Return all benchmark suites with nested workloads and test cases."""
    try:
        result = await session.execute(
            select(BenchmarkSuite).order_by(BenchmarkSuite.last_run_at.desc(), BenchmarkSuite.id)
        )
        suites = result.scalars().all()

        if not suites:
            return []

        suite_ids = [suite.id for suite in suites]

        workload_rows_result = await session.execute(
            select(BenchmarkWorkload)
            .where(BenchmarkWorkload.suite_id.in_(suite_ids))
            .order_by(BenchmarkWorkload.id)
        )
        workload_rows = workload_rows_result.scalars().all()

        workload_ids = [workload.id for workload in workload_rows]
        test_case_rows_result = await session.execute(
            select(BenchmarkTestCase)
            .where(BenchmarkTestCase.workload_id.in_(workload_ids))
            .order_by(BenchmarkTestCase.id)
        )
        test_case_rows = test_case_rows_result.scalars().all()

        test_cases_by_workload_id: dict[int, list[schemas.BenchmarkTestCase]] = {}
        for row in test_case_rows:
            test_cases_by_workload_id.setdefault(row.workload_id, []).append(
                schemas.BenchmarkTestCase(
                    id=row.id,
                    variant_id=row.variant_id,
                    streams=row.streams,
                )
            )

        workloads_by_suite_id: dict[int, list[schemas.BenchmarkWorkload]] = {}
        for row in workload_rows:
            workloads_by_suite_id.setdefault(row.suite_id, []).append(
                schemas.BenchmarkWorkload(
                    id=row.id,
                    pipeline_id=row.pipeline_id,
                    variants=row.variants,
                    test_cases=test_cases_by_workload_id.get(row.id, []),
                )
            )

        return [
            schemas.BenchmarkSuite(
                id=suite.id,
                slug=suite.slug,
                name=suite.name,
                description=suite.description,
                created_at=suite.created_at,
                last_run_at=suite.last_run_at,
                workloads=workloads_by_suite_id.get(suite.id, []),
            )
            for suite in suites
        ]
    except Exception:
        logger.error("Unexpected error while listing benchmarks", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while listing benchmarks."
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/runs",
    operation_id="get_all_benchmark_runs",
    summary="List all benchmark runs across all suites",
    response_model=list[schemas.BenchmarkSuiteRun],
    responses={
        200: {
            "description": "List of all suite runs",
            "model": list[schemas.BenchmarkSuiteRun],
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def get_all_benchmark_runs(
    session: AsyncSession = Depends(get_session),
):
    """Return all benchmark runs across all suites."""
    try:
        suite_runs_result = await session.execute(
            select(BenchmarkSuiteRun).order_by(BenchmarkSuiteRun.start_time.desc(), BenchmarkSuiteRun.id.desc())
        )
        suite_runs = suite_runs_result.scalars().all()
        if not suite_runs:
            return []

        suite_ids = [suite_run.suite_id for suite_run in suite_runs]
        suites_by_id: dict[int, BenchmarkSuite] = {}
        if suite_ids:
            suites_result = await session.execute(
                select(BenchmarkSuite).where(BenchmarkSuite.id.in_(suite_ids))
            )
            suites = suites_result.scalars().all()
            suites_by_id = {suite.id: suite for suite in suites}

        response_runs: list[schemas.BenchmarkSuiteRun] = []
        now_ms = int(time.time() * 1000)
        for suite_run in suite_runs:
            suite = suites_by_id.get(suite_run.suite_id)
            if suite is None:
                continue

            response_runs.append(
                schemas.BenchmarkSuiteRun(
                    id=suite_run.id,
                    suite_id=suite_run.suite_id,
                    suite_slug=suite.slug,
                    suite_name=suite.name,
                    suite_description=suite.description,
                    status=schemas.BenchmarkTestCaseRunStatus(suite_run.status),
                    score_total=suite_run.score_total,
                    score_performance=suite_run.score_performance,
                    score_efficiency=suite_run.score_efficiency,
                    start_time=suite_run.start_time,
                    execution_time=(
                        now_ms - suite_run.start_time
                        if suite_run.status == "running"
                        else suite_run.execution_time
                    ),
                    job_id=suite_run.job_id,
                    total_test_cases=suite_run.total_test_cases,
                    passed_test_cases=suite_run.passed_test_cases,
                )
            )

        return response_runs

    except Exception:
        logger.error("Unexpected error while listing all benchmark runs", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while listing benchmark runs."
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/{suite_slug}",
    operation_id="get_benchmark_suite_by_slug",
    summary="Get benchmark suite by slug",
    response_model=schemas.BenchmarkSuite,
    responses={
        200: {
            "description": "Benchmark suite with workloads and test cases",
            "model": schemas.BenchmarkSuite,
        },
        404: {
            "description": "Benchmark suite not found",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def get_benchmark_suite_by_slug(
    suite_slug: str,
    session: AsyncSession = Depends(get_session),
):
    """Return one benchmark suite by slug with nested workloads and test cases."""
    try:
        suite = await session.scalar(
            select(BenchmarkSuite).where(BenchmarkSuite.slug == suite_slug)
        )

        if suite is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=f"Benchmark suite with slug '{suite_slug}' not found."
                ).model_dump(),
                status_code=404,
            )

        workload_rows_result = await session.execute(
            select(BenchmarkWorkload)
            .where(BenchmarkWorkload.suite_id == suite.id)
            .order_by(BenchmarkWorkload.id)
        )
        workload_rows = workload_rows_result.scalars().all()

        workload_ids = [workload.id for workload in workload_rows]
        test_case_rows_result = await session.execute(
            select(BenchmarkTestCase)
            .where(BenchmarkTestCase.workload_id.in_(workload_ids))
            .order_by(BenchmarkTestCase.id)
        )
        test_case_rows = test_case_rows_result.scalars().all()

        test_cases_by_workload_id: dict[int, list[schemas.BenchmarkTestCase]] = {}
        for row in test_case_rows:
            test_cases_by_workload_id.setdefault(row.workload_id, []).append(
                schemas.BenchmarkTestCase(
                    id=row.id,
                    variant_id=row.variant_id,
                    streams=row.streams,
                )
            )

        workloads = [
            schemas.BenchmarkWorkload(
                id=row.id,
                pipeline_id=row.pipeline_id,
                variants=row.variants,
                test_cases=test_cases_by_workload_id.get(row.id, []),
            )
            for row in workload_rows
        ]

        return schemas.BenchmarkSuite(
            id=suite.id,
            slug=suite.slug,
            name=suite.name,
            description=suite.description,
            created_at=suite.created_at,
            last_run_at=suite.last_run_at,
            workloads=workloads,
        )
    except Exception:
        logger.error(
            "Unexpected error while loading benchmark suite slug=%s",
            suite_slug,
            exc_info=True,
        )
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while loading benchmark suite."
            ).model_dump(),
            status_code=500,
        )


@router.post(
    "/{suite_slug}/run",
    operation_id="run_benchmark_suite",
    summary="Start a benchmark suite run",
    status_code=202,
    response_model=schemas.BenchmarkJobResponse,
    responses={
        202: {
            "description": "Benchmark suite job created",
            "model": schemas.BenchmarkJobResponse,
        },
        400: {
            "description": "Invalid benchmark suite request",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Unexpected error while starting benchmark suite",
            "model": schemas.MessageResponse,
        },
    },
)
def run_benchmark_suite(suite_slug: str):
    """Start asynchronous benchmark execution for one suite slug."""
    try:
        job_id = BenchmarkManager().start_suite(suite_slug)
        return JSONResponse(
            content=schemas.BenchmarkJobResponse(job_id=job_id).model_dump(),
            status_code=202,
        )
    except ValueError as exc:
        logger.error("Invalid benchmark suite run request for slug=%s: %s", suite_slug, exc)
        return JSONResponse(
            content=schemas.MessageResponse(message=str(exc)).model_dump(),
            status_code=400,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error while starting benchmark suite slug=%s",
            suite_slug,
            exc_info=True,
        )
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Unexpected error while starting benchmark suite: {str(exc)}"
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/{suite_slug}/runs",
    operation_id="get_benchmark_suite_runs",
    summary="List historical runs of a benchmark suite",
    response_model=list[schemas.BenchmarkSuiteRun],
    responses={
        200: {
            "description": "List of suite runs with nested workload and test case runs",
            "model": list[schemas.BenchmarkSuiteRun],
        },
        404: {
            "description": "Benchmark suite not found",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def get_benchmark_suite_runs(
    suite_slug: str,
    session: AsyncSession = Depends(get_session),
):
    """Return historical suite runs with nested workload and test-case runs."""
    try:
        suite = await session.scalar(
            select(BenchmarkSuite).where(BenchmarkSuite.slug == suite_slug)
        )
        if suite is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=f"Benchmark suite with slug '{suite_slug}' not found."
                ).model_dump(),
                status_code=404,
            )

        suite_runs_result = await session.execute(
            select(BenchmarkSuiteRun)
            .where(BenchmarkSuiteRun.suite_id == suite.id)
            .order_by(BenchmarkSuiteRun.start_time.desc(), BenchmarkSuiteRun.id.desc())
        )
        suite_runs = suite_runs_result.scalars().all()
        if not suite_runs:
            return []

        response_runs: list[schemas.BenchmarkSuiteRun] = [
            schemas.BenchmarkSuiteRun(
                id=suite_run.id,
                suite_id=suite_run.suite_id,
                suite_slug=suite.slug,
                suite_name=suite.name,
                suite_description=suite.description,
                status=schemas.BenchmarkTestCaseRunStatus(suite_run.status),
                score_total=suite_run.score_total,
                score_performance=suite_run.score_performance,
                score_efficiency=suite_run.score_efficiency,
                start_time=suite_run.start_time,
                execution_time=(
                    int(time.time() * 1000) - suite_run.start_time
                    if suite_run.status == "running"
                    else suite_run.execution_time
                ),
                job_id=suite_run.job_id,
                total_test_cases=suite_run.total_test_cases,
                passed_test_cases=suite_run.passed_test_cases,
            )
            for suite_run in suite_runs
        ]

        return response_runs

    except Exception:
        logger.error(
            "Unexpected error while listing benchmark runs for slug=%s",
            suite_slug,
            exc_info=True,
        )
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while listing benchmark runs."
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/{suite_slug}/run/{run_id}/csv",
    operation_id="export_benchmark_suite_run_csv",
    summary="Export one benchmark suite run as CSV",
    responses={
        200: {
            "description": "CSV file containing workload and test case data",
        },
        404: {
            "description": "Benchmark suite or run not found",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def export_benchmark_suite_run_csv(
    suite_slug: str,
    run_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Export one suite run by id as a CSV with run metadata and workload sections."""
    try:
        suite = await session.scalar(
            select(BenchmarkSuite).where(BenchmarkSuite.slug == suite_slug)
        )
        if suite is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=f"Benchmark suite with slug '{suite_slug}' not found."
                ).model_dump(),
                status_code=404,
            )

        suite_run = await session.scalar(
            select(BenchmarkSuiteRun).where(
                BenchmarkSuiteRun.id == run_id,
                BenchmarkSuiteRun.suite_id == suite.id,
            )
        )
        if suite_run is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=(
                        f"Benchmark suite run with id={run_id} not found for "
                        f"suite '{suite_slug}'."
                    )
                ).model_dump(),
                status_code=404,
            )

        workload_runs_result = await session.execute(
            select(BenchmarkWorkloadRun)
            .where(BenchmarkWorkloadRun.suite_run_id == suite_run.id)
            .order_by(BenchmarkWorkloadRun.id)
        )
        workload_runs = workload_runs_result.scalars().all()
        pipeline_name_by_id = _build_pipeline_name_by_id_map()

        workload_ids = [workload_run.workload_id for workload_run in workload_runs]
        workloads_by_id: dict[int, BenchmarkWorkload] = {}
        if workload_ids:
            workloads_result = await session.execute(
                select(BenchmarkWorkload).where(BenchmarkWorkload.id.in_(workload_ids))
            )
            workloads = workloads_result.scalars().all()
            workloads_by_id = {workload.id: workload for workload in workloads}

        workload_run_ids = [workload_run.id for workload_run in workload_runs]
        test_case_runs: list[BenchmarkTestCaseRun] = []
        if workload_run_ids:
            test_case_runs_result = await session.execute(
                select(BenchmarkTestCaseRun)
                .where(BenchmarkTestCaseRun.workload_run_id.in_(workload_run_ids))
                .order_by(BenchmarkTestCaseRun.id)
            )
            test_case_runs = test_case_runs_result.scalars().all()

        test_case_ids = [test_case_run.test_case_id for test_case_run in test_case_runs]
        benchmark_test_cases_by_id: dict[int, BenchmarkTestCase] = {}
        if test_case_ids:
            benchmark_test_cases_result = await session.execute(
                select(BenchmarkTestCase).where(BenchmarkTestCase.id.in_(test_case_ids))
            )
            benchmark_test_cases = benchmark_test_cases_result.scalars().all()
            benchmark_test_cases_by_id = {
                test_case.id: test_case for test_case in benchmark_test_cases
            }

        test_case_runs_by_workload_run_id: dict[int, list[BenchmarkTestCaseRun]] = {}
        for row in test_case_runs:
            test_case_runs_by_workload_run_id.setdefault(row.workload_run_id, []).append(
                row
            )

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["suite_name", "start_time", "id", "status"])
        writer.writerow([
            suite.name,
            suite_run.start_time,
            suite_run.id,
            suite_run.status,
        ])
        writer.writerow([])

        workload_header = [
            "pipeline_name",
            "overall_score",
            "performance_score",
            "efficiency_score",
            "duration",
            "pass_rate",
            "status",
        ]

        test_header = [
            "variant",
            "streams",
            "duration",
            "total_fps",
            "per_stream_fps",
            "cpu",
            "gpu",
            "npu",
            "media",
            "memory",
            "power",
            "status",
        ]

        for row in workload_runs:
            workload_test_case_runs = test_case_runs_by_workload_run_id.get(row.id, [])

            writer.writerow(workload_header)
            writer.writerow(
                [
                    pipeline_name_by_id.get(
                        workloads_by_id[row.workload_id].pipeline_id,
                        workloads_by_id[row.workload_id].pipeline_id,
                    )
                    if row.workload_id in workloads_by_id
                    else "",
                    row.score_total,
                    row.score_performance,
                    row.score_efficiency,
                    row.execution_time,
                    "",
                    row.status,
                ]
            )

            writer.writerow(test_header)

            for test_row in workload_test_case_runs:
                benchmark_test_case = benchmark_test_cases_by_id.get(test_row.test_case_id)
                variant_id = benchmark_test_case.variant_id if benchmark_test_case else ""
                streams = benchmark_test_case.streams if benchmark_test_case else 0

                status = schemas.BenchmarkTestCaseRunStatus(test_row.status)

                writer.writerow(
                    [
                        variant_id,
                        streams,
                        test_row.execution_time,
                        test_row.total_fps,
                        test_row.per_stream_fps,
                        test_row.cpu_usage,
                        test_row.gpu_usage,
                        test_row.npu_usage,
                        test_row.media_usage,
                        test_row.memory_usage,
                        test_row.power_usage,
                        status.value,
                    ]
                )

            writer.writerow([])

        filename = f"{suite.slug}-run-{suite_run.id}.csv"
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except Exception:
        logger.error(
            "Unexpected error while exporting benchmark run id=%s for slug=%s",
            run_id,
            suite_slug,
            exc_info=True,
        )
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while exporting benchmark run CSV."
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/{suite_slug}/run/{run_id}",
    operation_id="get_benchmark_suite_run_by_id",
    summary="Get one benchmark suite run by id with nested workload and test-case runs",
    response_model=schemas.BenchmarkSuiteRunDetails,
    responses={
        200: {
            "description": "Detailed suite run with nested workload and test case runs",
            "model": schemas.BenchmarkSuiteRunDetails,
        },
        404: {
            "description": "Benchmark suite or run not found",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def get_benchmark_suite_run_by_id(
    suite_slug: str,
    run_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Return one suite run by id with nested workload and test-case runs."""
    try:
        suite = await session.scalar(
            select(BenchmarkSuite).where(BenchmarkSuite.slug == suite_slug)
        )
        if suite is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=f"Benchmark suite with slug '{suite_slug}' not found."
                ).model_dump(),
                status_code=404,
            )

        suite_run = await session.scalar(
            select(BenchmarkSuiteRun).where(
                BenchmarkSuiteRun.id == run_id,
                BenchmarkSuiteRun.suite_id == suite.id,
            )
        )
        if suite_run is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=(
                        f"Benchmark suite run with id={run_id} not found for "
                        f"suite '{suite_slug}'."
                    )
                ).model_dump(),
                status_code=404,
            )

        workload_runs_result = await session.execute(
            select(BenchmarkWorkloadRun)
            .where(BenchmarkWorkloadRun.suite_run_id == suite_run.id)
            .order_by(BenchmarkWorkloadRun.id)
        )
        workload_runs = workload_runs_result.scalars().all()

        workload_ids = [workload_run.workload_id for workload_run in workload_runs]
        workloads_by_id: dict[int, BenchmarkWorkload] = {}
        if workload_ids:
            workloads_result = await session.execute(
                select(BenchmarkWorkload).where(BenchmarkWorkload.id.in_(workload_ids))
            )
            workloads = workloads_result.scalars().all()
            workloads_by_id = {workload.id: workload for workload in workloads}

        workload_run_ids = [workload_run.id for workload_run in workload_runs]
        test_case_runs: list[BenchmarkTestCaseRun] = []
        if workload_run_ids:
            test_case_runs_result = await session.execute(
                select(BenchmarkTestCaseRun)
                .where(BenchmarkTestCaseRun.workload_run_id.in_(workload_run_ids))
                .order_by(BenchmarkTestCaseRun.id)
            )
            test_case_runs = test_case_runs_result.scalars().all()

        test_case_ids = [test_case_run.test_case_id for test_case_run in test_case_runs]
        benchmark_test_cases_by_id: dict[int, BenchmarkTestCase] = {}
        if test_case_ids:
            benchmark_test_cases_result = await session.execute(
                select(BenchmarkTestCase).where(BenchmarkTestCase.id.in_(test_case_ids))
            )
            benchmark_test_cases = benchmark_test_cases_result.scalars().all()
            benchmark_test_cases_by_id = {
                test_case.id: test_case for test_case in benchmark_test_cases
            }

        now_ms = int(time.time() * 1000)
        test_case_runs_by_workload_run_id: dict[
            int, list[schemas.BenchmarkTestCaseRun]
        ] = {}
        for row in test_case_runs:
            benchmark_test_case = benchmark_test_cases_by_id.get(row.test_case_id)
            variant_id = benchmark_test_case.variant_id if benchmark_test_case else ""
            streams = benchmark_test_case.streams if benchmark_test_case else 0

            status = schemas.BenchmarkTestCaseRunStatus(row.status)
            live_execution_time = (
                now_ms - row.start_time
                if status == schemas.BenchmarkTestCaseRunStatus.RUNNING and row.start_time is not None
                else row.execution_time
            )

            test_case_runs_by_workload_run_id.setdefault(row.workload_run_id, []).append(
                schemas.BenchmarkTestCaseRun(
                    id=row.id,
                    test_case_id=row.test_case_id,
                    variant_id=variant_id,
                    streams=streams,
                    workload_run_id=row.workload_run_id,
                    start_time=row.start_time,
                    execution_time=live_execution_time,
                    total_fps=row.total_fps,
                    per_stream_fps=(
                        row.per_stream_fps
                        if row.per_stream_fps is not None
                        else (
                            row.total_fps / streams
                            if row.total_fps is not None and streams > 0
                            else None
                        )
                    ),
                    cpu_usage=row.cpu_usage,
                    gpu_usage=row.gpu_usage,
                    npu_usage=row.npu_usage,
                    media_usage=row.media_usage,
                    memory_usage=row.memory_usage,
                    power_usage=row.power_usage,
                    metrics=row.metrics,
                    job_id=row.job_id,
                    status=status,
                )
            )

        workload_run_items: list[schemas.BenchmarkWorkloadRun] = []
        for row in workload_runs:
            workload_test_case_runs = test_case_runs_by_workload_run_id.get(row.id, [])
            total_test_cases = len(workload_test_case_runs)
            passed_test_cases = sum(
                1
                for test_case_run in workload_test_case_runs
                if test_case_run.status == schemas.BenchmarkTestCaseRunStatus.PASSED
            )
            failed_test_cases = sum(
                1
                for test_case_run in workload_test_case_runs
                if test_case_run.status == schemas.BenchmarkTestCaseRunStatus.FAILED
            )
            pass_rate = (
                passed_test_cases / total_test_cases if total_test_cases > 0 else 0.0
            )

            workload_run_items.append(
                schemas.BenchmarkWorkloadRun(
                    id=row.id,
                    workload_id=row.workload_id,
                    pipeline_id=(
                        workloads_by_id[row.workload_id].pipeline_id
                        if row.workload_id in workloads_by_id
                        else ""
                    ),
                    suite_run_id=row.suite_run_id,
                    status=schemas.BenchmarkTestCaseRunStatus(row.status),
                    score_total=row.score_total,
                    score_performance=row.score_performance,
                    score_efficiency=row.score_efficiency,
                    start_time=row.start_time,
                    execution_time=(
                        now_ms - row.start_time
                        if row.status == "running" and row.start_time is not None
                        else row.execution_time
                    ),
                    test_case_runs=workload_test_case_runs,
                    total_test_cases=total_test_cases,
                    passed_test_cases=passed_test_cases,
                    failed_test_cases=failed_test_cases,
                    pass_rate=pass_rate,
                )
            )

        return schemas.BenchmarkSuiteRunDetails(
            id=suite_run.id,
            suite_id=suite_run.suite_id,
            suite_slug=suite.slug,
            suite_name=suite.name,
            suite_description=suite.description,
            status=schemas.BenchmarkTestCaseRunStatus(suite_run.status),
            score_total=suite_run.score_total,
            score_performance=suite_run.score_performance,
            score_efficiency=suite_run.score_efficiency,
            start_time=suite_run.start_time,
            execution_time=(
                now_ms - suite_run.start_time
                if suite_run.status == "running"
                else suite_run.execution_time
            ),
            job_id=suite_run.job_id,
            total_test_cases=suite_run.total_test_cases,
            passed_test_cases=suite_run.passed_test_cases,
            workload_runs=workload_run_items,
        )
    except Exception:
        logger.error(
            "Unexpected error while loading benchmark run id=%s for slug=%s",
            run_id,
            suite_slug,
            exc_info=True,
        )
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while loading benchmark run."
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/{suite_slug}/run/{run_id}/test/{test_run_id}",
    operation_id="get_benchmark_test_run_by_id",
    summary="Get one benchmark test-case run by id with resolved benchmark references",
    response_model=schemas.BenchmarkTestCaseRunDetails,
    responses={
        200: {
            "description": "Detailed test-case run with test case and suite metadata",
            "model": schemas.BenchmarkTestCaseRunDetails,
        },
        404: {
            "description": "Benchmark suite, run, or test run not found",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def get_benchmark_test_run_by_id(
    suite_slug: str,
    run_id: int,
    test_run_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Return one test-case run by id with resolved test-case and suite metadata."""
    try:
        suite = await session.scalar(
            select(BenchmarkSuite).where(BenchmarkSuite.slug == suite_slug)
        )
        if suite is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=f"Benchmark suite with slug '{suite_slug}' not found."
                ).model_dump(),
                status_code=404,
            )

        suite_run = await session.scalar(
            select(BenchmarkSuiteRun).where(
                BenchmarkSuiteRun.id == run_id,
                BenchmarkSuiteRun.suite_id == suite.id,
            )
        )
        if suite_run is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=(
                        f"Benchmark suite run with id={run_id} not found for "
                        f"suite '{suite_slug}'."
                    )
                ).model_dump(),
                status_code=404,
            )

        test_case_run = await session.scalar(
            select(BenchmarkTestCaseRun).where(BenchmarkTestCaseRun.id == test_run_id)
        )
        if test_case_run is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=(
                        f"Benchmark test-case run with id={test_run_id} not found for "
                        f"suite run id={run_id}."
                    )
                ).model_dump(),
                status_code=404,
            )

        workload_run = await session.scalar(
            select(BenchmarkWorkloadRun).where(
                BenchmarkWorkloadRun.id == test_case_run.workload_run_id,
                BenchmarkWorkloadRun.suite_run_id == suite_run.id,
            )
        )
        if workload_run is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=(
                        f"Benchmark test-case run with id={test_run_id} does not belong "
                        f"to suite run id={run_id}."
                    )
                ).model_dump(),
                status_code=404,
            )

        benchmark_test_case = await session.scalar(
            select(BenchmarkTestCase).where(BenchmarkTestCase.id == test_case_run.test_case_id)
        )
        if benchmark_test_case is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=(
                        f"Benchmark test case id={test_case_run.test_case_id} referenced "
                        f"by test run id={test_run_id} was not found."
                    )
                ).model_dump(),
                status_code=404,
            )

        workload = await session.scalar(
            select(BenchmarkWorkload).where(BenchmarkWorkload.id == benchmark_test_case.workload_id)
        )
        if workload is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=(
                        f"Benchmark workload id={benchmark_test_case.workload_id} referenced "
                        f"by test run id={test_run_id} was not found."
                    )
                ).model_dump(),
                status_code=404,
            )

        now_ms = int(time.time() * 1000)
        status = schemas.BenchmarkTestCaseRunStatus(test_case_run.status)
        execution_time = (
            now_ms - test_case_run.start_time
            if status == schemas.BenchmarkTestCaseRunStatus.RUNNING
            and test_case_run.start_time is not None
            else test_case_run.execution_time
        )

        return schemas.BenchmarkTestCaseRunDetails(
            id=test_case_run.id,
            test_case_id=test_case_run.test_case_id,
            variant_id=benchmark_test_case.variant_id,
            streams=benchmark_test_case.streams,
            workload_run_id=test_case_run.workload_run_id,
            start_time=test_case_run.start_time,
            execution_time=execution_time,
            total_fps=test_case_run.total_fps,
            per_stream_fps=(
                test_case_run.per_stream_fps
                if test_case_run.per_stream_fps is not None
                else (
                    test_case_run.total_fps / benchmark_test_case.streams
                    if test_case_run.total_fps is not None and benchmark_test_case.streams > 0
                    else None
                )
            ),
            cpu_usage=test_case_run.cpu_usage,
            gpu_usage=test_case_run.gpu_usage,
            npu_usage=test_case_run.npu_usage,
            media_usage=test_case_run.media_usage,
            memory_usage=test_case_run.memory_usage,
            power_usage=test_case_run.power_usage,
            metrics=test_case_run.metrics,
            job_id=test_case_run.job_id,
            status=status,
            suite_run_id=suite_run.id,
            workload_id=workload.id,
            pipeline_id=workload.pipeline_id,
            test_case=schemas.BenchmarkTestCase(
                id=benchmark_test_case.id,
                variant_id=benchmark_test_case.variant_id,
                streams=benchmark_test_case.streams,
            ),
            suite=schemas.BenchmarkSuiteRef(
                id=suite.id,
                slug=suite.slug,
                name=suite.name,
                description=suite.description,
            ),
        )
    except Exception:
        logger.error(
            "Unexpected error while loading benchmark test run id=%s for suite run id=%s and slug=%s",
            test_run_id,
            run_id,
            suite_slug,
            exc_info=True,
        )
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while loading benchmark test run."
            ).model_dump(),
            status_code=500,
        )
