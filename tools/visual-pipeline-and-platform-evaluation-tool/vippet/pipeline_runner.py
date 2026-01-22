"""pipeline_runner.py

This module provides the PipelineRunner class for executing GStreamer pipelines
and extracting performance metrics (FPS).

The runner uses gst_runner.py to execute pipelines in either normal or validation
mode, providing unified interface for both production pipeline execution and
pipeline validation.
"""

import logging
import os
import re
import select
import subprocess
import sys
import time
import psutil as ps
from dataclasses import dataclass
from subprocess import PIPE, Popen


@dataclass
class PipelineRunResult:
    """Result of a pipeline run with FPS metrics."""

    total_fps: float
    per_stream_fps: float
    num_streams: int

    def __repr__(self):
        return (
            f"PipelineRunResult("
            f"total_fps={self.total_fps}, "
            f"per_stream_fps={self.per_stream_fps}, "
            f"num_streams={self.num_streams}"
            f")"
        )


@dataclass
class PipelineValidationResult:
    """Result of a pipeline validation run."""

    is_valid: bool
    errors: list[str]

    def __repr__(self):
        return (
            f"PipelineValidationResult(is_valid={self.is_valid}, errors={self.errors})"
        )


class PipelineRunner:
    """
    A class for running GStreamer pipelines in normal or validation mode.

    This class handles the execution of GStreamer pipeline commands using
    gst_runner.py and provides two operational modes:

    - normal mode: Runs pipelines for production use, extracting FPS metrics.
    - validation mode: Runs pipelines for a limited time to verify correctness.

    The runner manages the full lifecycle of gst_runner.py subprocess execution,
    including timeout enforcement, output parsing, and error handling.
    """

    # Default path to the FPS file
    DEFAULT_FPS_FILE_PATH = "/home/dlstreamer/vippet/.collector-signals/fps.txt"

    def __init__(
        self,
        mode: str = "normal",
        max_runtime: float = 0.0,
        poll_interval: int = 1,
        fps_file_path: str | None = None,
        inactivity_timeout: int = 120,
        hard_timeout: int | None = None,
    ):
        """
        Initialize the PipelineRunner.

        Args:
            mode: Execution mode - either "normal" or "validation".
                - normal: Run pipeline for production use (default).
                - validation: Run pipeline for limited time to verify correctness.
            max_runtime: Maximum time in seconds for pipeline execution.
                - For normal mode: 0 means run until EOS, >0 means stop after duration.
                - For validation mode: must be >0.
            poll_interval: Interval in seconds to poll the process for metrics
                (only used in normal mode).
            fps_file_path: Optional path to write latest FPS values for real-time
                monitoring (only used in normal mode).
            inactivity_timeout: Max seconds to wait without new stdout/stderr logs
                before treating the pipeline as hung and terminating it
                (only used in normal mode).
            hard_timeout: Absolute maximum time in seconds before forcibly killing
                the subprocess regardless of state (only used in validation mode).
                If None in validation mode, defaults to max_runtime + 60.
        """
        self.mode = mode
        self.max_runtime = max_runtime
        self.poll_interval = poll_interval
        self.fps_file_path = fps_file_path or self.DEFAULT_FPS_FILE_PATH
        self.inactivity_timeout = inactivity_timeout
        self.hard_timeout = hard_timeout
        self.logger = logging.getLogger("PipelineRunner")
        self.cancelled = False

        # Validate mode
        if self.mode not in ("normal", "validation"):
            raise ValueError(
                f"Invalid mode '{self.mode}'. Must be 'normal' or 'validation'."
            )

        # Validate max_runtime for validation mode
        if self.mode == "validation":
            if self.max_runtime <= 0:
                raise ValueError(
                    "Validation mode requires max_runtime > 0. "
                    "Received max_runtime={}.".format(self.max_runtime)
                )
            # Set default hard_timeout for validation if not provided
            if self.hard_timeout is None:
                self.hard_timeout = int(self.max_runtime + 60)

    def run(
        self, pipeline_command: str, total_streams: int = 1
    ) -> PipelineRunResult | PipelineValidationResult:
        """
        Run a GStreamer pipeline and return results based on mode.

        The pipeline is executed using gst_runner.py with the configured mode
        and max-runtime parameters.

        Args:
            pipeline_command: The complete GStreamer pipeline command string.
            total_streams: Total number of streams to expect in metrics
                (only used in normal mode for FPS extraction).

        Returns:
            - In normal mode: PipelineRunResult with FPS metrics.
            - In validation mode: PipelineValidationResult with validation status.

        Raises:
            RuntimeError: If pipeline execution fails in normal mode.
        """
        if self.mode == "validation":
            return self._run_validation(pipeline_command)
        else:
            return self._run_normal(pipeline_command, total_streams)

    def _run_validation(self, pipeline_command: str) -> PipelineValidationResult:
        """
        Run pipeline in validation mode.

        This method executes gst_runner.py with --mode validation and enforces
        the configured hard_timeout.

        Args:
            pipeline_command: GStreamer pipeline description string.

        Returns:
            PipelineValidationResult indicating whether the pipeline is valid
            and any error messages encountered.
        """
        cmd = [
            sys.executable,
            "gst_runner.py",
            "--mode",
            "validation",
            "--max-runtime",
            str(self.max_runtime),
            pipeline_command,
        ]

        self.logger.debug(
            "Starting validation subprocess with cmd=%s, pipeline=%s",
            cmd,
            pipeline_command,
        )

        # Start subprocess with pipes for stdout/stderr
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),
            text=True,
        )

        try:
            # Wait for completion up to the hard timeout
            stdout, stderr = proc.communicate(timeout=self.hard_timeout)
        except subprocess.TimeoutExpired:
            # If process exceeds hard timeout, kill it
            self.logger.warning(
                "gst_runner.py timed out after %s seconds, killing process",
                self.hard_timeout,
            )
            proc.kill()
            stdout, stderr = proc.communicate()
            errors = self._parse_validation_stderr(stderr)
            errors.append(
                "Pipeline validation timed out: gst_runner.py did not finish "
                "within the allowed time and had to be terminated."
            )
            return PipelineValidationResult(is_valid=False, errors=errors)

        self.logger.info(
            "gst_runner.py finished with return code=%s, stdout=\n%s\nstderr=\n%s\n",
            proc.returncode,
            stdout,
            stderr,
        )

        # Parse stderr for errors
        errors = self._parse_validation_stderr(stderr)

        # Pipeline is valid only if exit code is 0 and no errors found
        is_valid = proc.returncode == 0 and len(errors) == 0
        return PipelineValidationResult(is_valid=is_valid, errors=errors)

    def _parse_validation_stderr(self, raw_stderr: str) -> list[str]:
        """
        Parse raw stderr from gst_runner.py into a list of error messages.

        This method:
        - Splits stderr into lines
        - Filters only lines starting with "gst_runner - ERROR - "
        - Strips that prefix from each line
        - Trims surrounding whitespace
        - Discards empty lines

        Args:
            raw_stderr: Raw stderr output from gst_runner.py.

        Returns:
            List of error message strings.
        """
        if not raw_stderr:
            return []

        messages: list[str] = []
        prefix = "gst_runner - ERROR - "

        for line in raw_stderr.splitlines():
            if not line.startswith(prefix):
                continue

            content = line[len(prefix) :].strip()
            if not content:
                continue

            messages.append(content)

        return messages

    def _run_normal(
        self, pipeline_command: str, total_streams: int
    ) -> PipelineRunResult:
        """
        Run pipeline in normal mode and extract FPS metrics.

        This method executes gst_runner.py with --mode normal and monitors
        the output for FPS metrics from gvafpscounter.

        After pipeline completion (success or failure), writes 0.0 to the FPS
        file to indicate that the pipeline is no longer running.

        Args:
            pipeline_command: GStreamer pipeline description string.
            total_streams: Total number of streams to expect in metrics.

        Returns:
            PipelineRunResult containing total_fps, per_stream_fps, and num_streams.

        Raises:
            RuntimeError: If pipeline execution fails.
        """
        # Construct the command using gst_runner.py
        pipeline_cmd = [
            sys.executable,
            "gst_runner.py",
            "--mode",
            "normal",
            "--max-runtime",
            str(self.max_runtime),
            pipeline_command,
        ]

        self.logger.info(f"Pipeline Command: {' '.join(pipeline_cmd)}")

        try:
            # Spawn command in a subprocess
            process = Popen(
                pipeline_cmd, stdout=PIPE, stderr=PIPE, env=os.environ.copy()
            )

            exit_code = None
            total_fps = None
            per_stream_fps = None
            num_streams = None
            last_fps = None
            avg_fps_dict = {}
            process_output = []
            process_stderr = []

            # Define patterns to capture FPSCounter metrics
            overall_pattern = r"FpsCounter\(overall ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"
            avg_pattern = r"FpsCounter\(average ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"
            last_pattern = r"FpsCounter\(last ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"

            # Track last activity time for inactivity timeout
            last_activity_time = time.time()

            # Poll the process to check if it is still running
            while process.poll() is None:
                if self.cancelled:
                    process.terminate()
                    self.logger.info("Process cancelled, terminating")
                    break

                reads, _, _ = select.select(
                    [process.stdout, process.stderr], [], [], self.poll_interval
                )

                if reads:
                    # We saw some activity on stdout/stderr
                    last_activity_time = time.time()

                for r in reads:
                    line = r.readline()
                    if not line:
                        continue

                    if r == process.stdout:
                        process_output.append(line)

                        # Write the average FPS to file in real-time for monitoring
                        line_str = line.decode("utf-8")
                        match = re.search(avg_pattern, line_str)
                        if match:
                            result = {
                                "total_fps": float(match.group(2)),
                                "number_streams": int(match.group(3)),
                                "per_stream_fps": float(match.group(4)),
                            }
                            self.logger.info(
                                f"Avg FPS: {result['total_fps']} fps; "
                                f"Num Streams: {result['number_streams']}; "
                                f"Per Stream FPS: {result['per_stream_fps']} fps."
                            )

                            # Skip the result if the number of streams does not match
                            if result["number_streams"] != total_streams:
                                continue

                            latest_fps = result["per_stream_fps"]

                            # Write latest FPS to file
                            self._write_fps_to_file(latest_fps)

                    elif r == process.stderr:
                        process_stderr.append(line)

                    try:
                        if ps.Process(process.pid).status() == "zombie":
                            exit_code = process.wait()
                            break
                    except ps.NoSuchProcess:
                        # Process has already terminated
                        exit_code = process.wait()
                        break

                # If there was no activity for a prolonged period, treat as hang
                if (
                    not self.cancelled
                    and (time.time() - last_activity_time) > self.inactivity_timeout
                ):
                    self.logger.error(
                        "No new logs on stdout/stderr for %s seconds; "
                        "terminating pipeline as potentially hung",
                        self.inactivity_timeout,
                    )
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except Exception:
                        self.logger.warning(
                            "Process did not terminate gracefully after inactivity; killing it"
                        )
                        process.kill()
                        process.wait()

                    raise RuntimeError(
                        f"Pipeline execution terminated due to inactivity timeout "
                        f"({self.inactivity_timeout} seconds without stdout/stderr logs)."
                    )

            # Capture remaining output after process ends
            if exit_code is None:
                exit_code = process.wait()

            # Process output and extract FPS metrics
            for line in process_output:
                line_str = line.decode("utf-8")

                match = re.search(overall_pattern, line_str)
                if match:
                    result = {
                        "total_fps": float(match.group(2)),
                        "number_streams": int(match.group(3)),
                        "per_stream_fps": float(match.group(4)),
                    }
                    if result["number_streams"] == total_streams:
                        total_fps = result["total_fps"]
                        num_streams = result["number_streams"]
                        per_stream_fps = result["per_stream_fps"]
                        break

                match = re.search(avg_pattern, line_str)
                if match:
                    result = {
                        "total_fps": float(match.group(2)),
                        "number_streams": int(match.group(3)),
                        "per_stream_fps": float(match.group(4)),
                    }
                    avg_fps_dict[result["number_streams"]] = result

                match = re.search(last_pattern, line_str)
                if match:
                    result = {
                        "total_fps": float(match.group(2)),
                        "number_streams": int(match.group(3)),
                        "per_stream_fps": float(match.group(4)),
                    }
                    last_fps = result

            # Fallback to average FPS if overall not found
            if total_fps is None and avg_fps_dict.keys():
                if total_streams in avg_fps_dict.keys():
                    total_fps = avg_fps_dict[total_streams]["total_fps"]
                    num_streams = avg_fps_dict[total_streams]["number_streams"]
                    per_stream_fps = avg_fps_dict[total_streams]["per_stream_fps"]
                else:
                    # Find closest match
                    closest_match = min(
                        avg_fps_dict.keys(),
                        key=lambda x: abs(x - total_streams),
                        default=None,
                    )
                    if closest_match is not None:
                        total_fps = avg_fps_dict[closest_match]["total_fps"]
                        num_streams = avg_fps_dict[closest_match]["number_streams"]
                        per_stream_fps = avg_fps_dict[closest_match]["per_stream_fps"]

            # Fallback to last FPS if average not found
            if total_fps is None and last_fps:
                total_fps = last_fps["total_fps"]
                num_streams = last_fps["number_streams"]
                per_stream_fps = last_fps["per_stream_fps"]

            # Convert None to appropriate defaults
            if total_fps is None:
                total_fps = 0.0
            if num_streams is None:
                num_streams = 0
            if per_stream_fps is None:
                per_stream_fps = 0.0

            # Prepare output strings for error logging
            stdout_str = "".join(
                [line.decode("utf-8", errors="replace") for line in process_output]
            )
            stderr_str = "".join(
                [line.decode("utf-8", errors="replace") for line in process_stderr]
            )

            # Log errors if exit code is non-zero
            if exit_code != 0:
                self.logger.error("Pipeline failed with exit_code=%s", exit_code)
                self.logger.error("STDOUT:\n%s", stdout_str)
                self.logger.error("STDERR:\n%s", stderr_str)
                # Only raise an error if the failure was not due to cancellation
                if not self.is_cancelled():
                    raise RuntimeError(
                        f"Pipeline execution failed: {stderr_str.strip()}"
                    )

            self.logger.info("Exit code: {}".format(exit_code))
            self.logger.info("Total FPS is {}".format(total_fps))
            self.logger.info("Per Stream FPS is {}".format(per_stream_fps))
            self.logger.info("Num of Streams is {}".format(num_streams))

            return PipelineRunResult(
                total_fps=total_fps,
                per_stream_fps=per_stream_fps,
                num_streams=num_streams,
            )

        except Exception as e:
            self.logger.error(f"Pipeline execution error: {e}")
            raise
        finally:
            # Always write 0.0 to FPS file after pipeline completion (success or failure)
            self._write_fps_to_file(0.0)

    def _write_fps_to_file(self, fps: float) -> None:
        """
        Write the given FPS value to the FPS file.

        This method is called:
        - During pipeline execution to write current FPS metrics for monitoring
        - After pipeline completion (with 0.0) to signal that pipeline is no longer running

        Args:
            fps: FPS value to write to the file.
        """
        try:
            with open(self.fps_file_path, "w") as f:
                f.write(f"{fps}\n")
        except (OSError, IOError) as e:
            self.logger.warning(
                "Failed to write FPS to file %s: %s", self.fps_file_path, e
            )

    def cancel(self):
        """Cancel the currently running pipeline."""
        self.cancelled = True

    def is_cancelled(self) -> bool:
        """Check if the pipeline run has been cancelled."""
        return self.cancelled
