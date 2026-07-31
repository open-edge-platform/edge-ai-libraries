import json
import logging
import os
import threading
import time
import uuid
from typing import Any, TypeVar
import httpx
from graph import Graph

from internal_types import (
    InternalDensityJobStatus,
    InternalDensityJobSummary,
    InternalExecutionConfig,
    InternalLatencyMetrics,
    InternalMetadataMode,
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
from pipeline_runner import LatencyTracerSample, PipelineRunner
from benchmark import Benchmark
from managers.execution_coordinator import (
    ExecutionCoordinator,
    ExecutionLease,
    PIPELINE_EXECUTION_GROUP,
)
from managers.pipeline_manager import PipelineManager
from managers.metadata_manager import MetadataManager
from videos import collect_video_outputs_from_dirs
from utils import slugify_text

logger = logging.getLogger("tests_manager")

METRICS_MANAGER_URL: str = os.environ.get(
    "METRICS_MANAGER_URL", "http://metrics-manager:9090"
).rstrip("/")
METRICS_STREAM_PATH = "/metrics/stream"
METRICS_STREAM_MAX_EVENTS: int = int(
    os.environ.get("TESTS_METRICS_STREAM_MAX_EVENTS", "10000")
)


class _MetricsSSECollector:
    """Background SSE collector for `/metrics/stream` payloads."""

    def __init__(
        self,
        stream_url: str,
        logger_instance: logging.Logger,
        max_events: int = METRICS_STREAM_MAX_EVENTS,
    ) -> None:
        self._stream_url = stream_url
        self._logger = logger_instance
        self._max_events = max_events
        self._events: list[str] = []
        self._events_lock = threading.Lock()
        self._resources_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._client: httpx.Client | None = None
        self._response: httpx.Response | None = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        with self._resources_lock:
            if self._response is not None:
                self._response.close()
            if self._client is not None:
                self._client.close()

        self._thread.join(timeout=1.0)

    def snapshot(self) -> list[str]:
        with self._events_lock:
            return list(self._events)

    def _record_event(self, data_lines: list[str]) -> None:
        if not data_lines:
            return
        payload = "\n".join(data_lines)
        self._logger.info("Metrics SSE event received: %s", payload)
        with self._events_lock:
            self._events.append(payload)
            if len(self._events) > self._max_events:
                del self._events[0 : len(self._events) - self._max_events]

    def _run(self) -> None:
        timeout = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }

        try:
            with httpx.Client(timeout=timeout, headers=headers) as client:
                with self._resources_lock:
                    self._client = client

                with client.stream("GET", self._stream_url) as response:
                    response.raise_for_status()

                    with self._resources_lock:
                        self._response = response

                    data_lines: list[str] = []
                    for line in response.iter_lines():
                        if self._stop_event.is_set():
                            break

                        if line is None:
                            continue

                        if line == "":
                            self._record_event(data_lines)
                            data_lines = []
                            continue

                        if line.startswith(":"):
                            continue

                        field, separator, value = line.partition(":")
                        if not separator:
                            continue

                        if value.startswith(" "):
                            value = value[1:]

                        if field == "data":
                            data_lines.append(value)

                    self._record_event(data_lines)

        except Exception as exc:
            self._logger.warning(
                "Metrics SSE collector stopped for '%s': %s",
                self._stream_url,
                exc,
            )
        finally:
            with self._resources_lock:
                self._response = None
                self._client = None


def _map_latency_tracer_samples(
    samples: dict[str, LatencyTracerSample] | None,
) -> dict[str, InternalLatencyMetrics] | None:
    """
    Convert the runner-local ``LatencyTracerSample`` map into the
    internal job-status representation ``InternalLatencyMetrics``.

    Both types carry the same fields with the same semantics; the
    indirection exists only to keep ``pipeline_runner`` free of any
    dependency on ``internal_types`` (see the docstring on
    :class:`LatencyTracerSample` for the circular-import rationale).

    Preserves the ``None`` / empty-dict distinction:

    * ``None`` input — tracer was not enabled — returns ``None``.
    * ``{}`` input — tracer was enabled but produced no matching
      samples — returns ``{}``.
    """
    if samples is None:
        return None
    return {
        stream_id: InternalLatencyMetrics(
            interval_ms=sample.interval_ms,
            avg_ms=sample.avg_ms,
            min_ms=sample.min_ms,
            max_ms=sample.max_ms,
            latency_ms=sample.latency_ms,
        )
        for stream_id, sample in samples.items()
    }


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
        # Active metrics SSE collectors keyed by job id.
        self._metrics_collectors: dict[str, _MetricsSSECollector] = {}
        # Final metrics payload (JSON text) keyed by job id.
        self._metrics_json_text: dict[str, str] = {}
        # Shared lock protecting access to ``jobs`` and ``runners``
        self._jobs_lock = threading.Lock()
        self.logger = logging.getLogger("TestsManager")
        # Pipeline manager instance
        self.pipeline_manager = PipelineManager()

    def _start_metrics_stream_collection(self, job_id: str) -> None:
        if not METRICS_MANAGER_URL:
            return

        stream_url = f"{METRICS_MANAGER_URL}{METRICS_STREAM_PATH}"
        collector = _MetricsSSECollector(
            stream_url=stream_url,
            logger_instance=self.logger,
        )
        collector.start()

        with self._jobs_lock:
            self._metrics_collectors[job_id] = collector

    def _stop_metrics_stream_collection(self, job_id: str) -> None:
        with self._jobs_lock:
            collector = self._metrics_collectors.pop(job_id, None)

        if collector is None:
            return

        collector.stop()
        events = collector.snapshot()
        metrics_json_text = self._serialize_metrics_events(events)

        with self._jobs_lock:
            self._metrics_json_text[job_id] = metrics_json_text

    @staticmethod
    def _serialize_metrics_events(events: list[str]) -> str:
        parsed_events: list[dict[str, Any] | str] = []
        for payload in events:
            try:
                parsed_events.append(json.loads(payload))
            except Exception:
                parsed_events.append(payload)
        return json.dumps(parsed_events)

    def _get_metrics_json_text_for_job(self, job_id: str) -> str | None:
        with self._jobs_lock:
            metrics_json_text = self._metrics_json_text.get(job_id)
            collector = self._metrics_collectors.get(job_id)

        if metrics_json_text is not None:
            return metrics_json_text
        if collector is None:
            return None
        return self._serialize_metrics_events(collector.snapshot())

    @staticmethod
    def _generate_job_id() -> str:
        """
        Generate a unique job ID using UUID.
        """
        return uuid.uuid1().hex

    def test_performance(
        self,
        internal_spec: InternalPerformanceTestSpec,
        collect_metrics: bool = False,
        job_id: str | None = None,
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
        if job_id is None:
            job_id = self._generate_job_id()
        execution_lease = ExecutionCoordinator().acquire(
            job_id=job_id,
            job_kind="performance",
            groups=[PIPELINE_EXECUTION_GROUP],
        )

        try:
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
        if collect_metrics:
            thread_args = (job_id, internal_spec, execution_lease, True)
        else:
            # Keep the historical call signature for unit tests and
            # existing mocks when metrics collection is disabled.
            thread_args = (job_id, internal_spec, execution_lease)

        thread = threading.Thread(
            target=self._execute_performance_test,
            args=thread_args,
            daemon=True,
        )
        thread.start()
        except Exception:
            with self._jobs_lock:
                self.jobs.pop(job_id, None)
            ExecutionCoordinator().release(execution_lease)
            raise

        self.logger.info(f"Performance test started for job {job_id}")

        return job_id

    def test_performance_sync(
        self,
        internal_spec: InternalPerformanceTestSpec,
        collect_metrics: bool = False,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a performance test synchronously and return final result payload.

        This method is intended for orchestration flows that need to run
        multiple performance tests sequentially and consume each finished
        test result (for example: total_fps, metrics, job_id) before
        starting the next one.

        Cancellation is still supported: the running job is registered in
        ``self.jobs`` / ``self.runners`` and can be cancelled by calling
        :meth:`stop_job` from another thread or API request while this call
        is blocked.

        Args:
            internal_spec: Validated and converted internal test specification.

        Returns:
            dict: Final execution payload with keys:
                - job_id
                - state
                - total_fps
                - metrics
                - details
                - cancelled
        """
        if job_id is None:
            job_id = self._generate_job_id()

        job = InternalPerformanceJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            state=InternalTestJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )

        with self._jobs_lock:
            self.jobs[job_id] = job

        self.logger.info(f"Performance test started synchronously for job {job_id}")

        return self._execute_performance_test(
            job_id,
            internal_spec,
            collect_metrics,
        )

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
        execution_lease = ExecutionCoordinator().acquire(
            job_id=job_id,
            job_kind="density",
            groups=[PIPELINE_EXECUTION_GROUP],
        )

        try:
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
                args=(job_id, internal_spec, execution_lease),
                daemon=True,
            )
            thread.start()
        except Exception:
            with self._jobs_lock:
                self.jobs.pop(job_id, None)
            ExecutionCoordinator().release(execution_lease)
            raise

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

        if (
            is_density_test
            and execution_config.metadata_mode != InternalMetadataMode.DISABLED
        ):
            raise ValueError(
                "Density tests do not support metadata output. "
                "Set metadata_mode to 'disabled' for density tests."
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
        collect_metrics: bool = False,
        execution_lease: ExecutionLease | None = None,
    ) -> dict[str, Any]:
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
        if collect_metrics:
            self._start_metrics_stream_collection(job_id)

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
                return self._build_performance_execution_result(job_id)

            # Build pipeline command from specs.
            # `pipeline_cmd` carries the pipeline string plus all
            # side outputs (output dirs, live-stream URLs, metadata
            # files, per-pipeline stream identifiers). The
            # `streams_per_pipeline` map is used below to populate
            # `InternalPipelineStreamSpec.streams_ids` and to filter
            # latency_tracer samples to the streams we actually own.
            pipeline_cmd = self.pipeline_manager.build_pipeline_command(
                internal_spec.pipeline_performance_specs,
                internal_spec.execution_config,
                job_id,
            )
            pipeline_command = pipeline_cmd.command
            video_output_dirs = pipeline_cmd.video_output_paths
            live_stream_urls = pipeline_cmd.live_stream_urls
            metadata_file_paths = pipeline_cmd.metadata_file_paths
            streams_by_pipeline = pipeline_cmd.streams_per_pipeline

            # Set up metadata streaming if the pipeline produces metadata output files.
            metadata_stream_urls = None
            if metadata_file_paths:
                MetadataManager().register_job(job_id, metadata_file_paths)
                metadata_stream_urls = {
                    pipeline_id: [
                        f"/jobs/tests/performance/{job_id}/metadata/{slugify_text(pipeline_id)}/{i}/stream"
                        for i in range(len(paths))
                    ]
                    for pipeline_id, paths in metadata_file_paths.items()
                }

            # Build streams_per_pipeline using InternalPipelineStreamSpec.
            # `streams_ids` carries the stable, stream-unique identifiers
            # used to correlate latency_tracer rows back to individual
            # streams. The list order matches the order streams were
            # created by the pipeline runner.
            streams_per_pipeline = [
                InternalPipelineStreamSpec(
                    id=spec.pipeline_id,
                    streams=spec.streams,
                    streams_ids=[
                        info.stream_id
                        for info in streams_by_pipeline.get(spec.pipeline_id, [])
                    ],
                )
                for spec in internal_spec.pipeline_performance_specs
            ]

            # Update job with live_stream_urls, metadata_stream_urls and streams_per_pipeline immediately
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
                        job.metadata_stream_urls = metadata_stream_urls
                        self.logger.debug(
                            f"Updated job {job_id} with live_stream_urls: {live_stream_urls}, "
                            f"metadata_stream_urls: {metadata_stream_urls}"
                        )

            # Initialize PipelineRunner in normal mode with max_runtime from execution_config
            runner = PipelineRunner(
                mode="normal",
                max_runtime=internal_spec.execution_config.max_runtime,
                enable_latency_metrics=internal_spec.execution_config.enable_latency_metrics,
                job_id=job_id,
            )

            # Store runner for this job so it can be cancelled via stop_job()
            with self._jobs_lock:
                self.runners[job_id] = runner

            # Run the pipeline.
            # `allowed_stream_ids` scopes latency_tracer parsing to the
            # user-facing source/sink pairs we actually declared;
            # anything the tracer reports for internal bin sinks or
            # intermediate `splitmuxsink` elements is dropped.
            # If exit_code != 0 and the run was not cancelled, PipelineRunner
            # raises RuntimeError which is handled in the except block below.
            result = runner.run(
                pipeline_command=pipeline_command,
                total_streams=total_streams,
                allowed_stream_ids=set(pipeline_cmd.all_stream_ids),
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
                                f"Performance test {job_id} was cancelled with non-zero exit code ({result.exit_code}), "
                                f"marking as FAILED, details={result.details}"
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
                                f"num_streams={result.num_streams}, "
                                f"marking as COMPLETED, details={result.details}"
                            )
                            job.state = InternalTestJobState.COMPLETED
                            job.end_time = int(time.time() * 1000)
                            job.details = ["Cancelled by user"]

                            # Save result data even when cancelled with exit code 0
                            job.total_fps = result.total_fps
                            job.per_stream_fps = result.per_stream_fps
                            job.total_streams = result.num_streams
                            job.video_output_paths = video_output_paths
                            # Record the last observed latency_tracer
                            # sample per stream, or `None` if the tracer
                            # was not enabled for this run.
                            job.latency_tracer_metrics = _map_latency_tracer_samples(
                                result.latency_tracer_metrics
                            )
                    else:
                        # Normal completion (exit_code is always 0 here because
                        # non-zero exit without cancellation raises RuntimeError
                        # in PipelineRunner)
                        self.logger.info(
                            f"Performance test {job_id} completed successfully: "
                            f"exit_code={result.exit_code}, "
                            f"total_fps={result.total_fps}, "
                            f"per_stream_fps={result.per_stream_fps}, "
                            f"total_streams={result.num_streams}, "
                            f"details={result.details}"
                        )
                        job.state = InternalTestJobState.COMPLETED
                        job.end_time = int(time.time() * 1000)
                        job.details = ["Pipeline completed successfully"]

                        # Update performance metrics
                        job.total_fps = result.total_fps
                        job.per_stream_fps = result.per_stream_fps
                        job.total_streams = result.num_streams
                        job.video_output_paths = video_output_paths
                        # Record the last observed latency_tracer sample
                        # per stream, or `None` if the tracer was not
                        # enabled for this run.
                        job.latency_tracer_metrics = _map_latency_tracer_samples(
                            result.latency_tracer_metrics
                        )

                # Clean up runner after completion regardless of outcome
                self.runners.pop(job_id, None)

            # Stop tailing metadata files now that the pipeline has finished
            MetadataManager().stop_tailing(job_id)

            return self._build_performance_execution_result(job_id)

        except Exception as e:
            # Clean up runner on error
            with self._jobs_lock:
                self.runners.pop(job_id, None)
            MetadataManager().stop_tailing(job_id)
            self._update_job_failed(job_id, str(e))
            return self._build_performance_execution_result(job_id)
        finally:
            if collect_metrics:
                self._stop_metrics_stream_collection(job_id)
            if execution_lease is not None:
                            ExecutionCoordinator().release(execution_lease)

    def _build_performance_execution_result(self, job_id: str) -> dict[str, Any]:
        """Build final performance execution payload for orchestration callers."""
        with self._jobs_lock:
            job = self.jobs.get(job_id)

        if job is None or not isinstance(job, InternalPerformanceJobStatus):
            return {
                "job_id": job_id,
                "state": InternalTestJobState.FAILED,
                "total_fps": None,
                "metrics": None,
                "details": [f"Job {job_id} not found after execution."],
                "cancelled": False,
            }

        return {
            "job_id": job.id,
            "state": job.state,
            "total_fps": job.total_fps,
            "metrics": self._get_metrics_json_text_for_job(job_id),
            "details": list(job.details),
            "cancelled": any("cancel" in detail.lower() for detail in job.details),
        }

    def _execute_density_test(
        self,
        job_id: str,
        internal_spec: InternalDensityTestSpec,
        execution_lease: ExecutionLease | None = None,
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
                max_runtime=internal_spec.execution_config.max_runtime,
                enable_latency_metrics=internal_spec.execution_config.enable_latency_metrics,
                job_id=job_id,
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
                        # Record the latency_tracer samples captured on
                        # the benchmark's best-configuration run (the
                        # iteration whose ``n_streams`` / ``per_stream_fps``
                        # are reported above), NOT on the last iteration
                        # of the search. `None` when the tracer was not
                        # enabled for this job.
                        job.latency_tracer_metrics = _map_latency_tracer_samples(
                            results.latency_tracer_metrics
                        )

                # Clean up benchmark after completion regardless of outcome
                self.runners.pop(job_id, None)

        except Exception as e:
            # Clean up benchmark on error
            with self._jobs_lock:
                self.runners.pop(job_id, None)
            self._update_job_failed(job_id, str(e))
        finally:
            if execution_lease is not None:
                ExecutionCoordinator().release(execution_lease)

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

            job = self.jobs[job_id]

            if job.state != InternalTestJobState.RUNNING:
                msg = f"Job {job_id} is not running (state: {job.state})"
                self.logger.warning(msg)
                return False, msg

            runner = self.runners.get(job_id)
            if runner is None:
                msg = f"No active runner found for job {job_id}. It may have already completed or was never started."
                self.logger.warning(msg)
                return False, msg

            runner.cancel()
            msg = f"Job {job_id} stopped"
            self.logger.info(msg)
            return True, msg
