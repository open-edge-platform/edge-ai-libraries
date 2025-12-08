import logging
import sys
import threading
import time
from typing import Dict, Optional, List
from dataclasses import dataclass
import uuid

from api.api_schemas import (
    DensityJobSummary,
    DensityTestSpec,
    PerformanceJobSummary,
    PerformanceTestSpec,
    TestJobState,
    PipelinePerformanceSpec,
    PerformanceJobStatus,
    DensityJobStatus,
    TestsJobStatus,
)
from pipeline_runner import PipelineRunner
from benchmark import Benchmark
from managers.pipeline_manager import get_pipeline_manager

logger = logging.getLogger("tests_manager")

pipeline_manager = get_pipeline_manager()

# Singleton instance for TestsManager
_tests_manager_instance: Optional["TestsManager"] = None


def get_tests_manager() -> "TestsManager":
    """
    Return the singleton instance of :class:`TestsManager`.

    The first call lazily creates the instance.  If initialization fails
    for any reason the error is logged and the process is terminated.
    """
    global _tests_manager_instance
    if _tests_manager_instance is None:
        try:
            _tests_manager_instance = TestsManager()
        except Exception as e:
            logger.error(f"Failed to initialize TestsManager: {e}")
            sys.exit(1)
    return _tests_manager_instance


@dataclass
class PerformanceJob:
    """
    Internal representation of a single performance test job.

    This mirrors what is exposed through :class:`PerformanceJobStatus`
    and :class:`PerformanceJobSummary`, with a few runtime-only fields.
    """

    id: str
    request: PerformanceTestSpec
    state: TestJobState
    start_time: int
    end_time: Optional[int] = None
    total_fps: Optional[float] = None
    per_stream_fps: Optional[float] = None
    total_streams: Optional[int] = None
    streams_per_pipeline: Optional[List[PipelinePerformanceSpec]] = None
    video_output_paths: Optional[Dict[str, List[str]]] = None
    error_message: Optional[str] = None


@dataclass
class DensityJob:
    """
    Internal representation of a single density test job.

    This mirrors what is exposed through :class:`DensityJobStatus`
    and :class:`DensityJobSummary`, with a few runtime-only fields.
    """

    id: str
    request: DensityTestSpec
    state: TestJobState
    start_time: int
    end_time: Optional[int] = None
    total_fps: Optional[float] = None
    per_stream_fps: Optional[float] = None
    total_streams: Optional[int] = None
    streams_per_pipeline: Optional[List[PipelinePerformanceSpec]] = None
    video_output_paths: Optional[Dict[str, List[str]]] = None
    error_message: Optional[str] = None


class TestsManager:
    """
    Manage performance and density test jobs for pipelines.

    Responsibilities:

    * create and track :class:`PerformanceJob` and :class:`DensityJob` instances,
    * run tests asynchronously in background threads,
    * expose job status and summaries in a thread-safe manner.
    """

    def __init__(self):
        # All known jobs keyed by job id
        self.jobs: Dict[str, PerformanceJob | DensityJob] = {}
        # Currently running PipelineRunner or Benchmark jobs keyed by job id
        self.runners: Dict[str, PipelineRunner | Benchmark] = {}
        # Shared lock protecting access to ``jobs`` and ``runners``
        self.lock = threading.Lock()
        self.logger = logging.getLogger("TestsManager")

    @staticmethod
    def _generate_job_id() -> str:
        """
        Generate a unique job ID using UUID.
        """
        return uuid.uuid1().hex

    def _start_job(
        self,
        test_request: PerformanceTestSpec | DensityTestSpec,
        target_func,
    ) -> str:
        """
        Helper to start a performance or density test and return the job ID.

        The method:

        * creates a new job record with RUNNING state,
        * spawns a background thread that executes the test.
        """
        job_id = self._generate_job_id()

        # Create job record
        job: PerformanceJob | DensityJob
        if isinstance(test_request, PerformanceTestSpec):
            job = PerformanceJob(
                id=job_id,
                request=test_request,
                state=TestJobState.RUNNING,
                start_time=int(time.time() * 1000),  # milliseconds
            )
        else:  # DensityTestSpec
            job = DensityJob(
                id=job_id,
                request=test_request,
                state=TestJobState.RUNNING,
                start_time=int(time.time() * 1000),  # milliseconds
            )

        with self.lock:
            self.jobs[job_id] = job

        # Start execution in background thread
        thread = threading.Thread(
            target=target_func,
            args=(job_id, test_request),
            daemon=True,
        )
        thread.start()

        self.logger.info(
            f"{'Test density' if target_func == self._execute_density_test else 'Test performance'} started for job {job_id}"
        )

        return job_id

    def test_performance(self, performance_request: PerformanceTestSpec) -> str:
        """
        Start a performance test job in the background and return its job id.

        The method creates a new :class:`PerformanceJob` and spawns a
        background thread that executes the performance test.
        """
        return self._start_job(performance_request, self._execute_performance_test)

    def test_density(self, density_request: DensityTestSpec) -> str:
        """
        Start a density test job in the background and return its job id.

        The method creates a new :class:`DensityJob` and spawns a
        background thread that executes the density test.
        """
        return self._start_job(density_request, self._execute_density_test)

    def _execute_performance_test(
        self,
        job_id: str,
        performance_request: PerformanceTestSpec,
    ):
        """
        Execute the performance test in a background thread.

        The method builds the pipeline command, executes it using
        :class:`PipelineRunner` and then updates the corresponding
        :class:`PerformanceJob` accordingly.
        """
        try:
            # Calculate total streams
            total_streams = sum(
                spec.streams for spec in performance_request.pipeline_performance_specs
            )

            if total_streams == 0:
                self._update_job_error(
                    job_id,
                    "At least one stream must be specified to run the pipeline.",
                )
                return

            # Build pipeline command from specs
            pipeline_command, video_output_paths = (
                pipeline_manager.build_pipeline_command(
                    performance_request.pipeline_performance_specs,
                    performance_request.video_output,
                )
            )

            # Initialize PipelineRunner
            runner = PipelineRunner()

            # Store runner for this job so that a future extension could cancel it.
            with self.lock:
                self.runners[job_id] = runner

            # Run the pipeline
            results = runner.run(
                pipeline_command=pipeline_command,
                total_streams=total_streams,
            )

            # Update job with results
            with self.lock:
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

                        if results is not None:
                            # Build streams distribution per pipeline
                            streams_per_pipeline = [
                                PipelinePerformanceSpec(
                                    id=spec.id,
                                    streams=spec.streams,
                                )
                                for spec in performance_request.pipeline_performance_specs
                            ]

                            # Update performance metrics
                            job.total_fps = results.total_fps
                            job.per_stream_fps = results.per_stream_fps
                            job.total_streams = results.num_streams
                            job.streams_per_pipeline = streams_per_pipeline
                            job.video_output_paths = video_output_paths

                            self.logger.info(
                                f"Performance test {job_id} completed successfully: "
                                f"total_fps={results.total_fps}, "
                                f"per_stream_fps={results.per_stream_fps}, "
                                f"total_streams={results.num_streams}"
                            )

                # Clean up runner after completion regardless of outcome
                self.runners.pop(job_id, None)

        except Exception as e:
            # Clean up runner on error
            with self.lock:
                self.runners.pop(job_id, None)
            self._update_job_error(job_id, str(e))

    def _execute_density_test(
        self,
        job_id: str,
        density_request: DensityTestSpec,
    ):
        """
        Execute the density test in a background thread.

        The method runs the benchmark using :class:`Benchmark` and then
        updates the corresponding :class:`DensityJob` accordingly.
        """
        try:
            # Initialize Benchmark
            benchmark = Benchmark()

            # Store benchmark runner for this job so that a future extension could cancel it.
            with self.lock:
                self.runners[job_id] = benchmark

            # Run the benchmark
            results = benchmark.run(
                pipeline_benchmark_specs=density_request.pipeline_density_specs,
                fps_floor=density_request.fps_floor,
                video_config=density_request.video_output,
            )

            # Update job with results
            with self.lock:
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
            with self.lock:
                self.runners.pop(job_id, None)
            self._update_job_error(job_id, str(e))

    def _update_job_error(self, job_id: str, error_message: str) -> None:
        """
        Mark the job as failed and persist the error message.

        Used both for validation errors and unexpected exceptions.
        """
        with self.lock:
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
            error_message=job.error_message,
        )

    def _build_density_status(self, job: DensityJob) -> DensityJobStatus:
        """
        Build a :class:`DensityJobStatus` DTO from the internal job object.

        This method centralises the mapping to ensure consistency between
        status queries.
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
        with self.lock:
            statuses: list[TestsJobStatus] = []
            for job in self.jobs.values():
                if job_type == PerformanceJob and isinstance(job, PerformanceJob):
                    statuses.append(self._build_performance_status(job))
                elif job_type == DensityJob and isinstance(job, DensityJob):
                    statuses.append(self._build_density_status(job))
            self.logger.debug(f"Current job statuses for type {job_type}: {statuses}")
            return statuses

    def get_job_status(self, job_id: str) -> Optional[TestsJobStatus]:
        """
        Return the status for a single job.

        ``None`` is returned when the job id is unknown.
        """
        with self.lock:
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
    ) -> Optional[PerformanceJobSummary | DensityJobSummary]:
        """
        Return a short summary for a single job.

        The summary intentionally contains only the job id and the original
        test request.
        """
        with self.lock:
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
        with self.lock:
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
