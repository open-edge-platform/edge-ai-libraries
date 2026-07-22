import asyncio
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from database import async_session_maker
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
        self.logger = logging.getLogger("BenchmarkManager")

    @staticmethod
    def _generate_job_id() -> str:
        return uuid.uuid1().hex

    @staticmethod
    def _run_db(coro):
        return asyncio.run(coro)

    @staticmethod
    def _parse_metrics_text(metrics_text: str | None) -> list[dict]:
        logger = logging.getLogger(__name__)
        if not metrics_text:
            logger.warning("_parse_metrics_text: metrics_text is None or empty")
            return []

        try:
            parsed = json.loads(metrics_text)
        except Exception as e:
            logger.error(f"_parse_metrics_text: Failed to parse JSON: {e}")
            return []

        if not isinstance(parsed, list):
            logger.warning(f"_parse_metrics_text: Expected list, got {type(parsed)}")
            return []

        result = [item for item in parsed if isinstance(item, dict)]
        logger.debug(f"_parse_metrics_text: Parsed {len(result)} dict items from {len(parsed)} total items")
        return result

    @staticmethod
    def _get_metric_values_from_parsed_metrics(
        parsed_metrics: list[dict], metric_name: str
    ) -> list[float]:
        values: list[float] = []

        for event in parsed_metrics:
            metrics = event.get("metrics")
            if not isinstance(metrics, list):
                continue

            for metric in metrics:
                if not isinstance(metric, dict) or metric.get("name") != metric_name:
                    continue

                fields = metric.get("fields")
                raw_value = None
                if isinstance(fields, dict):
                    if "value" in fields:
                        raw_value = fields.get("value")
                    elif metric_name in fields:
                        raw_value = fields.get(metric_name)
                    elif len(fields) == 1:
                        raw_value = next(iter(fields.values()))
                elif "value" in metric:
                    raw_value = metric.get("value")

                if isinstance(raw_value, (int, float)):
                    values.append(float(raw_value))

        return values

    @staticmethod
    def _trim_metric_edge_values(values: list[float]) -> list[float]:
        logger = logging.getLogger(__name__)
        if not values:
            logger.debug("_trim_metric_edge_values: Empty values list")
            return []

        trim_count = int(len(values) * 0.1)
        if trim_count == 0 or trim_count * 2 >= len(values):
            logger.debug(f"_trim_metric_edge_values: Not trimming (len={len(values)}, trim_count={trim_count})")
            return values

        trimmed = values[trim_count:-trim_count]
        logger.debug(f"_trim_metric_edge_values: Trimmed {trim_count} items from each end (before={len(values)}, after={len(trimmed)})")
        return trimmed

    @classmethod
    def _get_average_metric_from_parsed_metrics(
        cls, parsed_metrics: list[dict], metric_name: str
    ) -> float | None:
        values = cls._get_metric_values_from_parsed_metrics(
            parsed_metrics, metric_name=metric_name
        )
        trimmed_values = cls._trim_metric_edge_values(values)
        if not trimmed_values:
            return None
        return sum(trimmed_values) / len(trimmed_values)

    # TODO: maybe better would be to iterate over metrics and process them based on their name, instead of haveing separate methods that iterate over metrics again.
    @classmethod
    def get_cpu_usage_from_parsed_metrics(cls, parsed_metrics: list[dict]) -> float | None:
        return cls._get_average_metric_from_parsed_metrics(
            parsed_metrics, metric_name="cpu_usage_user"
        )

    @classmethod
    def get_gpu_usage_from_parsed_metrics(cls, parsed_metrics: list[dict]) -> float | None:
        primary_values: list[float] = []
        fallback_values: list[float] = []

        for event in parsed_metrics:
            metrics = event.get("metrics")
            if isinstance(metrics, list):
                metric_entries = metrics
            elif event.get("name") == "gpu_engine_usage_usage":
                metric_entries = [event]
            else:
                continue

            for metric in metric_entries:
                if (
                    not isinstance(metric, dict)
                    or metric.get("name") != "gpu_engine_usage_usage"
                ):
                    continue

                labels = metric.get("labels")
                engine = metric.get("engine")
                engine_label = None

                if isinstance(labels, dict):
                    engine_label = labels.get("engine") or labels.get("engine.labels")

                if engine_label is None and isinstance(engine, dict):
                    engine_label = engine.get("labels")

                fields = metric.get("fields")
                raw_value = None
                if isinstance(fields, dict):
                    if "value" in fields:
                        raw_value = fields.get("value")
                    elif "gpu_engine_usage_usage" in fields:
                        raw_value = fields.get("gpu_engine_usage_usage")
                    elif len(fields) == 1:
                        raw_value = next(iter(fields.values()))
                elif "value" in metric:
                    raw_value = metric.get("value")

                if not isinstance(raw_value, (int, float)):
                    continue

                value = float(raw_value)
                if engine_label in {"compute", "ccs"}:
                    primary_values.append(value)
                elif engine_label in {"render", "rcs"}:
                    fallback_values.append(value)

        # Phase 1: select the set with the most non-zero values.
        # Break ties by preferring compute/ccs over render/rcs.
        nonzero_primary_count = sum(1 for v in primary_values if v > 0)
        nonzero_fallback_count = sum(1 for v in fallback_values if v > 0)
        if nonzero_primary_count >= nonzero_fallback_count and nonzero_primary_count > 0:
            selected_values = primary_values
        elif nonzero_fallback_count > 0:
            selected_values = fallback_values
        else:
            selected_values = primary_values or fallback_values

        # Phase 2: calculate the average from the selected set.
        trimmed_values = cls._trim_metric_edge_values(selected_values)
        if not trimmed_values:
            return None
        return sum(trimmed_values) / len(trimmed_values)

    @classmethod
    def get_gpu_usage_from_metrics_text(cls, metrics_text: str | None) -> float | None:
        parsed_metrics = cls._parse_metrics_text(metrics_text)
        return cls.get_gpu_usage_from_parsed_metrics(parsed_metrics)

    @classmethod
    def get_mem_usage_from_parsed_metrics(cls, parsed_metrics: list[dict]) -> float | None:
        return cls._get_average_metric_from_parsed_metrics(
            parsed_metrics, metric_name="mem_used_percent"
        )

    @classmethod
    def get_npu_usage_from_parsed_metrics(cls, parsed_metrics: list[dict]) -> float | None:
        return cls._get_average_metric_from_parsed_metrics(
            parsed_metrics, metric_name="npu_utilization"
        )

    @classmethod
    def get_npu_usage_from_metrics_text(cls, metrics_text: str | None) -> float | None:
        parsed_metrics = cls._parse_metrics_text(metrics_text)
        return cls.get_npu_usage_from_parsed_metrics(parsed_metrics)

    @classmethod
    def get_media_usage_from_parsed_metrics(cls, parsed_metrics: list[dict]) -> float | None:
        # Media usage groups samples by supported media engine labels and returns
        # the highest trimmed average because different platforms can report the
        # same workload under different engine buckets.
        video_values: list[float] = []
        vcs_values: list[float] = []
        video_enhance_values: list[float] = []
        vecs_values: list[float] = []

        for event in parsed_metrics:
            if not isinstance(event, dict):
                continue

            metrics = event.get("metrics")
            if isinstance(metrics, list):
                metric_entries = metrics
            elif event.get("name") == "gpu_engine_usage_usage":
                metric_entries = [event]
            else:
                continue

            for metric in metric_entries:
                if (
                    not isinstance(metric, dict)
                    or metric.get("name") != "gpu_engine_usage_usage"
                ):
                    continue

                labels = metric.get("labels")
                engine = metric.get("engine")
                engine_label = None

                if isinstance(labels, dict):
                    engine_label = labels.get("engine") or labels.get("engine.labels")

                if engine_label is None and isinstance(engine, dict):
                    engine_label = engine.get("labels")

                fields = metric.get("fields")
                raw_value = None
                if isinstance(fields, dict):
                    if "value" in fields:
                        raw_value = fields.get("value")
                    elif "gpu_engine_usage_usage" in fields:
                        raw_value = fields.get("gpu_engine_usage_usage")
                    elif len(fields) == 1:
                        raw_value = next(iter(fields.values()))
                elif "value" in metric:
                    raw_value = metric.get("value")

                if not isinstance(raw_value, (int, float)):
                    continue

                value = float(raw_value)

                if engine_label == "video":
                    video_values.append(value)
                elif engine_label == "vcs":
                    vcs_values.append(value)
                elif engine_label == "video-enhance":
                    video_enhance_values.append(value)
                elif engine_label == "vecs":
                    vecs_values.append(value)

        def average(values: list[float]) -> float | None:
            trimmed_values = cls._trim_metric_edge_values(values)
            if not trimmed_values:
                return None
            avg = sum(trimmed_values) / len(trimmed_values)
            return avg

        video_avg = average(video_values)
        vcs_avg = average(vcs_values)
        video_enhance_avg = average(video_enhance_values)
        vecs_avg = average(vecs_values)

        averages = [avg for avg in [video_avg, vcs_avg, video_enhance_avg, vecs_avg] if avg is not None]
        if not averages:
            return None

        return max(averages)

    @classmethod
    def get_power_usage_from_parsed_metrics(cls, parsed_metrics: list[dict]) -> float | None:
        values: list[float] = []

        for event in parsed_metrics:
            metrics = event.get("metrics")
            if not isinstance(metrics, list):
                continue

            for metric in metrics:
                if not isinstance(metric, dict) or metric.get("name") != "gpu_power":
                    continue

                labels = metric.get("labels")
                if not isinstance(labels, dict) or labels.get("type") != "pkg_cur_power":
                    continue

                fields = metric.get("fields")
                raw_value = None
                if isinstance(fields, dict):
                    if "value" in fields:
                        raw_value = fields.get("value")
                    elif "gpu_power" in fields:
                        raw_value = fields.get("gpu_power")
                    elif len(fields) == 1:
                        raw_value = next(iter(fields.values()))
                elif "value" in metric:
                    raw_value = metric.get("value")

                if isinstance(raw_value, (int, float)):
                    values.append(float(raw_value))

        trimmed_values = cls._trim_metric_edge_values(values)
        if not trimmed_values:
            return None
        return sum(trimmed_values) / len(trimmed_values)

    def start_suite(self, suite_slug: str) -> str:
        job_id = self._generate_job_id()
        plan = self._run_db(self._create_benchmark_plan(suite_slug=suite_slug, job_id=job_id))

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

    async def _create_benchmark_plan(self, suite_slug: str, job_id: str) -> _BenchmarkPlan:
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
                    workload_run_id=workload_run_by_workload_id[test_case.workload_id].id,
                    job_id=performance_job_id,
                    status="created",
                )
                session.add(test_case_run)
                await session.flush()

                planned_cases.append(
                    _PlannedTestCaseRun(
                        test_case_run_id=test_case_run.id,
                        workload_run_id=workload_run_by_workload_id[test_case.workload_id].id,
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
                select(BenchmarkTestCaseRun).where(BenchmarkTestCaseRun.id == test_case_run_id)
            )
            if test_case_run is not None:
                test_case_run.status = status
                if status == "running" and start_time_ms is not None and test_case_run.start_time is None:
                    test_case_run.start_time = start_time_ms
                await session.commit()

    async def _update_workload_run_status(self, workload_run_id: int) -> None:
        """Update workload_run status based on aggregate of its test_case_run statuses."""
        if async_session_maker is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        async with async_session_maker() as session:
            workload_run = await session.scalar(
                select(BenchmarkWorkloadRun).where(BenchmarkWorkloadRun.id == workload_run_id)
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

                if statuses == {"created"}:
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
                workload_run.execution_time = int(time.time() * 1000) - workload_run.start_time

            await session.commit()

    async def _mark_workload_run_started(self, workload_run_id: int, start_time_ms: int) -> None:
        if async_session_maker is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        async with async_session_maker() as session:
            workload_run = await session.scalar(
                select(BenchmarkWorkloadRun).where(BenchmarkWorkloadRun.id == workload_run_id)
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
                select(BenchmarkWorkloadRun).where(BenchmarkWorkloadRun.suite_run_id == suite_run_id)
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
                    if workload_run.start_time is not None and workload_run.execution_time is None:
                        workload_run.execution_time = int(time.time() * 1000) - workload_run.start_time
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
                select(BenchmarkTestCaseRun).where(BenchmarkTestCaseRun.id == test_case_run_id)
            )
            if test_case_run is None:
                raise ValueError(
                    f"BenchmarkTestCaseRun with id={test_case_run_id} not found."
                )

            benchmark_test_case = await session.scalar(
                select(BenchmarkTestCase).where(BenchmarkTestCase.id == test_case_run.test_case_id)
            )

            if test_case_run.start_time is None:
                test_case_run.start_time = start_time_ms
            test_case_run.execution_time = execution_time_ms
            test_case_run.total_fps = total_fps
            parsed_metrics = self._parse_metrics_text(metrics_text)
            test_case_run.cpu_usage = self.get_cpu_usage_from_parsed_metrics(parsed_metrics)
            test_case_run.gpu_usage = self.get_gpu_usage_from_parsed_metrics(parsed_metrics)
            test_case_run.npu_usage = self.get_npu_usage_from_parsed_metrics(parsed_metrics)
            test_case_run.media_usage = self.get_media_usage_from_parsed_metrics(parsed_metrics)
            test_case_run.memory_usage = self.get_mem_usage_from_parsed_metrics(parsed_metrics)
            test_case_run.power_usage = self.get_power_usage_from_parsed_metrics(parsed_metrics)
            if total_fps is not None and benchmark_test_case is not None and benchmark_test_case.streams > 0:
                test_case_run.per_stream_fps = total_fps / benchmark_test_case.streams
            else:
                test_case_run.per_stream_fps = None
            test_case_run.metrics = metrics_text

            if cancelled:
                test_case_run.status = "cancelled"
            elif total_fps is not None:
                test_case_run.status = "passed"
                workload_run = await session.scalar(
                    select(BenchmarkWorkloadRun).where(
                        BenchmarkWorkloadRun.id == test_case_run.workload_run_id
                    )
                )
                if workload_run is not None:
                    workload_run.passed_test_cases = (workload_run.passed_test_cases or 0) + 1
                suite_run.passed_test_cases = (suite_run.passed_test_cases or 0) + 1
            else:
                test_case_run.status = "failed"

            if execution_time_ms is not None:
                suite_run.execution_time = (suite_run.execution_time or 0) + execution_time_ms

            await session.commit()

    def _execute_benchmark_plan(self, benchmark_job_id: str, plan: _BenchmarkPlan) -> None:
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
                            self._mark_created_runs_cancelled(suite_run_id=plan.suite_run_id)
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
                    job.details = [
                        f"Running test case {index}/{plan.total_test_cases}"
                    ]

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
                    self._update_workload_run_status(workload_run_id=planned.workload_run_id)
                )

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
                        execution_time_ms = perf_status.end_time - perf_status.start_time

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
                    self._update_workload_run_status(workload_run_id=planned.workload_run_id)
                )

                with self._jobs_lock:
                    job = self.jobs.get(benchmark_job_id)
                    if job is None:
                        return

                    cancelled = bool(result.get("cancelled", False))
                    if result.get("state") != InternalTestJobState.COMPLETED or cancelled:
                        failures += 1
                    if cancelled:
                        cancelled_cases += 1

                    job.completed_test_cases = index

                    if benchmark_job_id in self._cancel_requested:
                        self._run_db(
                            self._mark_created_runs_cancelled(suite_run_id=plan.suite_run_id)
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
            self.logger.error("Benchmark suite job %s failed: %s", benchmark_job_id, exc)
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
