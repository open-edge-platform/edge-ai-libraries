import logging
import threading
import time
from dataclasses import dataclass
import uuid
from typing import Any, Dict, Optional

from api.api_schemas import (
    DensityJobStatus,
    DensityJobSummary,
    PerformanceJobStatus,
    PerformanceJobSummary,
    PipelineStreamSpec,
    TestJobState,
    TestsJobStatus,
)
from internal_types import (
    InternalExecutionConfig,
    InternalOutputMode,
    InternalDensityTestSpec,
    InternalPerformanceTestSpec,
)
from pipeline_runner import PipelineRunner, PipelineRunResult
from benchmark import Benchmark
from managers.pipeline_manager import PipelineManager

logger = logging.getLogger("tests_manager")


@dataclass
class PerformanceJob:
    """
    Internal representation of a single performance test job.

    This mirrors what is exposed through :class:`PerformanceJobStatus`
    and :class:`PerformanceJobSummary`, with a few runtime-only fields.

    The streams_per_pipeline field contains pipeline IDs in the format:
    * For variant reference: "/pipelines/{pipeline_id}/variants/{variant_id}"
    * For inline graph: "__graph-{16-char-hash}"

    Attributes:
        id: Unique job identifier.
        request: Original API request as serialized dict (for summary endpoint).
        state: Current job state.
        start_time: Job start time in milliseconds since epoch.
        end_time: Job end time in milliseconds since epoch (None if running).
        total_fps: Total FPS across all streams.
        per_stream_fps: Average FPS per stream.
        total_streams: Number of active streams.
        streams_per_pipeline: List of pipeline IDs with stream counts.
        video_output_paths: Mapping from pipeline ID to output file paths.
        live_stream_urls: Mapping from pipeline ID to live stream URL.
        error_message: Error description when state is ERROR or ABORTED.
    """

    id: str
    request: Dict[str, Any]
    state: TestJobState
    start_time: int
    end_time: int | None = None
    total_fps: float | None = None
    per_stream_fps: float | None = None
    total_streams: int | None = None
    streams_per_pipeline: list[PipelineStreamSpec] | None = None
    video_output_paths: dict[str, list[str]] | None = None
    live_stream_urls: dict[str, str] | None = None
    error_message: str | None = None


@dataclass
class DensityJob:
    """
    Internal representation of a single density test job.

    This mirrors what is exposed through :class:`DensityJobStatus`
    and :class:`DensityJobSummary`, with a few runtime-only fields.

    The streams_per_pipeline field contains pipeline IDs in the format:
    * For variant reference: "/pipelines/{pipeline_id}/variants/{variant_id}"
    * For inline graph: "__graph-{16-char-hash}"

    Note: live_stream_urls is not included because density tests do not support
    live-streaming output mode.

    Attributes:
        id: Unique job identifier.
        request: Original API request as serialized dict (for summary endpoint).
        state: Current job state.
        start_time: Job start time in milliseconds since epoch.
        end_time: Job end time in milliseconds since epoch (None if running).
        total_fps: Total FPS across all streams.
        per_stream_fps: Average FPS per stream.
        total_streams: Number of active streams.
        streams_per_pipeline: List of pipeline IDs with stream counts.
        video_output_paths: Mapping from pipeline ID to output file paths.
        error_message: Error description when state is ERROR or ABORTED.
    """

    id: str
    request: Dict[str, Any]
    state: TestJobState
    start_time: int
    end_time: int | None = None
    total_fps: float | None = None
    per_stream_fps: float | None = None
    total_streams: int | None = None
    streams_per_pipeline: list[PipelineStreamSpec] | None = None
    video_output_paths: dict[str, list[str]] | None = None
    error_message: str | None = None


class TestsManager:
    """
    Thread-safe singleton that manages performance and density test jobs for pipelines.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with TestsManager() to get the shared singleton instance.

    Responsibilities:

    * create and track :class:`PerformanceJob` and :class:`DensityJob` instances,
    * run tests asynchronously in background threads,
    * expose job status and summaries in a thread-safe manner.

    Note: This manager works with internal types (InternalPerformanceTestSpec,
    InternalDensityTestSpec) for execution. Original API requests are stored
    inside internal specs and extracted for summary endpoints.
    """

    _instance: Optional["TestsManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "TestsManager":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # All known jobs keyed by job id
        self.jobs: dict[str, PerformanceJob | DensityJob] = {}
        # Currently running PipelineRunner or Benchmark jobs keyed by job id
        self.runners: dict[str, PipelineRunner | Benchmark] = {}
        # Shared lock protecting access to ``jobs`` and ``runners``
        self._jobs_lock = threading.Lock()
        self.logger = logging.getLogger("TestsManager")
        # Pipeline manager instance
        self.pipeline_manager = PipelineManager()

    @staticmethod
    def _generate_job_id() -> str:
        """
        Generate a unique job ID using UUID.
        """
        return uuid.uuid1().hex

    def test_performance(
        self,
        internal_spec: InternalPerformanceTestSpec,
    ) -> str:
        """
        Start a performance test job in the background and return its job id.

        The method creates a new :class:`PerformanceJob` and spawns a
        background thread that executes the performance test.

        Args:
            internal_spec: Validated and converted internal test specification
                with resolved pipeline information. Contains original_request
                dict for summary endpoint.

        Returns:
            Job ID of the created performance job.
        """
        job_id = self._generate_job_id()

        # Create job record with original request dict from internal spec
        job = PerformanceJob(
            id=job_id,
            request=internal_spec.original_request,
            state=TestJobState.RUNNING,
            start_time=int(time.time() * 1000),  # milliseconds
        )

        with self._jobs_lock:
            self.jobs[job_id] = job

        # Start execution in background thread
        thread = threading.Thread(
            target=self._execute_performance_test,
            args=(job_id, internal_spec),
            daemon=True,
        )
        thread.start()

        self.logger.info(f"Performance test started for job {job_id}")

        return job_id

    def test_density(
        self,
        internal_spec: InternalDensityTestSpec,
    ) -> str:
        """
        Start a density test job in the background and return its job id.

        The method creates a new :class:`DensityJob` and spawns a
        background thread that executes the density test.

        Args:
            internal_spec: Validated and converted internal test specification
                with resolved pipeline information. Contains original_request
                dict for summary endpoint.

        Returns:
            Job ID of the created density job.
        """
        job_id = self._generate_job_id()

        # Create job record with original request dict from internal spec
        job = DensityJob(
            id=job_id,
            request=internal_spec.original_request,
            state=TestJobState.RUNNING,
            start_time=int(time.time() * 1000),  # milliseconds
        )

        with self._jobs_lock:
            self.jobs[job_id] = job

        # Start execution in background thread
        thread = threading.Thread(
            target=self._execute_density_test,
            args=(job_id, internal_spec),
            daemon=True,
        )
        thread.start()

        self.logger.info(f"Density test started for job {job_id}")

        return job_id

    def _validate_execution_config(
        self, execution_config: InternalExecutionConfig, is_density_test: bool = False
    ) -> None:
        """
        Validate execution_config for invalid combinations.

        Args:
            execution_config: InternalExecutionConfig to validate.
            is_density_test: If True, also validate that live_stream is not used.

        Raises:
            ValueError: If output_mode=file is combined with max_runtime>0.
            ValueError: If output_mode=live_stream is used for density tests.
        """
        if (
            execution_config.output_mode == InternalOutputMode.FILE
            and execution_config.max_runtime > 0
        ):
            raise ValueError(
                "Invalid execution_config: output_mode='file' cannot be combined with max_runtime > 0. "
                "File output does not support looping. Use max_runtime=0 to run until EOS, "
                "or use output_mode='disabled' or 'live_stream' for time-limited execution."
            )

        if (
            is_density_test
            and execution_config.output_mode == InternalOutputMode.LIVE_STREAM
        ):
            raise ValueError(
                "Density tests do not support output_mode='live_stream'. "
                "Use output_mode='disabled' or output_mode='file' instead."
            )

    def _execute_performance_test(
        self,
        job_id: str,
        internal_spec: InternalPerformanceTestSpec,
    ):
        """
        Execute the performance test in a background thread.

        The method builds the pipeline command using internal types, executes it
        using :class:`PipelineRunner` and then updates the corresponding
        :class:`PerformanceJob` accordingly.

        Args:
            job_id: Job identifier.
            internal_spec: Internal test specification with resolved pipeline information.
        """
        try:
            # Validate execution_config (performance tests support all output modes)
            self._validate_execution_config(
                internal_spec.execution_config, is_density_test=False
            )

            # Calculate total streams
            total_streams = sum(
                spec.streams for spec in internal_spec.pipeline_performance_specs
            )

            if total_streams == 0:
                self._update_job_error(
                    job_id,
                    "At least one stream must be specified to run the pipeline.",
                )
                return

            # Build pipeline command from specs
            pipeline_command, video_output_paths, live_stream_urls = (
                self.pipeline_manager.build_pipeline_command(
                    internal_spec.pipeline_performance_specs,
                    internal_spec.execution_config,
                    job_id,
                )
            )

            # Build streams_per_pipeline from internal specs (pipeline_id already resolved)
            streams_per_pipeline = [
                PipelineStreamSpec(id=spec.pipeline_id, streams=spec.streams)
                for spec in internal_spec.pipeline_performance_specs
            ]

            # Update job with live_stream_urls and streams_per_pipeline immediately
            with self._jobs_lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]
                    job.streams_per_pipeline = streams_per_pipeline

                    # Type guard: ensure we have a PerformanceJob
                    if not isinstance(job, PerformanceJob):
                        self.logger.error(
                            f"Job {job_id} is not a PerformanceJob, skipping update"
                        )
                    else:
                        job.live_stream_urls = live_stream_urls
                        self.logger.debug(
                            f"Updated job {job_id} with live_stream_urls: {live_stream_urls}"
                        )

            # Initialize PipelineRunner in normal mode with max_runtime from execution_config
            runner = PipelineRunner(
                mode="normal",
                max_runtime=internal_spec.execution_config.max_runtime,
            )

            # Store runner for this job so that a future extension could cancel it.
            with self._jobs_lock:
                self.runners[job_id] = runner

            # Run the pipeline
            result = runner.run(
                pipeline_command=pipeline_command,
                total_streams=total_streams,
            )

            # Type narrowing: PipelineRunner in normal mode returns PipelineRunResult
            if not isinstance(result, PipelineRunResult):
                self._update_job_error(
                    job_id,
                    "Unexpected result type from pipeline runner",
                )
                return

            # Update job with results
            with self._jobs_lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]

                    # Check if job was cancelled while running
                    if runner.is_cancelled():
                        self.logger.info(
                            f"Performance test {job_id} was cancelled, updating state to ABORTED"
                        )
                        job.state = TestJobState.ABORTED
                        job.end_time = int(time.time() * 1000)
                        job.error_message = "Cancelled by user"
                    else:
                        # Normal completion
                        job.state = TestJobState.COMPLETED
                        job.end_time = int(time.time() * 1000)

                        # Update performance metrics
                        job.total_fps = result.total_fps
                        job.per_stream_fps = result.per_stream_fps
                        job.total_streams = result.num_streams
                        job.video_output_paths = video_output_paths

                        self.logger.info(
                            f"Performance test {job_id} completed successfully: "
                            f"total_fps={result.total_fps}, "
                            f"per_stream_fps={result.per_stream_fps}, "
                            f"total_streams={result.num_streams}"
                        )

                # Clean up runner after completion regardless of outcome
                self.runners.pop(job_id, None)

        except Exception as e:
            # Clean up runner on error
            with self._jobs_lock:
                self.runners.pop(job_id, None)
            self._update_job_error(job_id, str(e))

    def _execute_density_test(
        self,
        job_id: str,
        internal_spec: InternalDensityTestSpec,
    ):
        """
        Execute the density test in a background thread.

        The method runs the benchmark using :class:`Benchmark` and then
        updates the corresponding :class:`DensityJob` accordingly.

        Note: Density tests do not support live-streaming output mode.

        Args:
            job_id: Job identifier.
            internal_spec: Internal test specification with resolved pipeline information.
        """
        try:
            # Validate execution_config (density tests do not support live_stream)
            self._validate_execution_config(
                internal_spec.execution_config, is_density_test=True
            )

            # Initialize Benchmark
            benchmark = Benchmark()

            # Store benchmark runner for this job so that a future extension could cancel it.
            with self._jobs_lock:
                self.runners[job_id] = benchmark

            # Run the benchmark
            results = benchmark.run(
                pipeline_density_specs=internal_spec.pipeline_density_specs,
                fps_floor=internal_spec.fps_floor,
                execution_config=internal_spec.execution_config,
                job_id=job_id,
            )

            # Update job with results
            with self._jobs_lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]

                    # Check if job was cancelled while running
                    if benchmark.runner.is_cancelled():
                        self.logger.info(
                            f"Density test {job_id} was cancelled, updating state to ABORTED"
                        )
                        job.state = TestJobState.ABORTED
                        job.end_time = int(time.time() * 1000)
                        job.error_message = "Cancelled by user"
                    else:
                        # Normal completion
                        job.state = TestJobState.COMPLETED
                        job.end_time = int(time.time() * 1000)

                        job.total_fps = None
                        job.per_stream_fps = results.per_stream_fps
                        job.streams_per_pipeline = results.streams_per_pipeline
                        job.total_streams = results.n_streams
                        job.video_output_paths = results.video_output_paths

                        self.logger.info(
                            f"Density test {job_id} completed successfully: "
                            f"streams={results.n_streams}, "
                            f"streams_per_pipeline={results.streams_per_pipeline}, "
                            f"per_stream_fps={results.per_stream_fps}"
                        )

                # Clean up benchmark after completion regardless of outcome
                self.runners.pop(job_id, None)

        except Exception as e:
            # Clean up benchmark on error
            with self._jobs_lock:
                self.runners.pop(job_id, None)
            self._update_job_error(job_id, str(e))

    def _update_job_error(self, job_id: str, error_message: str) -> None:
        """
        Mark the job as failed and persist the error message.

        Used both for validation errors and unexpected exceptions.
        """
        with self._jobs_lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.state = TestJobState.ERROR
                job.end_time = int(time.time() * 1000)
                job.error_message = error_message
        self.logger.error(f"Test job {job_id} error: {error_message}")

    def _build_performance_status(self, job: PerformanceJob) -> PerformanceJobStatus:
        """
        Build a :class:`PerformanceJobStatus` DTO from the internal job object.

        This method centralises the mapping to ensure consistency between
        status queries.
        """
        current_time = int(time.time() * 1000)
        elapsed_time = (
            job.end_time - job.start_time
            if job.end_time
            else current_time - job.start_time
        )
        return PerformanceJobStatus(
            id=job.id,
            start_time=job.start_time,
            elapsed_time=elapsed_time,
            state=job.state,
            total_fps=job.total_fps,
            per_stream_fps=job.per_stream_fps,
            total_streams=job.total_streams,
            streams_per_pipeline=job.streams_per_pipeline,
            video_output_paths=job.video_output_paths,
            live_stream_urls=job.live_stream_urls,
            error_message=job.error_message,
        )

    def _build_density_status(self, job: DensityJob) -> DensityJobStatus:
        """
        Build a :class:`DensityJobStatus` DTO from the internal job object.

        This method centralises the mapping to ensure consistency between
        status queries.

        Note: DensityJobStatus does not include live_stream_urls because
        density tests do not support live-streaming output mode.
        """
        current_time = int(time.time() * 1000)
        elapsed_time = (
            job.end_time - job.start_time
            if job.end_time
            else current_time - job.start_time
        )
        return DensityJobStatus(
            id=job.id,
            start_time=job.start_time,
            elapsed_time=elapsed_time,
            state=job.state,
            total_fps=job.total_fps,
            per_stream_fps=job.per_stream_fps,
            total_streams=job.total_streams,
            streams_per_pipeline=job.streams_per_pipeline,
            video_output_paths=job.video_output_paths,
            error_message=job.error_message,
        )

    def get_job_statuses_by_type(self, job_type) -> list[TestsJobStatus]:
        """
        Return statuses for all jobs of a specific type.

        The ``job_type`` parameter should be either :class:`PerformanceJob`
        or :class:`DensityJob`.  Access is protected by a lock to avoid
        reading partial updates.
        """
        with self._jobs_lock:
            statuses: list[TestsJobStatus] = []
            for job in self.jobs.values():
                if job_type == PerformanceJob and isinstance(job, PerformanceJob):
                    statuses.append(self._build_performance_status(job))
                elif job_type == DensityJob and isinstance(job, DensityJob):
                    statuses.append(self._build_density_status(job))
            self.logger.debug(f"Current job statuses for type {job_type}: {statuses}")
            return statuses

    def get_job_status(self, job_id: str) -> TestsJobStatus | None:
        """
        Return the status for a single job.

        ``None`` is returned when the job id is unknown.
        """
        with self._jobs_lock:
            if job_id not in self.jobs:
                return None
            job = self.jobs[job_id]
            if isinstance(job, PerformanceJob):
                job_status = self._build_performance_status(job)
            elif isinstance(job, DensityJob):
                job_status = self._build_density_status(job)
            else:
                job_status = None
            self.logger.debug(f"Test job status for {job_id}: {job_status}")
            return job_status

    def get_job_summary(
        self, job_id: str
    ) -> PerformanceJobSummary | DensityJobSummary | None:
        """
        Return a short summary for a single job.

        The summary intentionally contains only the job id and the original
        test request.
        """
        with self._jobs_lock:
            if job_id not in self.jobs:
                return None

            job = self.jobs[job_id]

            if isinstance(job, PerformanceJob):
                job_summary = PerformanceJobSummary(
                    id=job.id,
                    request=job.request,
                )
            else:  # DensityJob
                job_summary = DensityJobSummary(
                    id=job.id,
                    request=job.request,
                )

            self.logger.debug(f"Test job summary for {job_id}: {job_summary}")

            return job_summary

    def stop_job(self, job_id: str) -> tuple[bool, str]:
        """
        Stop a running test job by calling cancel on its runner.

        Returns a tuple of (success, message) indicating whether the
        cancellation was successful and a human-readable status message.
        """
        with self._jobs_lock:
            if job_id not in self.jobs:
                msg = f"Job {job_id} not found"
                self.logger.warning(msg)
                return False, msg

            if job_id not in self.runners:
                msg = f"No active runner found for job {job_id}. It may have already completed or was never started."
                self.logger.warning(msg)
                return False, msg

            job = self.jobs[job_id]

            if job.state != TestJobState.RUNNING:
                msg = f"Job {job_id} is not running (state: {job.state})"
                self.logger.warning(msg)
                return False, msg

            runner = self.runners.get(job_id)
            if runner is None:
                msg = f"No active runner found for job {job_id}"
                self.logger.warning(msg)
                return False, msg

            runner.cancel()
            msg = f"Job {job_id} stopped"
            self.logger.info(msg)
            return True, msg
