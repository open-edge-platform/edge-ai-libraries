import logging
import threading
import time
import uuid
from dataclasses import dataclass

from graph import Graph
from internal_types import (
    InternalOptimizationJobStatus,
    InternalOptimizationJobState,
    InternalOptimizationJobSummary,
    InternalOptimizationType,
    InternalPipelineRequestOptimize,
    InternalVariant,
)

DEFAULT_SEARCH_DURATION = 300  # seconds
DEFAULT_SAMPLE_DURATION = 10  # seconds

# Variant names (case-insensitive) that map directly to a single OpenVINO
# device. When a variant has one of these names, the optimizer search scope
# is restricted to that device via DLSOptimizer.set_allowed_devices().
# Any other variant name keeps the optimizer's default (all devices).
DEVICE_VARIANT_NAMES: frozenset[str] = frozenset({"CPU", "GPU", "NPU"})

logger = logging.getLogger("optimization_manager")


@dataclass
class PipelineOptimizationResult:
    """
    Lightweight result object returned by :class:`OptimizationRunner`.

    It is intentionally minimal: the manager is responsible for converting
    the optimized GStreamer pipeline string back into :class:`Graph`.

    Attributes:
        optimized_pipeline_description: Optimized GStreamer pipeline string produced by the optimizer.
        total_fps: Measured total FPS for the optimized pipeline (None for PREPROCESS type).
    """

    optimized_pipeline_description: str
    total_fps: float | None = None

    def __repr__(self) -> str:
        return (
            f"PipelineOptimizationResult("
            f"optimized_pipeline_description={self.optimized_pipeline_description}, "
            f"total_fps={self.total_fps}"
            f")"
        )


class OptimizationRunner:
    """
    Thin wrapper around the external optimizer module.

    All direct imports and calls into ``optimizer.py`` are isolated here
    so that the manager can be easily unit-tested by mocking this class.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger("OptimizationRunner")
        self.cancelled = False

    def run_preprocessing(
        self, pipeline_description: str
    ) -> PipelineOptimizationResult:
        """
        Run only the preprocessing stage on the provided GStreamer pipeline string.

        The external optimizer takes a GStreamer pipeline string, processes it,
        and returns the preprocessed pipeline string.

        Args:
            pipeline_description: Original GStreamer pipeline string to preprocess.

        Returns:
            PipelineOptimizationResult: Result containing the preprocessed GStreamer pipeline string.
        """
        # Import from /opt/intel/dlstreamer/scripts/optimizer/optimizer.py provided in DLStreamer image
        # https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/dl-streamer/scripts/optimizer
        import optimizer  # pyright: ignore[reportMissingImports]

        optimized_pipeline = optimizer.preprocess_pipeline(pipeline_description)
        return PipelineOptimizationResult(
            optimized_pipeline_description=optimized_pipeline
        )

    def run_optimization(
        self,
        pipeline_description: str,
        search_duration: int,
        sample_duration: int,
        allowed_devices: list[str] | None = None,
    ) -> PipelineOptimizationResult:
        """
        Run the full optimization process on the provided GStreamer pipeline string.

        The optimizer searches for optimal pipeline configurations and returns
        the optimized GStreamer pipeline string along with measured FPS.

        Args:
            pipeline_description: Original GStreamer pipeline string to optimize.
            search_duration: Duration in seconds for the optimization search phase.
            sample_duration: Duration in seconds for measuring each configuration.
            allowed_devices: Optional list of device strings (e.g. ["CPU"]) used to
                restrict the optimizer's device search scope. When None, the
                optimizer keeps its default scope (all detected devices).

        Returns:
            PipelineOptimizationResult: Result containing the optimized GStreamer
                pipeline string and measured total FPS.
        """
        # Import from /opt/intel/dlstreamer/scripts/optimizer/optimizer.py provided in DLStreamer image
        # https://github.com/open-edge-platform/dlstreamer/tree/main/scripts/optimizer/optimizer.py
        import optimizer  # pyright: ignore[reportMissingImports]

        opt = optimizer.DLSOptimizer()
        opt.set_sample_duration(sample_duration)

        # Restrict the device search scope only when an explicit list is
        # provided. Calling set_allowed_devices with None would override the
        # default behavior, which is undesirable.
        if allowed_devices is not None:
            opt.set_allowed_devices(allowed_devices)

        # Log the exact values that are about to be forwarded to
        # DLSOptimizer so the search time budget can be verified end-to-end
        # in the application log.
        self.logger.info(
            f"Calling DLSOptimizer.optimize_for_fps with "
            f"search_duration={search_duration}s, "
            f"sample_duration={sample_duration}s, "
            f"allowed_devices={allowed_devices}"
        )

        optimized_pipeline, total_fps = opt.optimize_for_fps(
            pipeline_description, search_duration=search_duration
        )

        return PipelineOptimizationResult(
            optimized_pipeline_description=optimized_pipeline, total_fps=total_fps
        )

    def cancel(self) -> None:
        """Mark the current run as cancelled."""
        self.cancelled = True

    def is_cancelled(self) -> bool:
        """Return ``True`` if :meth:`cancel` was called."""
        return self.cancelled


class OptimizationManager:
    """
    Thread-safe singleton that manages optimization jobs for pipeline variants.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with OptimizationManager() to get the shared singleton instance.

    Responsibilities:

    * create and track :class:`InternalOptimizationJobStatus` instances,
    * run optimizations asynchronously in background threads on specific variants,
    * expose job status and summaries in a thread-safe manner,
    * maintain both advanced and simple views of variant graphs throughout optimization,
    * convert between GStreamer pipeline strings and graph representations.
    """

    _instance: "OptimizationManager | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "OptimizationManager":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # All known jobs keyed by job id
        self.jobs: dict[str, InternalOptimizationJobStatus] = {}
        # Currently running OptimizationRunner instances keyed by job id
        self.runners: dict[str, OptimizationRunner] = {}
        # Shared lock protecting access to ``jobs`` and ``runners``
        self._jobs_lock = threading.Lock()
        self.logger = logging.getLogger("OptimizationManager")

    @staticmethod
    def _generate_job_id() -> str:
        """
        Generate a unique job ID using UUID.
        """
        return uuid.uuid1().hex

    @staticmethod
    def _resolve_allowed_devices(variant_name: str) -> list[str] | None:
        """
        Map a variant name to the optimizer's allowed device list.

        The match is case-insensitive. Only the names "CPU", "GPU" and "NPU"
        are recognized as device names. Any other variant name returns None,
        meaning the optimizer should keep its default device search scope
        (all detected devices).

        Args:
            variant_name: Name of the variant being optimized.

        Returns:
            A single-element list with the device string (e.g. ["CPU"]) when
            the variant name matches a known device, otherwise None.
        """
        if not variant_name:
            return None
        normalized = variant_name.strip().upper()
        if normalized in DEVICE_VARIANT_NAMES:
            return [normalized]
        return None

    def run_optimization(
        self,
        variant: InternalVariant,
        optimization_request: InternalPipelineRequestOptimize,
    ) -> str:
        """
        Start an optimization job in the background and return its job id.

        The method:

        * uses the variant's pipeline graphs (already as Graph objects),
        * converts the pipeline graph to a GStreamer pipeline string,
        * creates a new :class:`InternalOptimizationJobStatus` with RUNNING state,
        * spawns a background thread that executes the optimization.

        The variant name is also forwarded to the background worker so the
        optimizer can restrict its device search scope when the name matches
        a known device (CPU/GPU/NPU).

        Args:
            variant: InternalVariant with Graph objects to optimize.
            optimization_request: Internal optimization parameters (type and settings).

        Returns:
            str: Unique job identifier for tracking the optimization.
        """
        job_id = self._generate_job_id()

        # Get pipeline description from the variant's advanced graph
        pipeline_description = variant.pipeline_graph.to_pipeline_description()

        # Create job record with Graph objects from the variant
        job = InternalOptimizationJobStatus(
            id=job_id,
            original_pipeline_graph=variant.pipeline_graph,
            original_pipeline_graph_simple=variant.pipeline_graph_simple,
            original_pipeline_description=pipeline_description,
            request=optimization_request,
            state=InternalOptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),  # milliseconds
            type=optimization_request.type,
        )

        with self._jobs_lock:
            self.jobs[job_id] = job

        # Start execution in background thread. The variant name is passed
        # down so _execute_optimization can map it to an allowed device list
        # for the optimizer (only relevant for full OPTIMIZE jobs).
        thread = threading.Thread(
            target=self._execute_optimization,
            args=(job_id, pipeline_description, optimization_request, variant.name),
            daemon=True,
        )
        thread.start()

        return job_id

    def get_all_job_statuses(self) -> list[InternalOptimizationJobStatus]:
        """
        Return internal status objects for all known optimization jobs.

        Access is protected by a lock to avoid reading partial updates.
        The route layer is responsible for converting these to API DTOs.
        """
        with self._jobs_lock:
            statuses = list(self.jobs.values())
            self.logger.debug(f"Current pipeline optimization job statuses: {statuses}")
            return statuses

    def get_job_status(self, job_id: str) -> InternalOptimizationJobStatus | None:
        """
        Return the internal status for a single job.

        ``None`` is returned when the job id is unknown.
        The route layer is responsible for converting to API DTO.
        """
        with self._jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            self.logger.debug(f"Pipeline optimization job status for {job_id}: {job}")
            return job

    def get_job_summary(self, job_id: str) -> InternalOptimizationJobSummary | None:
        """
        Return a short internal summary for a single job.

        The summary contains only the job id and the original optimization
        request as internal types. The route layer converts to API DTO.
        """
        with self._jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None

            summary = InternalOptimizationJobSummary(
                id=job.id,
                request=job.request,
            )

            self.logger.debug(
                f"Pipeline optimization job summary for {job_id}: {summary}"
            )

            return summary

    def _update_job_error(self, job_id: str, error_message: str) -> None:
        """
        Mark the job as failed, clear the details list, and append the failure message.

        The details list is cleared when transitioning to FAILED state,
        then the new failure message is appended.

        Used both for validation errors and unexpected exceptions.
        """
        with self._jobs_lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.state = InternalOptimizationJobState.FAILED
                job.end_time = int(time.time() * 1000)
                job.details = [error_message]
        self.logger.error(f"Pipeline optimization {job_id} failed: {error_message}")

    def _execute_optimization(
        self,
        job_id: str,
        pipeline_description: str,
        optimization_request: InternalPipelineRequestOptimize,
        variant_name: str = "",
    ) -> None:
        """
        Execute the optimization process in a background thread.

        The method chooses between preprocessing or full optimization,
        delegates work to :class:`OptimizationRunner` and then updates
        the corresponding :class:`InternalOptimizationJobStatus` accordingly.

        For full OPTIMIZE jobs, the variant name is used to restrict the
        optimizer's device search scope: variant names equal (case-insensitive)
        to "CPU", "GPU" or "NPU" map to a single-device allowed list. Any
        other variant name keeps the optimizer's default search scope.
        The PREPROCESS type is not affected by this mapping.

        After successful optimization, both advanced and simple views
        are generated from the optimized GStreamer pipeline string as
        internal Graph objects.

        When a job is cancelled, it is always marked as FAILED regardless
        of exit code, because partial optimization results are not useful.
        There is no cancel endpoint yet, but the runner infrastructure is
        prepared to support it.

        The details list is cleared when transitioning to a new state, then
        new entries for that state are appended.

        Args:
            job_id: Unique identifier of the optimization job.
            pipeline_description: GStreamer pipeline string to optimize.
            optimization_request: Internal optimization parameters and type.
            variant_name: Name of the variant being optimized. Used to map
                to an allowed device list for the OPTIMIZE type.

        Returns:
            None (updates job status in place via self.jobs[job_id])

        Side effects:
            - Updates job state to COMPLETED or FAILED
            - Stores optimized pipeline Graph objects (both views) on success
            - Stores optimized GStreamer pipeline string on success
            - Stores details messages on completion or failure
            - Removes runner from self.runners when done
        """
        try:
            self.logger.info(
                f"Starting pipeline optimization execution for job {job_id}, original pipeline: {pipeline_description}"
            )

            # Initialize OptimizationRunner
            runner = OptimizationRunner()

            # Store runner for this job. There is no cancel endpoint yet,
            # but the infrastructure is prepared to support cancellation.
            with self._jobs_lock:
                self.runners[job_id] = runner

            if optimization_request.type not in [
                InternalOptimizationType.PREPROCESS,
                InternalOptimizationType.OPTIMIZE,
            ]:
                # Unsupported type; this is considered a user error.
                raise ValueError(
                    f"Unknown optimization type: {optimization_request.type}"
                )

            # Run the pipeline
            if optimization_request.type == InternalOptimizationType.PREPROCESS:
                results = runner.run_preprocessing(
                    pipeline_description=pipeline_description,
                )
            else:  # InternalOptimizationType.OPTIMIZE
                params = optimization_request.parameters or {}
                # Map the variant name to a device allow-list. Only "CPU",
                # "GPU" and "NPU" (case-insensitive) are recognized as
                # device names; other names keep the default search scope.
                allowed_devices = self._resolve_allowed_devices(variant_name)
                if allowed_devices is not None:
                    self.logger.info(
                        f"Restricting optimizer device search to {allowed_devices} "
                        f"for job {job_id} (variant name: {variant_name!r})"
                    )
                # Resolve effective values once so they can be both logged
                # and forwarded to the runner. This makes it easy to verify
                # in the logs that the values from the request (or defaults)
                # actually reach DLSOptimizer.
                effective_search_duration = params.get(
                    "search_duration", DEFAULT_SEARCH_DURATION
                )
                effective_sample_duration = params.get(
                    "sample_duration", DEFAULT_SAMPLE_DURATION
                )
                self.logger.info(
                    f"Starting DLSOptimizer for job {job_id} with "
                    f"search_duration={effective_search_duration}s, "
                    f"sample_duration={effective_sample_duration}s, "
                    f"allowed_devices={allowed_devices} "
                    f"(raw parameters={params!r})"
                )
                results = runner.run_optimization(
                    pipeline_description=pipeline_description,
                    search_duration=effective_search_duration,
                    sample_duration=effective_sample_duration,
                    allowed_devices=allowed_devices,
                )

            # Update job with results
            with self._jobs_lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]

                    # Cancelled optimization jobs are always FAILED because
                    # partial optimization results are not useful
                    if runner.is_cancelled():
                        self.logger.info(
                            f"Pipeline optimization {job_id} was cancelled, marking as FAILED"
                        )
                        job.state = InternalOptimizationJobState.FAILED
                        job.end_time = int(time.time() * 1000)
                        job.details = ["Cancelled by user"]
                    else:
                        # Normal completion
                        job.state = InternalOptimizationJobState.COMPLETED
                        job.end_time = int(time.time() * 1000)
                        job.details = ["Optimization completed successfully"]

                        if results is not None:
                            # Persist numeric metrics and optimized pipeline string
                            job.total_fps = results.total_fps
                            job.optimized_pipeline_description = (
                                results.optimized_pipeline_description
                            )

                            # Build advanced Graph from the optimized pipeline description
                            graph = Graph.from_pipeline_description(
                                results.optimized_pipeline_description
                            )
                            job.optimized_pipeline_graph = graph

                            # Generate simple view Graph from the optimized advanced graph
                            job.optimized_pipeline_graph_simple = graph.to_simple_view()

                        self.logger.info(
                            f"Pipeline optimization {job_id} completed successfully, optimized pipeline: {job.optimized_pipeline_description}"
                        )

                # Clean up runner after completion regardless of outcome
                self.runners.pop(job_id, None)

        except Exception as e:
            # Clean up runner on error
            with self._jobs_lock:
                self.runners.pop(job_id, None)
            self._update_job_error(job_id, str(e))
