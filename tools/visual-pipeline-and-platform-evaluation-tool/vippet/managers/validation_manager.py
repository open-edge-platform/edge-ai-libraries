import logging
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from api.api_schemas import (
    PipelineValidation,
    ValidationJobStatus,
    ValidationJobSummary,
    ValidationJobState,
)
from graph import Graph

logger = logging.getLogger("validation_manager")

# Singleton instance for ValidationManager
_validation_manager_instance: Optional["ValidationManager"] = None


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
    end_time: Optional[int] = None
    is_valid: Optional[bool] = None
    error_message: Optional[List[str]] = None


class ValidatorRunner:
    """
    Thin wrapper around the external ``validator.py`` script.

    All direct subprocess interaction is encapsulated here to make the
    manager logic easier to unit-test (this class can be mocked).
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger("ValidatorRunner")

    def run(
        self,
        pipeline_description: str,
        max_runtime: int,
        hard_timeout: int,
    ) -> Tuple[bool, List[str]]:
        """
        Execute ``validator.py`` in a subprocess and return its outcome.

        Parameters
        ----------
        pipeline_description:
            GStreamer pipeline launch string to be validated. This is
            passed as the last CLI argument to ``validator.py`` so that
            the validator does not depend on stdin semantics.
        max_runtime:
            Soft execution limit in seconds, taken from the request
            parameters (or defaulted by the manager).
        hard_timeout:
            Hard upper bound in seconds; after this the subprocess is
            forcibly terminated regardless of state.

        Returns
        -------
        (is_valid, errors):
            * ``is_valid`` – ``True`` if the pipeline is considered valid,
              ``False`` otherwise.
            * ``errors`` – list of human-readable error strings produced
              by ``validator.py`` (possibly empty when valid).
        """
        # Build the command; the pipeline string is passed as the last argument.
        cmd = [
            sys.executable,
            "validator.py",
            "--max-runtime",
            str(max_runtime),
            pipeline_description,
        ]

        payload = {"pipeline_description": pipeline_description}
        self.logger.debug(
            "Starting validator subprocess with cmd=%s, payload=%s", cmd, payload
        )

        # Start subprocess with pipes for stdout/stderr so we can capture and parse all messages.
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            # Wait for completion up to the hard timeout.
            stdout, stderr = proc.communicate(timeout=hard_timeout)
        except subprocess.TimeoutExpired:
            # If the process exceeds the overall timeout, kill it and
            # attempt to read any remaining stderr for diagnostics.
            self.logger.warning(
                "validator.py timed out after %s seconds, killing process", hard_timeout
            )
            proc.kill()
            # collect as much information as possible
            stdout, stderr = proc.communicate()
            errors = self._parse_stderr(stderr)
            errors.append(
                "Pipeline validation timed out: validator.py did not finish "
                "within the allowed time and had to be terminated."
            )
            return False, errors

        self.logger.debug(
            "validator.py finished with returncode=%s, stdout=%r, stderr=%r",
            proc.returncode,
            stdout,
            stderr,
        )

        # Normal completion: inspect return code and stderr.
        errors = self._parse_stderr(stderr)

        # The pipeline is considered valid only if exit code is 0 and there
        # are no error messages.
        is_valid = proc.returncode == 0 and len(errors) == 0
        return is_valid, errors

    @staticmethod
    def _parse_stderr(raw_stderr: str) -> List[str]:
        """
        Parse raw stderr from ``validator.py`` into a list of clean messages.

        The implementation:

        * splits stderr into lines,
        * filters only lines starting with ``"validator - ERROR - "``,
        * strips that prefix from each selected line,
        * trims surrounding whitespace,
        * discards lines that are empty or contain only whitespace,
        * returns messages as a list of strings.
        """
        if not raw_stderr:
            return []

        messages: List[str] = []
        prefix = "validator - ERROR - "

        for line in raw_stderr.splitlines():
            # Only consider messages produced by validator's ERROR logger.
            if not line.startswith(prefix):
                continue

            # Remove prefix and trim whitespace.
            content = line[len(prefix) :].strip()
            if not content:
                # Skip messages that become empty / whitespace-only
                # after cutting the prefix.
                continue

            messages.append(content)

        return messages


class ValidationManager:
    """
    Manage validation jobs that call the external ``validator.py`` tool.

    Responsibilities:

    * create and track :class:`ValidationJob` instances,
    * run validations asynchronously in background threads,
    * spawn a separate subprocess for ``validator.py`` per job to guard
      against crashes such as segmentation faults,
    * expose job status and summaries in a thread-safe manner.
    """

    def __init__(self) -> None:
        # All known jobs keyed by job id
        self.jobs: Dict[str, ValidationJob] = {}
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
        * spawns a background thread that executes ``validator.py`` via
          :class:`ValidatorRunner`.

        Raises
        ------
        ValueError
            If user-provided parameters are invalid (e.g. ``max-runtime``
            is less than 1).
        """
        # Convert PipelineGraph to a launch string once and reuse it for
        # the lifetime of the job.  This mirrors the approach used in
        # :mod:`optimization_manager`.
        pipeline_description = Graph.from_dict(
            validation_request.pipeline_graph.model_dump()
        ).to_pipeline_description()

        params = validation_request.parameters or {}
        max_runtime = params.get("max-runtime", 10)

        # Max runtime must be a positive integer.
        try:
            max_runtime = int(max_runtime)
        except (TypeError, ValueError):
            raise ValueError("Parameter 'max-runtime' must be an integer.")

        if max_runtime < 1:
            raise ValueError(
                "Parameter 'max-runtime' must be greater than or equal to 1."
            )

        # Hard timeout is max-runtime + 60 seconds as specified.
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

        The method delegates the actual work to :class:`ValidatorRunner`
        and then updates the corresponding :class:`ValidationJob`
        accordingly.
        """
        runner = ValidatorRunner()
        try:
            is_valid, errors = runner.run(
                pipeline_description=pipeline_description,
                max_runtime=max_runtime,
                hard_timeout=hard_timeout,
            )

            with self.lock:
                job = self.jobs.get(job_id)
                if job is None:
                    # Job might have been pruned in a future extension;
                    # nothing more to do here.
                    return

                job.end_time = int(time.time() * 1000)
                job.is_valid = is_valid
                job.error_message = errors if errors else None

                if is_valid:
                    job.state = ValidationJobState.COMPLETED
                    self.logger.info(
                        "Validation job %s completed successfully (pipeline is valid)",
                        job_id,
                    )
                else:
                    job.state = ValidationJobState.ERROR
                    self.logger.error(
                        "Validation job %s failed with errors: %s", job_id, errors
                    )

        except Exception as e:
            # Any unexpected exception is treated as an ERROR state for the job.
            self._update_job_error(job_id, str(e))

    def _update_job_error(self, job_id: str, error_message: str) -> None:
        """
        Mark the job as failed and persist the error message.

        Used both for validation errors produced by ``validator.py`` and
        for unexpected exceptions in the manager itself.
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

    def get_all_job_statuses(self) -> List[ValidationJobStatus]:
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

    def get_job_status(self, job_id: str) -> Optional[ValidationJobStatus]:
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

    def get_job_summary(self, job_id: str) -> Optional[ValidationJobSummary]:
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
