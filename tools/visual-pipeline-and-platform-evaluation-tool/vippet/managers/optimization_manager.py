import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

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
    total_fps: Optional[float] = None

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
        self, pipeline_description: str, search_duration: int, sample_duration: int
    ) -> PipelineOptimizationResult:
        """
        Run the full optimization process on the provided GStreamer pipeline string.

        The optimizer searches for optimal pipeline configurations and returns
        the optimized GStreamer pipeline string along with measured FPS.

        Args:
            pipeline_description: Original GStreamer pipeline string to optimize.
            search_duration: Duration in seconds for the optimization search phase.
            sample_duration: Duration in seconds for measuring each configuration.

        Returns:
            PipelineOptimizationResult: Result containing the optimized GStreamer
                pipeline string and measured total FPS.
        """
        # Import from /opt/intel/dlstreamer/scripts/optimizer/optimizer.py provided in DLStreamer image
        # https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/dl-streamer/scripts/optimizer
        import optimizer  # pyright: ignore[reportMissingImports]

        optimized_pipeline, total_fps = optimizer.get_optimized_pipeline(
            pipeline_description, search_duration, sample_duration
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

    _instance: Optional["OptimizationManager"] = None
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
        self.jobs: Dict[str, InternalOptimizationJobStatus] = {}
        # Currently running OptimizationRunner instances keyed by job id
        self.runners: Dict[str, OptimizationRunner] = {}
        # Shared lock protecting access to ``jobs`` and ``runners``
        self._jobs_lock = threading.Lock()
        self.logger = logging.getLogger("OptimizationManager")

    @staticmethod
    def _generate_job_id() -> str:
        """
        Generate a unique job ID using UUID.
        """
        return uuid.uuid1().hex

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

        # Start execution in background thread
        thread = threading.Thread(
            target=self._execute_optimization,
            args=(job_id, pipeline_description, optimization_request),
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

    def get_job_status(self, job_id: str) -> Optional[InternalOptimizationJobStatus]:
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

    def get_job_summary(self, job_id: str) -> Optional[InternalOptimizationJobSummary]:
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
        Mark the job as failed and persist the error message.

        Used both for validation errors and unexpected exceptions.
        """
        with self._jobs_lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.state = InternalOptimizationJobState.ERROR
                job.end_time = int(time.time() * 1000)
                job.error_message = error_message
        self.logger.error(f"Pipeline optimization {job_id} error: {error_message}")

    def _execute_optimization(
        self,
        job_id: str,
        pipeline_description: str,
        optimization_request: InternalPipelineRequestOptimize,
    ) -> None:
        """
        Execute the optimization process in a background thread.

        The method chooses between preprocessing or full optimization,
        delegates work to :class:`OptimizationRunner` and then updates
        the corresponding :class:`InternalOptimizationJobStatus` accordingly.

        After successful optimization, both advanced and simple views
        are generated from the optimized GStreamer pipeline string as
        internal Graph objects.

        Args:
            job_id: Unique identifier of the optimization job.
            pipeline_description: GStreamer pipeline string to optimize.
            optimization_request: Internal optimization parameters and type.

        Returns:
            None (updates job status in place via self.jobs[job_id])

        Side effects:
            - Updates job state to COMPLETED, ERROR, or ABORTED
            - Stores optimized pipeline Graph objects (both views) on success
            - Stores optimized GStreamer pipeline string on success
            - Stores error_message on failure
            - Removes runner from self.runners when done
        """
        try:
            self.logger.info(
                f"Starting pipeline optimization execution for job {job_id}, original pipeline: {pipeline_description}"
            )

            # Initialize OptimizationRunner
            runner = OptimizationRunner()

            # Store runner for this job so that a future extension could cancel it.
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
                results = runner.run_optimization(
                    pipeline_description=pipeline_description,
                    search_duration=params.get(
                        "search_duration", DEFAULT_SEARCH_DURATION
                    ),
                    sample_duration=params.get(
                        "sample_duration", DEFAULT_SAMPLE_DURATION
                    ),
                )

            # Update job with results
            with self._jobs_lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]

                    # Check if job was cancelled while running
                    if runner.is_cancelled():
                        self.logger.info(
                            f"Pipeline optimization {job_id} was cancelled, updating state to ABORTED"
                        )
                        job.state = InternalOptimizationJobState.ABORTED
                        job.end_time = int(time.time() * 1000)
                        job.error_message = "Cancelled by user"
                    else:
                        # Normal completion
                        job.state = InternalOptimizationJobState.COMPLETED
                        job.end_time = int(time.time() * 1000)

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
