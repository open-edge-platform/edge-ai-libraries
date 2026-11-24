# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""dlsps2_optimizer.py

``Dlsps2Optimizer`` runs the DL Streamer pipeline optimizer as a DLSPS 2.0
job, so candidate pipelines run on the server's runtime and devices, never in
vippet's process:

* ``POST /optimize`` starts the job; the server runs one at a time and
  answers 409 while another is active.
* ``GET /optimize/status/{id}`` is polled until the job is ``final``.
* ``GET /optimize/result/{id}`` returns the best pipeline found and its FPS.
* ``DELETE /optimize/{id}`` cancels the job.
* ``POST /optimize/preprocess`` applies only the optimizer's element
  substitutions to a launch string, synchronously and without a job.

The server keeps its jobs in memory only, so a job it no longer knows (404)
means the server restarted and the job is lost.
"""

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from dlsps2_runner import DLSPS2_BASE_URL, DLSPS2_HTTP_TIMEOUT_S, DLSPS2_VERIFY_TLS

logger = logging.getLogger("dlsps2_optimizer")

# Seconds between GET /optimize/status/{id} polls.
DLSPS2_OPTIMIZE_POLL_S: float = float(os.environ.get("DLSPS2_OPTIMIZE_POLL_S", "2"))

# Seconds a job may run beyond its search duration (and three sample
# durations) before it is cancelled as hung. Covers the baseline run and model
# compilation, which can take minutes on NPU.
DLSPS2_OPTIMIZE_SLACK_S: float = float(os.environ.get("DLSPS2_OPTIMIZE_SLACK_S", "300"))

# Seconds the server may stay unreachable, or answer with a server error (5xx),
# while a job is polled.
DLSPS2_OPTIMIZE_UNREACHABLE_S: float = float(
    os.environ.get("DLSPS2_OPTIMIZE_UNREACHABLE_S", "60")
)

# Seconds to keep retrying POST /optimize while the server answers 409. vippet
# is the server's only client and starts one optimization at a time, so a busy
# server is finishing a job cancelled when a previous vippet process ended (see
# cancel_leftover_optimizations): it frees the slot once that job's worker has
# exited, at most max(30, 3 * sample_duration) seconds after the cancel.
DLSPS2_OPTIMIZE_BUSY_WAIT_S: float = float(
    os.environ.get("DLSPS2_OPTIMIZE_BUSY_WAIT_S", "45")
)

# Per-request timeout of POST /optimize/preprocess, seconds. The server gives the
# preprocessing subprocess up to 30 s.
DLSPS2_PREPROCESS_TIMEOUT_S: float = float(
    os.environ.get("DLSPS2_PREPROCESS_TIMEOUT_S", "60")
)

# The server kills the optimizer worker max(30, 3 * sample_duration) seconds
# after a cancel; wait that long plus this margin for the job to end.
_CANCEL_GRACE_MIN_S = 30.0
_CANCEL_MARGIN_S = 15.0


class Dlsps2OptimizerError(RuntimeError):
    """The optimizer job could not be run or ended without a result."""


class Dlsps2OptimizerCancelled(Exception):
    """The optimizer job was cancelled through :meth:`Dlsps2Optimizer.cancel`."""


class _Dlsps2Unavailable(Dlsps2OptimizerError):
    """The server answered a status poll with a server error (5xx)."""


@dataclass
class Dlsps2OptimizeResult:
    """
    Outcome of a completed optimizer job.

    Attributes:
        pipeline: Best launch string found; the original one when no
            candidate beat it.
        fps: FPS measured for ``pipeline``, if the server reported it.
    """

    pipeline: str
    fps: float | None = None


def _response_detail(response: httpx.Response) -> str:
    """Describe an error response, preferring the server's FastAPI ``detail``."""
    try:
        body = response.json()
    except ValueError:
        body = None
    detail = body.get("detail") if isinstance(body, dict) else None
    return f"HTTP {response.status_code}: {detail or response.text}"


def _error_detail(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return _response_detail(exc.response)
    return str(exc)


class Dlsps2Optimizer:
    """Runs one optimizer job on DLSPS 2.0 and waits for its result.

    :meth:`optimize` blocks until the job ends; :meth:`cancel` may be called
    from another thread to stop it.
    """

    def __init__(
        self, base_url: Optional[str] = None, poll_interval: Optional[float] = None
    ) -> None:
        self.base_url = (base_url or DLSPS2_BASE_URL).rstrip("/")
        self.poll_interval = poll_interval or DLSPS2_OPTIMIZE_POLL_S
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        """Ask a running :meth:`optimize` to cancel its server job."""
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        """Return ``True`` once :meth:`cancel` was called."""
        return self._cancelled.is_set()

    def preprocess(self, pipeline: str) -> str:
        """
        Apply the optimizer's element substitutions to a launch string.

        Runs no candidate pipelines and takes no optimizer slot on the server.

        Args:
            pipeline: GStreamer launch string to preprocess.

        Returns:
            str: The preprocessed launch string.

        Raises:
            Dlsps2OptimizerError: The server is unreachable, has no
                preprocess endpoint, or could not preprocess the pipeline.
        """
        try:
            with httpx.Client(
                timeout=DLSPS2_PREPROCESS_TIMEOUT_S, verify=DLSPS2_VERIFY_TLS
            ) as client:
                response = client.post(
                    f"{self.base_url}/optimize/preprocess", json={"pipeline": pipeline}
                )
        except httpx.HTTPError as exc:
            raise Dlsps2OptimizerError(
                f"Cannot reach DLSPS 2.0 at {self.base_url}: {exc}"
            ) from exc
        if response.status_code in (404, 405):
            raise Dlsps2OptimizerError(
                f"DLSPS 2.0 at {self.base_url} has no preprocess endpoint "
                f"(POST /optimize/preprocess); it needs a server release with it"
            )
        if response.is_error:
            raise Dlsps2OptimizerError(
                f"DLSPS 2.0 could not preprocess the pipeline: "
                f"{_response_detail(response)}"
            )
        try:
            return str(response.json()["processed_pipeline"])
        except (ValueError, KeyError, TypeError) as exc:
            raise Dlsps2OptimizerError(
                f"Unexpected answer to POST /optimize/preprocess: {response.text}"
            ) from exc

    def optimize(
        self,
        pipeline: str,
        search_duration: float,
        sample_duration: float,
        allowed_devices: list[str] | None = None,
    ) -> Dlsps2OptimizeResult:
        """
        Optimize a launch string for FPS on DLSPS 2.0.

        Args:
            pipeline: GStreamer launch string to optimize.
            search_duration: Seconds the optimizer searches for a better pipeline.
            sample_duration: Seconds each candidate pipeline is sampled.
            allowed_devices: Devices the optimizer may use (e.g. ``["CPU"]``);
                ``None`` lets it use every device the server detects.

        Returns:
            Dlsps2OptimizeResult: The best pipeline and its FPS.

        Raises:
            Dlsps2OptimizerCancelled: :meth:`cancel` was called.
            Dlsps2OptimizerError: The job could not start, failed, was
                cancelled on the server, or took too long.
        """
        request: dict[str, Any] = {
            "pipeline": pipeline,
            "mode": "fps",
            "search_duration": search_duration,
            "sample_duration": sample_duration,
        }
        if allowed_devices is not None:
            request["allowed_devices"] = allowed_devices

        with httpx.Client(
            timeout=DLSPS2_HTTP_TIMEOUT_S, verify=DLSPS2_VERIFY_TLS
        ) as client:
            job_id = self._submit(client, request)
            logger.info(
                "DLSPS 2.0 optimizer job %s started (search_duration=%ss, "
                "sample_duration=%ss, allowed_devices=%s)",
                job_id,
                search_duration,
                sample_duration,
                allowed_devices,
            )
            try:
                deadline = (
                    time.monotonic()
                    + search_duration
                    + 3 * sample_duration
                    + DLSPS2_OPTIMIZE_SLACK_S
                )
                status = self._wait(client, job_id, deadline)
            except BaseException:
                # Whatever ends the wait, the server job must not outlive it, and
                # the caller keeps its lease until the server can take another job.
                self._cancel_job(client, job_id)
                self._wait_cancelled(client, job_id, sample_duration)
                raise
            if status is None:
                self._cancel_job(client, job_id)
                self._wait_cancelled(client, job_id, sample_duration)
                raise Dlsps2OptimizerCancelled(f"Optimizer job {job_id} cancelled")

            state = status.get("state")
            if state == "COMPLETED":
                return self._result(client, job_id)
            if state == "CANCELLED":
                raise Dlsps2OptimizerError(
                    f"Optimizer job {job_id} was cancelled on DLSPS 2.0"
                )
            raise Dlsps2OptimizerError(
                f"Optimizer job {job_id} failed on DLSPS 2.0: "
                f"{status.get('message') or state}"
            )

    def _submit(self, client: httpx.Client, request: dict[str, Any]) -> str:
        busy_deadline = time.monotonic() + DLSPS2_OPTIMIZE_BUSY_WAIT_S
        while True:
            try:
                response = client.post(f"{self.base_url}/optimize", json=request)
            except httpx.HTTPError as exc:
                raise Dlsps2OptimizerError(
                    f"Cannot reach DLSPS 2.0 at {self.base_url}: {exc}"
                ) from exc
            if response.status_code != 409 or time.monotonic() >= busy_deadline:
                break
            logger.info(
                "DLSPS 2.0 is still running another optimizer job, retrying: %s",
                _response_detail(response),
            )
            if self._cancelled.wait(self.poll_interval):
                raise Dlsps2OptimizerCancelled(
                    "Optimizer job cancelled before DLSPS 2.0 could start it"
                )
        if response.status_code in (404, 405):
            raise Dlsps2OptimizerError(
                f"DLSPS 2.0 at {self.base_url} has no optimizer endpoint "
                f"(POST /optimize); it needs a server release with the "
                f"pipeline optimizer"
            )
        if response.status_code == 409:
            raise Dlsps2OptimizerError(
                f"DLSPS 2.0 is already running another optimizer job "
                f"({_response_detail(response)})"
            )
        if response.is_error:
            raise Dlsps2OptimizerError(
                f"DLSPS 2.0 did not start the optimizer job: "
                f"{_response_detail(response)}"
            )
        try:
            return str(response.json()["job_id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise Dlsps2OptimizerError(
                f"Unexpected answer to POST /optimize: {response.text}"
            ) from exc

    def _wait(
        self, client: httpx.Client, job_id: str, deadline: float
    ) -> dict[str, Any] | None:
        """Poll until the job is final; ``None`` if :meth:`cancel` was called."""
        unreachable_since: float | None = None
        while True:
            if self._cancelled.is_set():
                return None
            try:
                status = self._status(client, job_id)
                unreachable_since = None
                if status.get("final"):
                    return status
            except (httpx.TransportError, _Dlsps2Unavailable) as exc:
                now = time.monotonic()
                unreachable_since = unreachable_since or now
                if now - unreachable_since > DLSPS2_OPTIMIZE_UNREACHABLE_S:
                    raise Dlsps2OptimizerError(
                        f"DLSPS 2.0 unreachable for more than "
                        f"{DLSPS2_OPTIMIZE_UNREACHABLE_S:.0f}s while running "
                        f"optimizer job {job_id}: {exc}"
                    ) from exc
            if time.monotonic() > deadline:
                raise Dlsps2OptimizerError(
                    f"Optimizer job {job_id} did not finish in time, cancelled"
                )
            self._cancelled.wait(self.poll_interval)

    def _status(self, client: httpx.Client, job_id: str) -> dict[str, Any]:
        response = client.get(f"{self.base_url}/optimize/status/{job_id}")
        if response.status_code == 404:
            raise Dlsps2OptimizerError(
                f"DLSPS 2.0 no longer knows optimizer job {job_id}; "
                f"the server may have restarted"
            )
        if response.is_server_error:
            raise _Dlsps2Unavailable(_response_detail(response))
        try:
            response.raise_for_status()
            status = response.json()
        except httpx.HTTPStatusError as exc:
            raise Dlsps2OptimizerError(
                f"Cannot read the status of optimizer job {job_id}: "
                f"{_error_detail(exc)}"
            ) from exc
        except ValueError as exc:
            raise Dlsps2OptimizerError(
                f"Cannot read the status of optimizer job {job_id}: {exc}"
            ) from exc
        if not isinstance(status, dict):
            raise Dlsps2OptimizerError(
                f"Unexpected status of optimizer job {job_id}: {status!r}"
            )
        return status

    def _result(self, client: httpx.Client, job_id: str) -> Dlsps2OptimizeResult:
        try:
            response = client.get(f"{self.base_url}/optimize/result/{job_id}")
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise Dlsps2OptimizerError(
                f"Cannot read the result of optimizer job {job_id}: "
                f"{_error_detail(exc) if isinstance(exc, httpx.HTTPError) else exc}"
            ) from exc
        # No better candidate leaves "best" empty; the baseline is then the answer.
        for key in ("best", "baseline"):
            entry = result.get(key) if isinstance(result, dict) else None
            if isinstance(entry, dict) and entry.get("pipeline"):
                return Dlsps2OptimizeResult(
                    pipeline=str(entry["pipeline"]), fps=entry.get("fps")
                )
        raise Dlsps2OptimizerError(
            f"Optimizer job {job_id} completed without a pipeline"
        )

    def _cancel_job(self, client: httpx.Client, job_id: str) -> None:
        """Best-effort DELETE /optimize/{id}. Never raises."""
        try:
            response = client.delete(f"{self.base_url}/optimize/{job_id}")
            # 409: the job already ended; 404: the server no longer knows it.
            if response.status_code not in (200, 404, 409):
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "Failed to cancel DLSPS 2.0 optimizer job %s: %s",
                job_id,
                _error_detail(exc),
            )

    def _wait_cancelled(
        self, client: httpx.Client, job_id: str, sample_duration: float
    ) -> None:
        """Wait until a cancelled job ends, so the server can take the next one.

        The server frees its only optimizer slot when the job's worker exits,
        which can take until the worker is killed, max(30, 3 * sample_duration)
        seconds after the cancel. Returns at once when the server is
        unreachable or no longer knows the job.
        """
        grace = max(_CANCEL_GRACE_MIN_S, 3 * sample_duration) + _CANCEL_MARGIN_S
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            try:
                if self._status(client, job_id).get("final"):
                    return
            except (httpx.HTTPError, Dlsps2OptimizerError):
                return
            time.sleep(self.poll_interval)
        logger.warning(
            "DLSPS 2.0 optimizer job %s still running %.0fs after cancel", job_id, grace
        )


def cancel_leftover_optimizations(base_url: Optional[str] = None) -> int:
    """Cancel every DLSPS 2.0 optimizer job that is still running. Never raises.

    ``vippet`` is the server's only client, so when ``vippet`` starts or stops
    no optimizer job should be running: one that is was started by a
    ``vippet`` process that ended mid-run. It would hold the server's only
    optimizer slot and load devices.

    Args:
        base_url: DLSPS 2.0 base URL, default ``DLSPS2_BASE_URL``.

    Returns:
        The number of jobs asked to cancel.
    """
    url = (base_url or DLSPS2_BASE_URL).rstrip("/")
    try:
        with httpx.Client(
            timeout=DLSPS2_HTTP_TIMEOUT_S, verify=DLSPS2_VERIFY_TLS
        ) as client:
            response = client.get(f"{url}/optimize/status")
            if response.status_code in (404, 405):
                logger.warning("DLSPS 2.0 at %s has no optimizer endpoint", url)
                return 0
            response.raise_for_status()
            running = [
                str(job["job_id"])
                for job in response.json()
                if job.get("state") == "RUNNING"
            ]
            if running:
                logger.warning(
                    "Cancelling %d DLSPS 2.0 optimizer job(s) that no run tracks: %s",
                    len(running),
                    running,
                )
            optimizer = Dlsps2Optimizer(base_url=url)
            for job_id in running:
                optimizer._cancel_job(client, job_id)
            return len(running)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        logger.warning("Could not cancel leftover DLSPS 2.0 optimizer jobs: %s", exc)
        return 0
