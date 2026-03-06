"""Shared API helper functions for VIPPET functional tests.

These helpers centralise common HTTP interactions so that individual test
modules do not duplicate fetch / polling logic.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

import pytest
import requests

from config import BASE_URL, POLL_INTERVAL_SECONDS, POLL_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

type JsonDict = dict[str, Any]
type JobAttemptFn = Callable[[], JsonDict]


def fetch_devices(session: requests.Session) -> list[JsonDict]:
    """Return the raw list of devices from GET /devices."""
    logger.info("Fetching devices from %s/devices", BASE_URL)
    response = session.get(f"{BASE_URL}/devices", timeout=30)
    response.raise_for_status()
    payload = response.json()
    assert isinstance(payload, list), (
        f"Expected list response, got {type(payload).__name__}"
    )
    logger.info("Retrieved %d devices", len(payload))
    return payload


def fetch_pipelines(session: requests.Session) -> list[JsonDict]:
    """Return the raw list of pipelines from GET /pipelines."""
    logger.info("Fetching pipelines from %s/pipelines", BASE_URL)
    response = session.get(f"{BASE_URL}/pipelines", timeout=30)
    response.raise_for_status()
    payload = response.json()
    assert isinstance(payload, list), (
        f"Expected list response, got {type(payload).__name__}"
    )
    logger.debug("Received %d pipelines", len(payload))
    return payload


def fetch_videos(session: requests.Session) -> list[JsonDict]:
    """Return the raw list of videos from GET /videos."""
    logger.info("Fetching videos from %s/videos", BASE_URL)
    response = session.get(f"{BASE_URL}/videos", timeout=30)
    response.raise_for_status()
    payload = response.json()
    assert isinstance(payload, list), (
        f"Expected list response, got {type(payload).__name__}"
    )
    logger.info("Retrieved %d videos", len(payload))
    return payload


def fetch_models(session: requests.Session) -> list[JsonDict]:
    """Return the raw list of models from GET /models."""
    logger.info("Fetching models from %s/models", BASE_URL)
    response = session.get(f"{BASE_URL}/models", timeout=30)
    response.raise_for_status()
    payload = response.json()
    assert isinstance(payload, list), (
        f"Expected list response, got {type(payload).__name__}"
    )
    logger.info("Retrieved %d models", len(payload))
    return payload


def fetch_cameras(session: requests.Session) -> list[JsonDict]:
    """Return the raw list of cameras from GET /cameras."""
    logger.info("Fetching cameras from %s/cameras", BASE_URL)
    response = session.get(f"{BASE_URL}/cameras", timeout=30)
    response.raise_for_status()
    payload = response.json()
    assert isinstance(payload, list), (
        f"Expected list response, got {type(payload).__name__}"
    )
    logger.info("Retrieved %d cameras", len(payload))
    return payload


def fetch_pipeline_templates(session: requests.Session) -> list[JsonDict]:
    """Return the raw list of pipeline templates from GET /pipeline-templates."""
    logger.info("Fetching pipeline templates from %s/pipeline-templates", BASE_URL)
    response = session.get(f"{BASE_URL}/pipeline-templates", timeout=30)
    response.raise_for_status()
    payload = response.json()
    assert isinstance(payload, list), (
        f"Expected list response, got {type(payload).__name__}"
    )
    logger.info("Retrieved %d pipeline templates", len(payload))
    return payload


def wait_for_job_completion(
    session: requests.Session,
    status_url: str,
    *,
    assert_initial_running: bool = True,
) -> JsonDict:
    """Poll *status_url* until the job leaves ``RUNNING`` state.

    Parameters
    ----------
    session:
        The HTTP session to use for polling requests.
    status_url:
        Full URL of the job status endpoint, e.g.
        ``http://localhost/api/v1/jobs/tests/density/{job_id}/status``.
    assert_initial_running:
        When ``True`` (default) the very first poll must return state
        ``RUNNING``; this matches the contract expected by density and
        performance job tests.

    Returns
    -------
    JsonDict
        The final status payload once ``state != "RUNNING"``.  The caller
        is responsible for checking the ``state`` field (e.g. via
        :func:`run_job_with_retry`).

    Raises
    ------
    pytest.fail
        If the job is still ``RUNNING`` after ``POLL_TIMEOUT_SECONDS``.
    """
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS

    response = session.get(status_url, timeout=30)
    response.raise_for_status()
    last_status: JsonDict = response.json()

    if assert_initial_running:
        assert last_status.get("state") == "RUNNING", (
            f"Expected initial job state RUNNING, got {last_status.get('state')}"
        )
    logger.info(
        "Job %s initial state=%s elapsed=%sms",
        status_url,
        last_status.get("state"),
        last_status.get("elapsed_time"),
    )

    while time.monotonic() < deadline:
        state = last_status.get("state")
        if state != "RUNNING":
            logger.info("Job at %s finished with state=%s", status_url, state)
            return last_status
        time.sleep(POLL_INTERVAL_SECONDS)
        response = session.get(status_url, timeout=30)
        response.raise_for_status()
        last_status = response.json()
        logger.info(
            "Job %s polled state=%s total_fps=%s error=%s",
            status_url,
            last_status.get("state"),
            last_status.get("total_fps"),
            last_status.get("error_message"),
        )

    pytest.fail(
        f"Job at {status_url} did not reach COMPLETED within {POLL_TIMEOUT_SECONDS} seconds"
    )


def run_job_with_retry(
    attempt_fn: JobAttemptFn,
    *,
    retry_delay_seconds: float = 5.0,
) -> JsonDict:
    """Run *attempt_fn* and, if the job does not reach ``COMPLETED``, retry once.

    Parameters
    ----------
    attempt_fn:
        A zero-argument callable that submits a job and waits for it to finish,
        returning the final status dict from :func:`wait_for_job_completion`.
    retry_delay_seconds:
        How long to wait between the first failure and the retry.

    Returns
    -------
    JsonDict
        The final status dict from the first attempt that reaches
        ``COMPLETED``, or the result of the second attempt (pass or fail).
    """
    status = attempt_fn()
    if status.get("state") != "COMPLETED":
        logger.warning(
            "First job attempt finished in state '%s' (error: %s) – retrying once after %.1fs",
            status.get("state"),
            status.get("error_message"),
            retry_delay_seconds,
        )
        time.sleep(retry_delay_seconds)
        status = attempt_fn()
    return status
