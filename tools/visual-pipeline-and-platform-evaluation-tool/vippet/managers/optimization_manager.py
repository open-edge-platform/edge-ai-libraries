import logging
import threading
import time
import uuid
from dataclasses import dataclass

from dlsps2_optimizer import Dlsps2Optimizer, Dlsps2OptimizerCancelled
from graph import Graph
from internal_types import (
    InternalOptimizationJobStatus,
    InternalOptimizationJobState,
    InternalOptimizationJobSummary,
    InternalOptimizationType,
    InternalPipelineRequestOptimize,
    InternalVariant,
)
from managers.execution_coordinator import (
    ExecutionCoordinator,
    ExecutionLease,
    PIPELINE_EXECUTION_GROUP,
)

DEFAULT_SEARCH_DURATION = 300  # seconds
DEFAULT_SAMPLE_DURATION = 10  # seconds

# Variant names (case-insensitive) that map directly to a single OpenVINO
# device. When a variant has one of these names, the optimizer search scope
# is restricted to that device through the job's ``allowed_devices``.
# Any other variant name keeps the optimizer's default (all devices).
DEVICE_VARIANT_NAMES: frozenset[str] = frozenset({"CPU", "GPU", "NPU"})

# DLSPS 2.0 runs only the full optimizer search, not its preprocessing alone.
PREPROCESS_NOT_SUPPORTED = (
    "Optimization type 'preprocess' is not supported: pipelines run on DLSPS 2.0, "
    "which runs only the full optimization. Use type 'optimize', which applies "
    "the same preprocessing first."
)

logger = logging.getLogger("optimization_manager")


@dataclass
class PipelineOptimizationResult:
    """
    Lightweight result object returned by :class:`OptimizationRunner`.

    It is intentionally minimal: the manager is responsible for converting
    the optimized GStreamer pipeline string back into :class:`Graph`.

    Attributes:
        optimized_pipeline_description: Optimized GStreamer pipeline string produced by the optimizer.
        total_fps: Measured total FPS for the optimized pipeline.
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
    Thin wrapper around the DLSPS 2.0 optimizer client.

    The optimizer runs as a DLSPS 2.0 job (see :mod:`dlsps2_optimizer`), so
    candidate pipelines run on the server's runtime and devices. All calls to
    the client are isolated here so that the manager can be easily
    unit-tested by mocking this class.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger("OptimizationRunner")
        self._optimizer = Dlsps2Optimizer()

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

        Raises:
            Dlsps2OptimizerCancelled: :meth:`cancel` was called.
            Dlsps2OptimizerError: The DLSPS 2.0 job failed or could not run.
        """
        result = self._optimizer.optimize(
            pipeline_description,
            search_duration=search_duration,
            sample_duration=sample_duration,
            allowed_devices=allowed_devices,
        )
        return PipelineOptimizationResult(
            optimized_pipeline_description=result.pipeline, total_fps=result.fps
        )

    def cancel(self) -> None:
        """Cancel the current run."""
        self._optimizer.cancel()

    def is_cancelled(self) -> bool:
        """Return ``True`` if :meth:`cancel` was called."""
        return self._optimizer.is_cancelled()


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
        * validates the RTSP URLs of rtspsrc nodes,
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

        Raises:
            ValueError: If an rtspsrc node has a missing or invalid location.
            ValueError: The optimization type is not supported (``preprocess``).
            JobExecutionConflictError: Another pipeline execution job is running.
        """
        variant.pipeline_graph.validate_rtsp_sources()

        if optimization_request.type != InternalOptimizationType.OPTIMIZE:
            if optimization_request.type == InternalOptimizationType.PREPROCESS:
                raise ValueError(PREPROCESS_NOT_SUPPORTED)
            raise ValueError(f"Unknown optimization type: {optimization_request.type}")

        job_id = self._generate_job_id()
        execution_lease = ExecutionCoordinator().acquire(
            job_id=job_id,
            job_kind="optimization",
            groups=[PIPELINE_EXECUTION_GROUP],
        )

        try:
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

            # Registered with the job, so the job can be cancelled as soon as
            # it is visible.
            runner = OptimizationRunner()
            with self._jobs_lock:
                self.jobs[job_id] = job
                self.runners[job_id] = runner

            # Start execution in background thread. The variant name is passed
            # down so _execute_optimization can map it to an allowed device list
            # for the optimizer.
            thread = threading.Thread(
                target=self._execute_optimization,
                args=(
                    job_id,
                    runner,
                    pipeline_description,
                    optimization_request,
                    variant.name,
                    execution_lease,
                ),
                daemon=True,
            )
            thread.start()
        except Exception:
            with self._jobs_lock:
                self.jobs.pop(job_id, None)
                self.runners.pop(job_id, None)
            ExecutionCoordinator().release(execution_lease)
            raise

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

    def cancel_job(self, job_id: str) -> tuple[bool, str]:
        """
        Cancel a running optimization job.

        The runner cancels the DLSPS 2.0 job; the job then ends as FAILED
        with the "Cancelled by user" detail.

        Returns:
            tuple[bool, str]: Whether cancellation was requested, and a
                human-readable message. The message says "not found" for an
                unknown job and "not running" for a job that already ended.
        """
        with self._jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                msg = f"Optimization job {job_id} not found"
                self.logger.warning(msg)
                return False, msg

            runner = self.runners.get(job_id)
            if job.state != InternalOptimizationJobState.RUNNING or runner is None:
                msg = f"Optimization job {job_id} is not running (state: {job.state.value})"
                self.logger.warning(msg)
                return False, msg

            runner.cancel()
            msg = f"Optimization job {job_id} cancelled"
            self.logger.info(msg)
            return True, msg

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
        runner: OptimizationRunner,
        pipeline_description: str,
        optimization_request: InternalPipelineRequestOptimize,
        variant_name: str = "",
        execution_lease: ExecutionLease | None = None,
    ) -> None:
        """
        Execute the optimization process in a background thread.

        The optimizer runs as a DLSPS 2.0 job through ``runner``; this method
        blocks until it ends and then updates the corresponding
        :class:`InternalOptimizationJobStatus`.

        The variant name restricts the optimizer's device search scope:
        variant names equal (case-insensitive) to "CPU", "GPU" or "NPU" map
        to a single-device allowed list. Any other variant name keeps the
        optimizer's default search scope.

        After successful optimization, both advanced and simple views
        are generated from the optimized GStreamer pipeline string as
        internal Graph objects.

        A cancelled job (see :meth:`cancel_job`) is always marked as FAILED,
        because partial optimization results are not useful.

        The details list is cleared when transitioning to a new state, then
        new entries for that state are appended.

        Args:
            job_id: Unique identifier of the optimization job.
            runner: Runner registered for the job in ``self.runners``.
            pipeline_description: GStreamer pipeline string to optimize.
            optimization_request: Internal optimization parameters.
            variant_name: Name of the variant being optimized. Used to map
                to an allowed device list.
            execution_lease: Lease released when the job ends.

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
            # actually reach the optimizer.
            effective_search_duration = params.get(
                "search_duration", DEFAULT_SEARCH_DURATION
            )
            effective_sample_duration = params.get(
                "sample_duration", DEFAULT_SAMPLE_DURATION
            )
            self.logger.info(
                f"Starting DLSPS 2.0 optimizer for job {job_id} with "
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

            # Build both views outside the lock; a parse error fails the job.
            graph = Graph.from_pipeline_description(
                results.optimized_pipeline_description
            )
            graph_simple = graph.to_simple_view()

            with self._jobs_lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]
                    job.state = InternalOptimizationJobState.COMPLETED
                    job.end_time = int(time.time() * 1000)
                    job.details = ["Optimization completed successfully"]
                    job.total_fps = results.total_fps
                    job.optimized_pipeline_description = (
                        results.optimized_pipeline_description
                    )
                    job.optimized_pipeline_graph = graph
                    job.optimized_pipeline_graph_simple = graph_simple

            self.logger.info(
                f"Pipeline optimization {job_id} completed successfully, "
                f"optimized pipeline: {results.optimized_pipeline_description}"
            )

        except Dlsps2OptimizerCancelled:
            self.logger.info(
                f"Pipeline optimization {job_id} was cancelled, marking as FAILED"
            )
            self._update_job_error(job_id, "Cancelled by user")
        except Exception as e:
            self._update_job_error(job_id, str(e))
        finally:
            with self._jobs_lock:
                self.runners.pop(job_id, None)
            if execution_lease is not None:
                ExecutionCoordinator().release(execution_lease)
