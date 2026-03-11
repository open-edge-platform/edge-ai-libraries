import logging
import threading
import time
import uuid
from typing import TypeVar
from graph import Graph

from internal_types import (
    InternalDensityJobStatus,
    InternalDensityJobSummary,
    InternalExecutionConfig,
    InternalOutputMode,
    InternalDensityTestSpec,
    InternalPerformanceJobStatus,
    InternalPerformanceJobSummary,
    InternalPerformanceTestSpec,
    InternalPipelinePerformanceSpec,
    InternalPipelineDensitySpec,
    InternalPipelineStreamSpec,
    InternalTestJobState,
)
from pipeline_runner import PipelineRunner
from benchmark import Benchmark
from managers.pipeline_manager import PipelineManager
from videos import collect_video_outputs_from_dirs

logger = logging.getLogger("tests_manager")

_T = TypeVar("_T", InternalPerformanceJobStatus, InternalDensityJobStatus)


class TestsManager:
    """
    Thread-safe singleton that manages performance and density test jobs for pipelines.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with TestsManager() to get the shared singleton instance.

    Responsibilities:

    * create and track :class:`InternalPerformanceJobStatus` and :class:`InternalDensityJobStatus` instances,
    * run tests asynchronously in background threads,
    * expose job status and summaries in a thread-safe manner.

    This manager works exclusively with internal types. Conversion to API
    types happens in the route layer.
    """

    _instance: "TestsManager | None" = None
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
        self.jobs: dict[
            str, InternalPerformanceJobStatus | InternalDensityJobStatus
        ] = {}
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

        The method creates a new :class:`InternalPerformanceJobStatus` and spawns a
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
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            state=InternalTestJobState.RUNNING,
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

        The method creates a new :class:`InternalDensityJobStatus` and spawns a
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
        job = InternalDensityJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            state=InternalTestJobState.RUNNING,
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

    def _get_usb_camera_devices(self, pipeline_graph: Graph) -> list[str]:
        """
        Get list of USB camera device paths from a pipeline graph.

        Args:
            pipeline_graph: Graph object containing pipeline nodes.

        Returns:
            list[str]: List of USB camera device paths (e.g., ['/dev/video0']).
                      Empty list if no USB cameras are found.
        """
        devices = []
        for node in pipeline_graph.nodes:
            if node.type == "v4l2src":
                device = node.data.get("device", "/dev/video0")
                devices.append(device)
        return devices

    def _validate_usb_camera_for_performance(
        self, pipeline_performance_specs: list[InternalPipelinePerformanceSpec]
    ) -> None:
        """
        Validate USB camera usage in performance tests.

        Each USB camera device can only be used in a single pipeline with a single stream
        because the underlying hardware device can only be opened by one process at a time.

        Args:
            pipeline_performance_specs: List of InternalPipelinePerformanceSpec objects.

        Raises:
            ValueError: If any USB camera device is used with multiple streams or in multiple pipelines.
        """
        device_usage = {}

        for spec in pipeline_performance_specs:
            devices = self._get_usb_camera_devices(spec.pipeline_graph)
            for device in devices:
                if device not in device_usage:
                    device_usage[device] = []
                device_usage[device].append((spec.pipeline_name, spec.streams))

        # Validate each USB camera device is used only once with one stream
        errors = []
        for device, usages in device_usage.items():
            total_streams = sum(streams for _, streams in usages)
            pipeline_names = [name for name, _ in usages]

            # Each device can only be in one pipeline with one stream
            if len(usages) > 1 or total_streams > 1:
                errors.append(
                    f"USB camera device '{device}' can only be used in one pipeline with one stream. "
                    f"Found in {len(usages)} pipeline(s) with total {total_streams} stream(s): "
                    f"{', '.join(pipeline_names)}"
                )

        if errors:
            raise ValueError("\n".join(errors))

    def _validate_no_usb_camera_for_density(
        self, pipeline_density_specs: list[InternalPipelineDensitySpec]
    ) -> None:
        """
        Validate that no pipeline uses USB camera in density tests.

        Density tests are not compatible with USB cameras because they require
        spawning multiple pipeline instances, but USB camera devices can only
        be opened by one process at a time.

        Args:
            pipeline_density_specs: List of InternalPipelineDensitySpec objects.

        Raises:
            ValueError: If any pipeline uses a USB camera source.
        """
        pipelines_with_usb = []

        for spec in pipeline_density_specs:
            devices = self._get_usb_camera_devices(spec.pipeline_graph)
            if devices:
                pipelines_with_usb.append(
                    f"{spec.pipeline_name} (devices: {', '.join(devices)})"
                )

        if pipelines_with_usb:
            raise ValueError(
                f"USB camera input sources are not supported in density tests. "
                f"USB camera devices can only be opened by one process at a time, "
                f"which is incompatible with density testing that spawns multiple pipeline instances. "
                f"Pipelines with USB camera: {'; '.join(pipelines_with_usb)}"
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
        :class:`InternalPerformanceJobStatus` accordingly.

        When a job is cancelled by the user:
        - If the pipeline exit code is 0, the job is marked COMPLETED and all
          result data (fps, streams, output paths) is saved.
        - If the pipeline exit code is non-zero, the job is marked FAILED.

        When the pipeline finishes without cancellation:
        - Non-zero exit codes raise RuntimeError inside PipelineRunner,
          which is caught by the except block below and marks the job FAILED.
        - Zero exit code means normal successful completion (COMPLETED).

        The details list is cleared when transitioning to a new state, then
        new entries for that state are appended.

        After pipeline completes, output directory paths are scanned to collect
        the actual video file lists using collect_video_outputs_from_dirs().

        Args:
            job_id: Job identifier.
            internal_spec: Internal test specification with resolved pipeline information.
        """
        try:
            # Validate execution_config (performance tests support all output modes)
            self._validate_execution_config(
                internal_spec.execution_config, is_density_test=False
            )

            # Validate USB camera usage for performance tests
            self._validate_usb_camera_for_performance(
                internal_spec.pipeline_performance_specs
            )

            # Calculate total streams
            total_streams = sum(
                spec.streams for spec in internal_spec.pipeline_performance_specs
            )

            if total_streams == 0:
                self._update_job_failed(
                    job_id,
                    "At least one stream must be specified to run the pipeline.",
                )
                return

            # Build pipeline command from specs
            # video_output_dirs maps pipeline IDs to their output directory paths
            pipeline_command, video_output_dirs, live_stream_urls = (
                self.pipeline_manager.build_pipeline_command(
                    internal_spec.pipeline_performance_specs,
                    internal_spec.execution_config,
                    job_id,
                )
            )

            # Build streams_per_pipeline using InternalPipelineStreamSpec
            streams_per_pipeline = [
                InternalPipelineStreamSpec(id=spec.pipeline_id, streams=spec.streams)
                for spec in internal_spec.pipeline_performance_specs
            ]

            # Update job with live_stream_urls and streams_per_pipeline immediately
            with self._jobs_lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]
                    job.streams_per_pipeline = streams_per_pipeline

                    # Type guard: ensure we have an InternalPerformanceJobStatus
                    if not isinstance(job, InternalPerformanceJobStatus):
                        self.logger.error(
                            f"Job {job_id} is not an InternalPerformanceJobStatus, skipping update"
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

            # Store runner for this job so it can be cancelled via stop_job()
            with self._jobs_lock:
                self.runners[job_id] = runner

            # Run the pipeline.
            # If exit_code != 0 and the run was not cancelled, PipelineRunner
            # raises RuntimeError which is handled in the except block below.
            result = runner.run(
                pipeline_command=pipeline_command,
                total_streams=total_streams,
            )

            # Collect actual video file lists from output directories after pipeline completes
            video_output_paths = collect_video_outputs_from_dirs(video_output_dirs)

            # Update job with results
            with self._jobs_lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]

                    if result.cancelled:
                        if result.exit_code != 0:
                            # Cancelled with non-zero exit code: mark as FAILED
                            self.logger.info(
                                f"Performance test {job_id} was cancelled with non-zero exit code ({result.exit_code}), marking as FAILED"
                            )
                            job.state = InternalTestJobState.FAILED
                            job.end_time = int(time.time() * 1000)
                            job.details = [
                                "Cancelled by user",
                                f"Pipeline exited with non-zero exit code: {result.exit_code}",
                            ]
                        else:
                            # Cancelled with zero exit code: mark as COMPLETED with results
                            self.logger.info(
                                f"Performance test {job_id} was cancelled with exit_code=0: "
                                f"total_fps={result.total_fps}, "
                                f"per_stream_fps={result.per_stream_fps}, "
                                f"num_streams={result.num_streams}, marking as COMPLETED"
                            )
                            job.state = InternalTestJobState.COMPLETED
                            job.end_time = int(time.time() * 1000)
                            job.details = ["Cancelled by user"]

                            # Save result data even when cancelled with exit code 0
                            job.total_fps = result.total_fps
                            job.per_stream_fps = result.per_stream_fps
                            job.total_streams = result.num_streams
                            job.video_output_paths = video_output_paths
                    else:
                        # Normal completion (exit_code is always 0 here because
                        # non-zero exit without cancellation raises RuntimeError
                        # in PipelineRunner)
                        self.logger.info(
                            f"Performance test {job_id} completed successfully: "
                            f"exit_code={result.exit_code}, "
                            f"total_fps={result.total_fps}, "
                            f"per_stream_fps={result.per_stream_fps}, "
                            f"total_streams={result.num_streams}"
                        )
                        job.state = InternalTestJobState.COMPLETED
                        job.end_time = int(time.time() * 1000)
                        job.details = ["Pipeline completed successfully"]

                        # Update performance metrics
                        job.total_fps = result.total_fps
                        job.per_stream_fps = result.per_stream_fps
                        job.total_streams = result.num_streams
                        job.video_output_paths = video_output_paths

                # Clean up runner after completion regardless of outcome
                self.runners.pop(job_id, None)

        except Exception as e:
            # Clean up runner on error
            with self._jobs_lock:
                self.runners.pop(job_id, None)
            self._update_job_failed(job_id, str(e))

    def _execute_density_test(
        self,
        job_id: str,
        internal_spec: InternalDensityTestSpec,
    ):
        """
        Execute the density test in a background thread.

        The method runs the benchmark using :class:`Benchmark` and then
        updates the corresponding :class:`InternalDensityJobStatus` accordingly.

        When a density job is cancelled, it is always marked as FAILED
        regardless of exit code, because partial benchmark results are
        not meaningful.

        After benchmark completes, output directory paths from the best result
        are scanned to collect the actual video file lists using
        collect_video_outputs_from_dirs().

        The details list is cleared when transitioning to a new state, then
        new entries for that state are appended.

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

            # Validate that no pipeline uses USB camera for density tests
            self._validate_no_usb_camera_for_density(
                internal_spec.pipeline_density_specs
            )

            # Initialize Benchmark
            benchmark = Benchmark(
                max_runtime=internal_spec.execution_config.max_runtime
            )

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

            # Collect actual video file lists from output directories after benchmark completes
            video_output_paths = collect_video_outputs_from_dirs(
                results.video_output_paths
            )

            # Update job with results
            with self._jobs_lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]

                    # Cancelled density tests are always FAILED
                    if benchmark.runner.is_cancelled():
                        self.logger.info(
                            f"Density test {job_id} was cancelled, marking as FAILED"
                        )
                        job.state = InternalTestJobState.FAILED
                        job.end_time = int(time.time() * 1000)
                        job.details = ["Cancelled by user"]
                    else:
                        # Normal completion
                        self.logger.info(
                            f"Density test {job_id} completed successfully: "
                            f"streams={results.n_streams}, "
                            f"streams_per_pipeline={results.streams_per_pipeline}, "
                            f"per_stream_fps={results.per_stream_fps}"
                        )
                        job.state = InternalTestJobState.COMPLETED
                        job.end_time = int(time.time() * 1000)
                        job.details = ["Density test completed successfully"]

                        job.total_fps = None
                        job.per_stream_fps = results.per_stream_fps
                        job.streams_per_pipeline = results.streams_per_pipeline
                        job.total_streams = results.n_streams
                        job.video_output_paths = video_output_paths

                # Clean up benchmark after completion regardless of outcome
                self.runners.pop(job_id, None)

        except Exception as e:
            # Clean up benchmark on error
            with self._jobs_lock:
                self.runners.pop(job_id, None)
            self._update_job_failed(job_id, str(e))

    def _update_job_failed(self, job_id: str, detail_message: str) -> None:
        """
        Mark the job as failed, clear the details list, and append the failure message.

        The details list is cleared when transitioning to FAILED state,
        then the new failure message is appended.

        Used for validation errors, unexpected exceptions, and cancellations
        with non-zero exit codes.
        """
        with self._jobs_lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.state = InternalTestJobState.FAILED
                job.end_time = int(time.time() * 1000)
                job.details = [detail_message]
        self.logger.error(f"Test job {job_id} failed: {detail_message}")

    def get_job_statuses_by_type(self, job_type: type[_T]) -> list[_T]:
        """
        Return internal job status objects for all jobs of a specific type.

        The ``job_type`` parameter should be either :class:`InternalPerformanceJobStatus`
        or :class:`InternalDensityJobStatus`. Access is protected by a lock to avoid
        reading partial updates.

        Returns internal types. Conversion to API types happens in the route layer.
        """
        with self._jobs_lock:
            statuses: list[_T] = []
            for job in self.jobs.values():
                if isinstance(job, job_type):
                    statuses.append(job)
            self.logger.debug(f"Current job statuses for type {job_type}: {statuses}")
            return statuses

    def get_job_status(
        self, job_id: str
    ) -> InternalPerformanceJobStatus | InternalDensityJobStatus | None:
        """
        Return the internal job status for a single job.

        ``None`` is returned when the job id is unknown.

        Returns internal types. Conversion to API types happens in the route layer.
        """
        with self._jobs_lock:
            if job_id not in self.jobs:
                return None
            job = self.jobs[job_id]
            self.logger.debug(f"Test job status for {job_id}: {job}")
            return job

    def get_job_summary(
        self, job_id: str
    ) -> InternalPerformanceJobSummary | InternalDensityJobSummary | None:
        """
        Return a short summary for a single job.

        The summary contains only the job id and the original test request.

        Returns internal types. Conversion to API types happens in the route layer.
        """
        with self._jobs_lock:
            if job_id not in self.jobs:
                return None

            job = self.jobs[job_id]

            if isinstance(job, InternalPerformanceJobStatus):
                job_summary = InternalPerformanceJobSummary(
                    id=job.id,
                    request=job.request,
                )
            else:  # InternalDensityJobStatus
                job_summary = InternalDensityJobSummary(
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

            if job.state != InternalTestJobState.RUNNING:
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
