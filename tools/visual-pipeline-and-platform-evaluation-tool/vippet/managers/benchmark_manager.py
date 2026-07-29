import asyncio
import logging
import threading
import time
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeVar

from sqlalchemy import select

from database import async_session_maker
from device import DeviceDiscovery, DeviceFamily
from internal_types import (
    InternalBenchmarkJobStatus,
    InternalBenchmarkJobSummary,
    InternalExecutionConfig,
    InternalMetadataMode,
    InternalOutputMode,
    InternalPerformanceJobStatus,
    InternalPerformanceTestSpec,
    InternalPipelinePerformanceSpec,
    InternalTestJobState,
)
from managers import benchmark_metrics as metrics
from managers import benchmark_scoring as scoring
from managers.pipeline_manager import PipelineManager
from managers.tests_manager import TestsManager
from orm_models import (
    BenchmarkSuite,
    BenchmarkSuiteRun,
    BenchmarkTestCase,
    BenchmarkTestCaseRun,
    BenchmarkWorkload,
    BenchmarkWorkloadRun,
)


logger = logging.getLogger("benchmark_manager")


_T = TypeVar("_T")


@dataclass
class _PlannedTestCaseRun:
    test_case_run_id: int
    workload_run_id: int
    performance_job_id: str
    pipeline_id: str
    variant_id: str
    streams: int


@dataclass
class _BenchmarkPlan:
    suite_run_id: int
    total_test_cases: int
    test_cases: list[_PlannedTestCaseRun]


class BenchmarkManager:
    """Thread-safe singleton orchestrating sequential benchmark suite runs."""

    _instance: "BenchmarkManager | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "BenchmarkManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.jobs: dict[str, InternalBenchmarkJobStatus] = {}
        self._cancel_requested: set[str] = set()
        self._jobs_lock = threading.Lock()

    @staticmethod
    def _generate_job_id() -> str:
        return uuid.uuid1().hex

    @staticmethod
    def _run_db(coro: Coroutine[object, object, _T]) -> _T:
        return asyncio.run(coro)

    @staticmethod
    def _is_device_available(variant_name: str) -> bool:
        """
        Check if the device specified by variant name is available on this system.

        Args:
            variant_name: Variant name (e.g., "CPU", "GPU", "NPU")

        Returns:
            True if the device is available, False otherwise.
        """
        try:
            device_discovery = DeviceDiscovery()
            available_devices = device_discovery.list_devices()
            available_families = {device.device_family for device in available_devices}

            # Map variant name to device family
            variant_upper = variant_name.upper()
            if variant_upper == "CPU":
                return DeviceFamily.CPU in available_families
            elif variant_upper == "GPU":
                return DeviceFamily.GPU in available_families
            elif variant_upper == "NPU":
                return DeviceFamily.NPU in available_families
            else:
                logger.warning(f"Unknown variant name for device check: {variant_name}")
                return True  # Default to allowing unknown variants
        except Exception as e:
            logger.error(
                f"Error checking device availability for variant {variant_name}: {e}"
            )
            return True  # Default to allowing on error

    def start_suite(self, suite_slug: str) -> str:
        job_id = self._generate_job_id()
        plan = self._run_db(
            self._create_benchmark_plan(suite_slug=suite_slug, job_id=job_id)
        )

        job = InternalBenchmarkJobStatus(
            id=job_id,
            suite_slug=suite_slug,
            suite_run_id=plan.suite_run_id,
            state=InternalTestJobState.RUNNING,
            start_time=int(time.time() * 1000),
            details=["Benchmark suite run started"],
            total_test_cases=plan.total_test_cases,
            completed_test_cases=0,
        )
        with self._jobs_lock:
            self.jobs[job_id] = job

        thread = threading.Thread(
            target=self._execute_benchmark_plan,
            args=(job_id, plan),
            daemon=True,
        )
        thread.start()

        return job_id

    async def _create_benchmark_plan(
        self, suite_slug: str, job_id: str
    ) -> _BenchmarkPlan:
        if async_session_maker is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        async with async_session_maker() as session:
            suite = await session.scalar(
                select(BenchmarkSuite).where(BenchmarkSuite.slug == suite_slug)
            )
            if suite is None:
                raise ValueError(f"Benchmark suite with slug '{suite_slug}' not found.")

            workloads_result = await session.execute(
                select(BenchmarkWorkload)
                .where(BenchmarkWorkload.suite_id == suite.id)
                .order_by(BenchmarkWorkload.id)
            )
            workloads = workloads_result.scalars().all()
            if not workloads:
                raise ValueError(
                    f"Benchmark suite '{suite_slug}' has no workloads configured."
                )

            workload_ids = [workload.id for workload in workloads]
            test_cases_result = await session.execute(
                select(BenchmarkTestCase)
                .where(BenchmarkTestCase.workload_id.in_(workload_ids))
                .order_by(BenchmarkTestCase.workload_id, BenchmarkTestCase.id)
            )
            test_cases = test_cases_result.scalars().all()
            if not test_cases:
                raise ValueError(
                    f"Benchmark suite '{suite_slug}' has no test cases configured."
                )

            now_ms = int(time.time() * 1000)
            suite.last_run_at = datetime.now(timezone.utc)

            suite_run = BenchmarkSuiteRun(
                suite_id=suite.id,
                start_time=now_ms,
                job_id=job_id,
                status="running",
                total_test_cases=len(test_cases),
            )
            session.add(suite_run)
            await session.flush()

            workload_run_by_workload_id: dict[int, BenchmarkWorkloadRun] = {}
            workload_test_case_counts = {
                workload.id: sum(
                    1 for tc in test_cases if tc.workload_id == workload.id
                )
                for workload in workloads
            }

            for workload in workloads:
                workload_run = BenchmarkWorkloadRun(
                    workload_id=workload.id,
                    suite_run_id=suite_run.id,
                    total_test_cases=workload_test_case_counts[workload.id],
                )
                session.add(workload_run)
                await session.flush()
                workload_run_by_workload_id[workload.id] = workload_run

            workload_by_id = {workload.id: workload for workload in workloads}
            planned_cases: list[_PlannedTestCaseRun] = []
            for test_case in test_cases:
                workload = workload_by_id[test_case.workload_id]
                performance_job_id = self._generate_job_id()
                test_case_run = BenchmarkTestCaseRun(
                    test_case_id=test_case.id,
                    workload_run_id=workload_run_by_workload_id[
                        test_case.workload_id
                    ].id,
                    job_id=performance_job_id,
                    status="created",
                )
                session.add(test_case_run)
                await session.flush()

                planned_cases.append(
                    _PlannedTestCaseRun(
                        test_case_run_id=test_case_run.id,
                        workload_run_id=workload_run_by_workload_id[
                            test_case.workload_id
                        ].id,
                        performance_job_id=performance_job_id,
                        pipeline_id=workload.pipeline_id,
                        variant_id=test_case.variant_id,
                        streams=test_case.streams,
                    )
                )

            await session.commit()

            return _BenchmarkPlan(
                suite_run_id=suite_run.id,
                total_test_cases=len(planned_cases),
                test_cases=planned_cases,
            )

    async def _update_suite_run_status(self, suite_run_id: int, status: str) -> None:
        if async_session_maker is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        async with async_session_maker() as session:
            suite_run = await session.scalar(
                select(BenchmarkSuiteRun).where(BenchmarkSuiteRun.id == suite_run_id)
            )
            if suite_run is not None:
                workload_runs_result = await session.execute(
                    select(BenchmarkWorkloadRun).where(
                        BenchmarkWorkloadRun.suite_run_id == suite_run_id
                    )
                )
                workload_runs = workload_runs_result.scalars().all()

                workload_statuses = {wr.status for wr in workload_runs}

                if "failed" in workload_statuses:
                    suite_run.status = "failed"
                elif "cancelled" in workload_statuses:
                    suite_run.status = "cancelled"
                elif workload_statuses == {"passed"} or status == "passed":
                    suite_run.status = "passed"
                    (
                        suite_run.score_performance,
                        suite_run.score_efficiency,
                        suite_run.score_total,
                    ) = scoring.aggregate_scores(list(workload_runs))
                else:
                    # Fallback for edge cases (e.g., all created/running)
                    suite_run.status = status

                await session.commit()

    def _resolve_variant_id(self, pipeline_id: str, variant_name_or_id: str) -> str:
        pipeline = PipelineManager().get_pipeline_by_id(pipeline_id)

        for variant in pipeline.variants:
            if variant.id == variant_name_or_id:
                return variant.id
        for variant in pipeline.variants:
            if variant.name == variant_name_or_id:
                return variant.id

        raise ValueError(
            f"Variant '{variant_name_or_id}' not found in pipeline '{pipeline_id}'."
        )

    def _build_internal_performance_spec(
        self,
        pipeline_id: str,
        variant_name_or_id: str,
        streams: int,
    ) -> InternalPerformanceTestSpec:
        pipeline = PipelineManager().get_pipeline_by_id(pipeline_id)
        resolved_variant_id = self._resolve_variant_id(pipeline_id, variant_name_or_id)
        variant = PipelineManager().get_variant_by_ids(pipeline_id, resolved_variant_id)

        return InternalPerformanceTestSpec(
            pipeline_performance_specs=[
                InternalPipelinePerformanceSpec(
                    pipeline_id=f"/pipelines/{pipeline_id}/variants/{resolved_variant_id}",
                    pipeline_name=pipeline.name,
                    pipeline_graph=variant.pipeline_graph,
                    streams=streams,
                )
            ],
            execution_config=InternalExecutionConfig(
                output_mode=InternalOutputMode.DISABLED,
                max_runtime=0,
                metadata_mode=InternalMetadataMode.DISABLED,
            ),
            original_request={
                "pipeline_performance_specs": [
                    {
                        "pipeline": {
                            "source": "variant",
                            "pipeline_id": pipeline_id,
                            "variant_id": resolved_variant_id,
                        },
                        "streams": streams,
                    }
                ],
                "execution_config": {
                    "output_mode": "disabled",
                    "max_runtime": 0,
                    "metadata_mode": "disabled",
                },
            },
        )

    async def _update_test_case_status(
        self,
        test_case_run_id: int,
        status: str,
        start_time_ms: int | None = None,
    ) -> None:
        if async_session_maker is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        async with async_session_maker() as session:
            test_case_run = await session.scalar(
                select(BenchmarkTestCaseRun).where(
                    BenchmarkTestCaseRun.id == test_case_run_id
                )
            )
            if test_case_run is not None:
                test_case_run.status = status
                if (
                    status == "running"
                    and start_time_ms is not None
                    and test_case_run.start_time is None
                ):
                    test_case_run.start_time = start_time_ms
                await session.commit()

    async def _update_workload_run_status(self, workload_run_id: int) -> None:
        """Update workload_run status based on aggregate of its test_case_run statuses."""
        if async_session_maker is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        async with async_session_maker() as session:
            workload_run = await session.scalar(
                select(BenchmarkWorkloadRun).where(
                    BenchmarkWorkloadRun.id == workload_run_id
                )
            )
            if workload_run is None:
                return

            test_case_runs_result = await session.execute(
                select(BenchmarkTestCaseRun).where(
                    BenchmarkTestCaseRun.workload_run_id == workload_run_id
                )
            )
            test_case_runs = test_case_runs_result.scalars().all()

            if not test_case_runs:
                workload_run.status = "created"
            else:
                statuses = {tcr.status for tcr in test_case_runs}

                # If any test case is skipped, mark workload as failed
                if "skipped" in statuses:
                    workload_run.status = "failed"
                elif statuses == {"created"}:
                    workload_run.status = "created"
                elif "running" in statuses:
                    workload_run.status = "running"
                elif "created" in statuses:
                    # Mixed with created means execution is still in progress.
                    workload_run.status = "running"
                elif "failed" in statuses:
                    workload_run.status = "failed"
                elif "cancelled" in statuses:
                    workload_run.status = "cancelled"
                elif statuses == {"passed"}:
                    workload_run.status = "passed"
                else:
                    # Fallback for unexpected terminal combinations.
                    workload_run.status = "failed"

            if (
                workload_run.status in {"passed", "failed", "cancelled"}
                and workload_run.start_time is not None
                and workload_run.execution_time is None
            ):
                workload_run.execution_time = (
                    int(time.time() * 1000) - workload_run.start_time
                )

            if workload_run.status == "passed":
                (
                    workload_run.score_performance,
                    workload_run.score_efficiency,
                    workload_run.score_total,
                ) = scoring.aggregate_scores(list(test_case_runs))

            await session.commit()

    async def _mark_workload_run_started(
        self, workload_run_id: int, start_time_ms: int
    ) -> None:
        if async_session_maker is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        async with async_session_maker() as session:
            workload_run = await session.scalar(
                select(BenchmarkWorkloadRun).where(
                    BenchmarkWorkloadRun.id == workload_run_id
                )
            )
            if workload_run is not None and workload_run.start_time is None:
                workload_run.start_time = start_time_ms
                await session.commit()

    async def _mark_created_runs_cancelled(self, suite_run_id: int) -> None:
        """Mark remaining created workload/test-case runs as cancelled for a suite run."""
        if async_session_maker is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        async with async_session_maker() as session:
            workload_runs_result = await session.execute(
                select(BenchmarkWorkloadRun).where(
                    BenchmarkWorkloadRun.suite_run_id == suite_run_id
                )
            )
            workload_runs = workload_runs_result.scalars().all()

            workload_run_ids = [workload_run.id for workload_run in workload_runs]
            if workload_run_ids:
                test_case_runs_result = await session.execute(
                    select(BenchmarkTestCaseRun).where(
                        BenchmarkTestCaseRun.workload_run_id.in_(workload_run_ids)
                    )
                )
                test_case_runs = test_case_runs_result.scalars().all()
            else:
                test_case_runs = []

            for workload_run in workload_runs:
                if workload_run.status == "running":
                    if (
                        workload_run.start_time is not None
                        and workload_run.execution_time is None
                    ):
                        workload_run.execution_time = (
                            int(time.time() * 1000) - workload_run.start_time
                        )
                    workload_run.status = "cancelled"
                elif workload_run.status == "created":
                    workload_run.status = "cancelled"

            for test_case_run in test_case_runs:
                if test_case_run.status in {"created", "running"}:
                    test_case_run.status = "cancelled"

            await session.commit()

    async def _persist_test_case_result(
        self,
        suite_run_id: int,
        test_case_run_id: int,
        start_time_ms: int,
        execution_time_ms: int | None,
        total_fps: float | None,
        metrics_text: str | None,
        cancelled: bool,
    ) -> None:
        if async_session_maker is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        async with async_session_maker() as session:
            suite_run = await session.scalar(
                select(BenchmarkSuiteRun).where(BenchmarkSuiteRun.id == suite_run_id)
            )
            if suite_run is None:
                raise ValueError(f"BenchmarkSuiteRun with id={suite_run_id} not found.")

            test_case_run = await session.scalar(
                select(BenchmarkTestCaseRun).where(
                    BenchmarkTestCaseRun.id == test_case_run_id
                )
            )
            if test_case_run is None:
                raise ValueError(
                    f"BenchmarkTestCaseRun with id={test_case_run_id} not found."
                )

            benchmark_test_case = await session.scalar(
                select(BenchmarkTestCase).where(
                    BenchmarkTestCase.id == test_case_run.test_case_id
                )
            )

            if test_case_run.start_time is None:
                test_case_run.start_time = start_time_ms
            test_case_run.execution_time = execution_time_ms
            test_case_run.total_fps = total_fps
            parsed_metrics = metrics.parse_metrics_text(metrics_text)
            test_case_run.cpu_usage = metrics.cpu_usage(parsed_metrics)
            test_case_run.gpu_usage = metrics.gpu_usage(parsed_metrics)
            test_case_run.npu_usage = metrics.npu_usage(parsed_metrics)
            test_case_run.media_usage = metrics.media_usage(parsed_metrics)
            test_case_run.memory_usage = metrics.memory_usage(parsed_metrics)
            test_case_run.power_usage = metrics.power_usage(parsed_metrics)
            if (
                total_fps is not None
                and benchmark_test_case is not None
                and benchmark_test_case.streams > 0
            ):
                test_case_run.per_stream_fps = total_fps / benchmark_test_case.streams
            else:
                test_case_run.per_stream_fps = None
            test_case_run.metrics = metrics_text

            if cancelled:
                test_case_run.status = "cancelled"
            elif total_fps is not None:
                test_case_run.status = "passed"
                (
                    test_case_run.score_performance,
                    test_case_run.score_efficiency,
                    test_case_run.score_total,
                ) = scoring.compute_test_case_scores(
                    total_fps=total_fps,
                    cpu_usage=test_case_run.cpu_usage,
                    gpu_usage=test_case_run.gpu_usage,
                    npu_usage=test_case_run.npu_usage,
                    media_usage=test_case_run.media_usage,
                    power_usage=test_case_run.power_usage,
                )
                workload_run = await session.scalar(
                    select(BenchmarkWorkloadRun).where(
                        BenchmarkWorkloadRun.id == test_case_run.workload_run_id
                    )
                )
                if workload_run is not None:
                    workload_run.passed_test_cases = (
                        workload_run.passed_test_cases or 0
                    ) + 1
                suite_run.passed_test_cases = (suite_run.passed_test_cases or 0) + 1
            else:
                test_case_run.status = "failed"

            if execution_time_ms is not None:
                suite_run.execution_time = (
                    suite_run.execution_time or 0
                ) + execution_time_ms

            await session.commit()

    def _execute_benchmark_plan(
        self, benchmark_job_id: str, plan: _BenchmarkPlan
    ) -> None:
        failures = 0
        cancelled_cases = 0

        try:
            for index, planned in enumerate(plan.test_cases, start=1):
                with self._jobs_lock:
                    job = self.jobs.get(benchmark_job_id)
                    if job is None:
                        return
                    if benchmark_job_id in self._cancel_requested:
                        self._run_db(
                            self._mark_created_runs_cancelled(
                                suite_run_id=plan.suite_run_id
                            )
                        )
                        self._run_db(
                            self._update_suite_run_status(
                                suite_run_id=plan.suite_run_id,
                                status="cancelled",
                            )
                        )
                        job.state = InternalTestJobState.FAILED
                        job.end_time = int(time.time() * 1000)
                        job.details = ["Cancelled by user"]
                        return

                    job.current_test_case_run_id = planned.test_case_run_id
                    job.current_performance_job_id = planned.performance_job_id
                    job.details = [f"Running test case {index}/{plan.total_test_cases}"]

                case_start_ms = int(time.time() * 1000)

                self._run_db(
                    self._mark_workload_run_started(
                        workload_run_id=planned.workload_run_id,
                        start_time_ms=case_start_ms,
                    )
                )

                self._run_db(
                    self._update_test_case_status(
                        test_case_run_id=planned.test_case_run_id,
                        status="running",
                        start_time_ms=case_start_ms,
                    )
                )

                self._run_db(
                    self._update_workload_run_status(
                        workload_run_id=planned.workload_run_id
                    )
                )

                pipeline = PipelineManager().get_pipeline_by_id(planned.pipeline_id)
                variant = None
                for v in pipeline.variants:
                    if v.id == planned.variant_id:
                        variant = v
                        break

                if variant is None:
                    logger.warning(
                        f"Variant {planned.variant_id} not found for pipeline {planned.pipeline_id}"
                    )
                    self._run_db(
                        self._update_test_case_status(
                            test_case_run_id=planned.test_case_run_id,
                            status="skipped",
                        )
                    )
                    self._run_db(
                        self._update_workload_run_status(
                            workload_run_id=planned.workload_run_id
                        )
                    )
                    with self._jobs_lock:
                        job = self.jobs.get(benchmark_job_id)
                        if job is not None:
                            job.completed_test_cases = index
                    continue

                if not self._is_device_available(variant.name):
                    logger.info(
                        f"Device {variant.name} not available, skipping test case {planned.test_case_run_id}"
                    )
                    self._run_db(
                        self._update_test_case_status(
                            test_case_run_id=planned.test_case_run_id,
                            status="skipped",
                        )
                    )
                    self._run_db(
                        self._update_workload_run_status(
                            workload_run_id=planned.workload_run_id
                        )
                    )
                    with self._jobs_lock:
                        job = self.jobs.get(benchmark_job_id)
                        if job is not None:
                            job.completed_test_cases = index
                    continue

                internal_spec = self._build_internal_performance_spec(
                    pipeline_id=planned.pipeline_id,
                    variant_name_or_id=planned.variant_id,
                    streams=planned.streams,
                )

                result = TestsManager().test_performance_sync(
                    internal_spec=internal_spec,
                    collect_metrics=True,
                    job_id=planned.performance_job_id,
                )

                perf_status = TestsManager().get_job_status(planned.performance_job_id)
                execution_time_ms: int | None = None
                if isinstance(perf_status, InternalPerformanceJobStatus):
                    if perf_status.end_time is not None:
                        execution_time_ms = (
                            perf_status.end_time - perf_status.start_time
                        )

                if execution_time_ms is None:
                    execution_time_ms = int(time.time() * 1000) - case_start_ms

                self._run_db(
                    self._persist_test_case_result(
                        suite_run_id=plan.suite_run_id,
                        test_case_run_id=planned.test_case_run_id,
                        start_time_ms=case_start_ms,
                        execution_time_ms=execution_time_ms,
                        total_fps=result.get("total_fps"),
                        metrics_text=result.get("metrics"),
                        cancelled=bool(result.get("cancelled", False)),
                    )
                )

                self._run_db(
                    self._update_workload_run_status(
                        workload_run_id=planned.workload_run_id
                    )
                )

                with self._jobs_lock:
                    job = self.jobs.get(benchmark_job_id)
                    if job is None:
                        return

                    cancelled = bool(result.get("cancelled", False))
                    if (
                        result.get("state") != InternalTestJobState.COMPLETED
                        or cancelled
                    ):
                        failures += 1
                    if cancelled:
                        cancelled_cases += 1

                    job.completed_test_cases = index

                    if benchmark_job_id in self._cancel_requested:
                        self._run_db(
                            self._mark_created_runs_cancelled(
                                suite_run_id=plan.suite_run_id
                            )
                        )
                        self._run_db(
                            self._update_suite_run_status(
                                suite_run_id=plan.suite_run_id,
                                status="cancelled",
                            )
                        )
                        job.state = InternalTestJobState.FAILED
                        job.end_time = int(time.time() * 1000)
                        job.details = ["Cancelled by user"]
                        return

            with self._jobs_lock:
                job = self.jobs.get(benchmark_job_id)
                if job is None:
                    return

                job.current_test_case_run_id = None
                job.current_performance_job_id = None
                job.end_time = int(time.time() * 1000)

                if failures == 0:
                    self._run_db(
                        self._update_suite_run_status(
                            suite_run_id=plan.suite_run_id,
                            status="passed",
                        )
                    )
                    job.state = InternalTestJobState.COMPLETED
                    job.details = ["Benchmark suite completed successfully"]
                elif cancelled_cases > 0:
                    self._run_db(
                        self._update_suite_run_status(
                            suite_run_id=plan.suite_run_id,
                            status="cancelled",
                        )
                    )
                    job.state = InternalTestJobState.FAILED
                    job.details = [
                        f"Benchmark suite finished with {cancelled_cases} cancelled test case(s)"
                    ]
                else:
                    self._run_db(
                        self._update_suite_run_status(
                            suite_run_id=plan.suite_run_id,
                            status="failed",
                        )
                    )
                    job.state = InternalTestJobState.FAILED
                    job.details = [
                        f"Benchmark suite finished with {failures} failed test case(s)"
                    ]

        except Exception as exc:
            logger.error("Benchmark suite job %s failed: %s", benchmark_job_id, exc)
            with self._jobs_lock:
                job = self.jobs.get(benchmark_job_id)
                if job is not None:
                    self._run_db(
                        self._update_suite_run_status(
                            suite_run_id=plan.suite_run_id,
                            status="failed",
                        )
                    )
                    job.state = InternalTestJobState.FAILED
                    job.end_time = int(time.time() * 1000)
                    job.details = [str(exc)]
                    job.current_test_case_run_id = None
                    job.current_performance_job_id = None

    def get_job_statuses(self) -> list[InternalBenchmarkJobStatus]:
        with self._jobs_lock:
            return list(self.jobs.values())

    def get_job_status(self, job_id: str) -> InternalBenchmarkJobStatus | None:
        with self._jobs_lock:
            return self.jobs.get(job_id)

    def get_job_summary(self, job_id: str) -> InternalBenchmarkJobSummary | None:
        with self._jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            return InternalBenchmarkJobSummary(
                id=job.id,
                suite_slug=job.suite_slug,
                suite_run_id=job.suite_run_id,
            )

    def stop_job(self, job_id: str) -> tuple[bool, str]:
        with self._jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                return False, f"Job {job_id} not found"
            if job.state != InternalTestJobState.RUNNING:
                return False, f"Job {job_id} is not running (state: {job.state})"

            self._cancel_requested.add(job_id)
            active_performance_job_id = job.current_performance_job_id

        if active_performance_job_id:
            TestsManager().stop_job(active_performance_job_id)

        return True, f"Job {job_id} stopped"
