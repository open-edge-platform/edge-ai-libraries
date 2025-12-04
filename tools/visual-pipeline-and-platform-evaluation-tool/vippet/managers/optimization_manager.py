import sys
import time
import uuid
import threading
import logging
from typing import Dict, Optional
from dataclasses import dataclass

from graph import Graph

from api.api_schemas import (
    Pipeline,
    PipelineRequestOptimize,
    OptimizationType,
    OptimizationJobStatus,
    OptimizationJobSummary,
    OptimizationJobState,
    PipelineGraph,
)

DEFAULT_SEARCH_DURATION = 300  # seconds
DEFAULT_SAMPLE_DURATION = 10  # seconds

logger = logging.getLogger("optimization_manager")

# Singleton instance for OptimizationManager
_optimization_manager_instance: Optional["OptimizationManager"] = None


def get_optimization_manager() -> "OptimizationManager":
    """
    Return the singleton instance of :class:`OptimizationManager`.

    The first call lazily creates the instance.  If initialization fails
    for any reason the error is logged and the process is terminated.
    """
    global _optimization_manager_instance
    if _optimization_manager_instance is None:
        try:
            _optimization_manager_instance = OptimizationManager()
        except Exception as e:
            logger.error(f"Failed to initialize OptimizationManager: {e}")
            sys.exit(1)
    return _optimization_manager_instance


@dataclass
class OptimizationJob:
    """
    Internal representation of a single optimization job.

    This mirrors what is exposed through :class:`OptimizationJobStatus`
    and :class:`OptimizationJobSummary`, with a few runtime-only fields.
    """

    id: str
    original_pipeline_graph: PipelineGraph
    original_pipeline_description: str
    request: PipelineRequestOptimize
    state: OptimizationJobState
    start_time: int
    end_time: Optional[int] = None
    optimized_pipeline_graph: Optional[PipelineGraph] = None
    optimized_pipeline_description: Optional[str] = None
    total_fps: Optional[float] = None
    error_message: Optional[str] = None


@dataclass
class PipelineOptimizationResult:
    """
    Lightweight result object returned by :class:`OptimizationRunner`.

    It is intentionally minimal: the manager is responsible for converting
    the optimized pipeline string back into :class:`PipelineGraph`.
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
        Run only the preprocessing stage on the provided pipeline.

        The external optimizer takes a list of element strings, so we split
        on ``!`` and then rejoin the processed list back into a single
        string for the caller.
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
        Run the full optimization process on the provided pipeline.

        The optimizer returns the optimized pipeline and a measured
        total FPS value.
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
    Manage optimization jobs for GStreamer pipelines.

    Responsibilities:

    * create and track :class:`OptimizationJob` instances,
    * run optimizations asynchronously in background threads,
    * expose job status and summaries in a thread-safe manner.
    """

    def __init__(self) -> None:
        # All known jobs keyed by job id
        self.jobs: Dict[str, OptimizationJob] = {}
        # Currently running OptimizationRunner instances keyed by job id
        self.runners: Dict[str, OptimizationRunner] = {}
        # Shared lock protecting access to ``jobs`` and ``runners``
        self.lock = threading.Lock()
        self.logger = logging.getLogger("OptimizationManager")

    @staticmethod
    def _generate_job_id() -> str:
        """
        Generate a unique job ID using UUID.
        """
        return uuid.uuid1().hex

    def run_optimization(
        self,
        pipeline: Pipeline,
        optimization_request: PipelineRequestOptimize,
    ) -> str:
        """
        Start an optimization job in the background and return its job id.

        The method:

        * converts the pipeline graph to a pipeline description string,
        * creates a new :class:`OptimizationJob` with RUNNING state,
        * spawns a background thread that executes the optimization.
        """
        job_id = self._generate_job_id()

        # Convert PipelineGraph to pipeline description string once and reuse.
        pipeline_description = Graph.from_dict(
            pipeline.pipeline_graph.model_dump()
        ).to_pipeline_description()

        # Create job record
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=pipeline.pipeline_graph,
            original_pipeline_description=pipeline_description,
            request=optimization_request,
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),  # milliseconds
        )

        with self.lock:
            self.jobs[job_id] = job

        # Start execution in background thread.  The thread itself will
        # update the job entry once finished or on error.
        thread = threading.Thread(
            target=self._execute_optimization,
            args=(job_id, pipeline_description, optimization_request),
            daemon=True,
        )
        thread.start()

        return job_id

    def _build_job_status(self, job: OptimizationJob) -> OptimizationJobStatus:
        """
        Build a :class:`OptimizationJobStatus` DTO from the internal job object.

        This method centralises the mapping to ensure consistency between
        status queries.
        """
        current_time = int(time.time() * 1000)
        elapsed_time = (
            job.end_time - job.start_time
            if job.end_time
            else current_time - job.start_time
        )
        return OptimizationJobStatus(
            id=job.id,
            type=job.request.type,
            start_time=job.start_time,
            elapsed_time=elapsed_time,
            state=job.state,
            total_fps=job.total_fps,
            original_pipeline_graph=job.original_pipeline_graph,
            optimized_pipeline_graph=job.optimized_pipeline_graph,
            original_pipeline_description=job.original_pipeline_description,
            optimized_pipeline_description=job.optimized_pipeline_description,
            error_message=job.error_message,
        )

    def get_all_job_statuses(self) -> list[OptimizationJobStatus]:
        """
        Return statuses for all known optimization jobs.

        Access is protected by a lock to avoid reading partial updates.
        """
        with self.lock:
            statuses = [self._build_job_status(job) for job in self.jobs.values()]
            self.logger.debug(f"Current pipeline optimization job statuses: {statuses}")
            return statuses

    def get_job_status(self, job_id: str) -> Optional[OptimizationJobStatus]:
        """
        Return the status for a single job.

        ``None`` is returned when the job id is unknown.
        """
        with self.lock:
            if job_id not in self.jobs:
                return None
            job = self.jobs[job_id]
            job_status = self._build_job_status(job)
            self.logger.debug(
                f"Pipeline optimization job status for {job_id}: {job_status}"
            )
            return job_status

    def get_job_summary(self, job_id: str) -> Optional[OptimizationJobSummary]:
        """
        Return a short summary for a single job.

        The summary intentionally contains only the job id and the original
        optimization request.
        """
        with self.lock:
            if job_id not in self.jobs:
                return None

            job = self.jobs[job_id]

            pipeline_job_summary = OptimizationJobSummary(
                id=job.id,
                request=job.request,
            )

            self.logger.debug(
                f"Pipeline optimization job summary for {job_id}: {pipeline_job_summary}"
            )

            return pipeline_job_summary

    def _update_job_error(self, job_id: str, error_message: str) -> None:
        """
        Mark the job as failed and persist the error message.

        Used both for validation errors and unexpected exceptions.
        """
        with self.lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.state = OptimizationJobState.ERROR
                job.end_time = int(time.time() * 1000)
                job.error_message = error_message
        self.logger.error(f"Pipeline optimization {job_id} error: {error_message}")

    def _execute_optimization(
        self,
        job_id: str,
        pipeline_description: str,
        optimization_request: PipelineRequestOptimize,
    ) -> None:
        """
        Execute the optimization process in a background thread.

        The method chooses between preprocessing or full optimization,
        delegates work to :class:`OptimizationRunner` and then updates
        the corresponding :class:`OptimizationJob` accordingly.
        """
        try:
            self.logger.info(
                f"Starting pipeline optimization execution for job {job_id}, original pipeline: {pipeline_description}"
            )

            # Initialize OptimizationRunner
            runner = OptimizationRunner()

            # Store runner for this job so that a future extension could cancel it.
            with self.lock:
                self.runners[job_id] = runner

            if optimization_request.type not in [
                OptimizationType.PREPROCESS,
                OptimizationType.OPTIMIZE,
            ]:
                # Unsupported type; this is considered a user error.
                raise ValueError(
                    f"Unknown optimization type: {optimization_request.type}"
                )

            # Run the pipeline
            if optimization_request.type == OptimizationType.PREPROCESS:
                results = runner.run_preprocessing(
                    pipeline_description=pipeline_description,
                )
            else:  # OptimizationType.OPTIMIZE
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
            with self.lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]

                    # Check if job was cancelled while running
                    if runner.is_cancelled():
                        self.logger.info(
                            f"Pipeline optimization {job_id} was cancelled, updating state to ABORTED"
                        )
                        job.state = OptimizationJobState.ABORTED
                        job.end_time = int(time.time() * 1000)
                        job.error_message = "Cancelled by user"
                    else:
                        # Normal completion
                        job.state = OptimizationJobState.COMPLETED
                        job.end_time = int(time.time() * 1000)

                        if results is not None:
                            # Persist numeric metrics and optimized pipeline string
                            job.total_fps = results.total_fps
                            job.optimized_pipeline_description = (
                                results.optimized_pipeline_description
                            )

                            # Build a new graph from the optimized pipeline description
                            graph = Graph.from_pipeline_description(
                                results.optimized_pipeline_description
                            )
                            job.optimized_pipeline_graph = PipelineGraph.model_validate(
                                graph.to_dict()
                            )

                        self.logger.info(
                            f"Pipeline optimization {job_id} completed successfully, optimized pipeline: {job.optimized_pipeline_description}"
                        )

                # Clean up runner after completion regardless of outcome
                self.runners.pop(job_id, None)

        except Exception as e:
            # Clean up runner on error
            with self.lock:
                self.runners.pop(job_id, None)
            self._update_job_error(job_id, str(e))
