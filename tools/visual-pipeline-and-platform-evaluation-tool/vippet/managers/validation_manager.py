import logging
import sys
import threading
import time
import uuid
from dataclasses import dataclass

from api.api_schemas import (
    PipelineValidation,
    ValidationJobStatus,
    ValidationJobSummary,
    ValidationJobState,
)
from graph import Graph
from pipeline_runner import PipelineRunner, PipelineValidationResult

logger = logging.getLogger("validation_manager")

# Singleton instance for ValidationManager
_validation_manager_instance: "ValidationManager | None" = None


def get_validation_manager() -> "ValidationManager":
    """
    Return the singleton instance of :class:`ValidationManager`.

    The first call lazily creates the instance.  If initialization fails
    for any reason the error is logged and the process is terminated.

    Keeping a dedicated accessor function allows tests to patch or
    replace the singleton if needed.
    """
    global _validation_manager_instance
    if _validation_manager_instance is None:
        try:
            _validation_manager_instance = ValidationManager()
        except Exception as e:  # pragma: no cover - defensive
            logger.error("Failed to initialize ValidationManager: %s", e)
            sys.exit(1)
    return _validation_manager_instance


@dataclass
class ValidationJob:
    """
    Internal representation of a single validation job.

    This mirrors what is exposed through :class:`ValidationJobStatus`
    and :class:`ValidationJobSummary`, with a few runtime-only fields.
    """

    id: str
    request: PipelineValidation
    # Converted GStreamer launch string used for the actual validation.
    # Keeping it here makes it visible in future summaries/debug logs.
    pipeline_description: str
    state: ValidationJobState
    start_time: int
    end_time: int | None = None
    is_valid: bool | None = None
    error_message: list[str] | None = None


class ValidationManager:
    """
    Manage validation jobs that use PipelineRunner to execute pipelines.

    Responsibilities:

    * create and track :class:`ValidationJob` instances,
    * run validations asynchronously in background threads,
    * use :class:`PipelineRunner` in validation mode to execute pipelines,
    * expose job status and summaries in a thread-safe manner.
    """

    def __init__(self) -> None:
        # All known jobs keyed by job id
        self.jobs: dict[str, ValidationJob] = {}
        # Shared lock protecting access to ``jobs``
        self.lock = threading.Lock()
        self.logger = logging.getLogger("ValidationManager")

    @staticmethod
    def _generate_job_id() -> str:
        """
        Generate a unique job ID using UUID.

        A dedicated helper makes it trivial to stub in tests.
        """
        return uuid.uuid1().hex

    def run_validation(self, validation_request: PipelineValidation) -> str:
        """
        Start a validation job in the background and return its job id.

        The method:

        * converts the pipeline graph to a pipeline description string,
        * extracts and validates runtime parameters (e.g. ``max-runtime``),
        * creates a new :class:`ValidationJob` with RUNNING state,
        * spawns a background thread that executes the pipeline via
          :class:`PipelineRunner` in validation mode.

        Raises
        ------
        ValueError
            If user-provided parameters are invalid (e.g. ``max-runtime``
            is less than 1).
        """
        # Convert PipelineGraph to a launch string
        pipeline_description = Graph.from_dict(
            validation_request.pipeline_graph.model_dump()
        ).to_pipeline_description()

        params = validation_request.parameters or {}
        max_runtime = params.get("max-runtime", 10)

        # Max runtime must be a positive integer for validation mode
        try:
            max_runtime = int(max_runtime)
        except (TypeError, ValueError):
            raise ValueError("Parameter 'max-runtime' must be an integer.")

        if max_runtime < 1:
            raise ValueError(
                "Parameter 'max-runtime' must be greater than or equal to 1."
            )

        # Hard timeout is max-runtime + 60 seconds
        hard_timeout = max_runtime + 60

        job_id = self._generate_job_id()
        job = ValidationJob(
            id=job_id,
            request=validation_request,
            state=ValidationJobState.RUNNING,
            start_time=int(time.time() * 1000),  # milliseconds
            pipeline_description=pipeline_description,
        )

        with self.lock:
            self.jobs[job_id] = job

        self.logger.info(
            "Validation started for job %s with max-runtime=%s, hard-timeout=%s",
            job_id,
            max_runtime,
            hard_timeout,
        )

        thread = threading.Thread(
            target=self._execute_validation,
            args=(job_id, pipeline_description, max_runtime, hard_timeout),
            daemon=True,
        )
        thread.start()

        return job_id

    def _execute_validation(
        self,
        job_id: str,
        pipeline_description: str,
        max_runtime: int,
        hard_timeout: int,
    ) -> None:
        """
        Execute the validation process in a background thread.

        The method uses :class:`PipelineRunner` in validation mode and updates
        the corresponding :class:`ValidationJob` accordingly.
        """
        try:
            # Create PipelineRunner in validation mode
            runner = PipelineRunner(
                mode="validation",
                max_runtime=max_runtime,
                hard_timeout=hard_timeout,
            )

            # Run pipeline validation
            result = runner.run(pipeline_description)

            # Type narrowing: PipelineRunner in validation mode returns PipelineValidationResult
            if not isinstance(result, PipelineValidationResult):
                self._update_job_error(
                    job_id,
                    "Unexpected result type from pipeline runner",
                )
                return

            with self.lock:
                job = self.jobs.get(job_id)
                if job is None:
                    # Job might have been pruned in a future extension;
                    # nothing more to do here.
                    return

                job.end_time = int(time.time() * 1000)
                job.is_valid = result.is_valid
                job.error_message = result.errors if result.errors else None

                if result.is_valid:
                    job.state = ValidationJobState.COMPLETED
                    self.logger.info(
                        "Validation job %s completed successfully (pipeline is valid)",
                        job_id,
                    )
                else:
                    job.state = ValidationJobState.ERROR
                    self.logger.error(
                        "Validation job %s failed with errors: %s",
                        job_id,
                        result.errors,
                    )

        except Exception as e:
            # Any unexpected exception is treated as an ERROR state
            self._update_job_error(job_id, str(e))

    def _update_job_error(self, job_id: str, error_message: str) -> None:
        """
        Mark the job as failed and persist the error message.

        Used for unexpected exceptions in the manager itself.
        """
        with self.lock:
            job = self.jobs.get(job_id)
            if job is not None:
                job.state = ValidationJobState.ERROR
                job.end_time = int(time.time() * 1000)
                if job.error_message is None:
                    job.error_message = [error_message]
                else:
                    job.error_message.append(error_message)
        self.logger.error("Validation job %s error: %s", job_id, error_message)

    def _build_job_status(self, job: ValidationJob) -> ValidationJobStatus:
        """
        Build a :class:`ValidationJobStatus` DTO from the internal job object.

        Centralising this mapping ensures consistency between status
        queries for single jobs and for the list-all endpoint.
        """
        current_time = int(time.time() * 1000)
        elapsed_time = (
            job.end_time - job.start_time
            if job.end_time is not None
            else current_time - job.start_time
        )
        return ValidationJobStatus(
            id=job.id,
            start_time=job.start_time,
            elapsed_time=elapsed_time,
            state=job.state,
            is_valid=job.is_valid,
            error_message=job.error_message,
        )

    def get_all_job_statuses(self) -> list[ValidationJobStatus]:
        """
        Return statuses for all known validation jobs.

        Access is protected by a lock to avoid reading partial updates.
        """
        with self.lock:
            statuses = [self._build_job_status(job) for job in self.jobs.values()]
            self.logger.debug(
                "Current validation job statuses: %s",
                statuses,
            )
            return statuses

    def get_job_status(self, job_id: str) -> ValidationJobStatus | None:
        """
        Return the status for a single validation job.

        ``None`` is returned when the job id is unknown.
        """
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            status = self._build_job_status(job)
            self.logger.debug("Validation job status for %s: %s", job_id, status)
            return status

    def get_job_summary(self, job_id: str) -> ValidationJobSummary | None:
        """
        Return a short summary for a single validation job.

        The summary intentionally contains only the job id and the
        original validation request.
        """
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None

            summary = ValidationJobSummary(
                id=job.id,
                request=job.request,
            )
            self.logger.debug("Validation job summary for %s: %s", job_id, summary)
            return summary
