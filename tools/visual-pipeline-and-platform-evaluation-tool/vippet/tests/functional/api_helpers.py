"""Shared API helper functions for VIPPET functional tests.

These helpers centralise common HTTP interactions so that individual test
modules do not duplicate fetch / polling logic.
"""

import logging
import time
from typing import Any

import pytest
import requests

from config import BASE_URL, POLL_INTERVAL_SECONDS, POLL_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

type JsonDict = dict[str, Any]


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


def fetch_pipeline_id(session: requests.Session, pipeline_name: str) -> str:
    """Return the ``id`` of the pipeline with the given name.

    Fetches GET /pipelines and asserts that exactly one pipeline with
    ``name == pipeline_name`` exists.
    """
    logger.info("Fetching pipeline id for '%s'", pipeline_name)
    pipelines = fetch_pipelines(session)

    matching = next((p for p in pipelines if p.get("name") == pipeline_name), None)
    assert matching is not None, (
        f"Pipeline named '{pipeline_name}' not found in /pipelines response"
    )
    pipeline_id = matching.get("id")
    assert pipeline_id, "Matching pipeline missing 'id' field"
    logger.info("Using pipeline id %s for '%s'", pipeline_id, pipeline_name)
    return str(pipeline_id)


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


def wait_for_job_completion(
    session: requests.Session,
    status_url: str,
    *,
    assert_initial_running: bool = True,
) -> JsonDict:
    """Poll *status_url* until the job reaches ``COMPLETED`` state.

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
        The final status payload once state == ``COMPLETED``.

    Raises
    ------
    pytest.fail
        If the job does not reach ``COMPLETED`` within
        ``POLL_TIMEOUT_SECONDS``.
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
        if state == "COMPLETED":
            logger.info("Job at %s finished with COMPLETED state", status_url)
            return last_status
        if state == "ERROR":
            pytest.fail(
                f"Job at {status_url} reached ERROR state: "
                f"{last_status.get('error_message')}"
            )
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
