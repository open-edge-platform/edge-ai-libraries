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

from helpers.config import BASE_URL, POLL_INTERVAL_SECONDS, POLL_TIMEOUT_SECONDS

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


def get_variant_simple_graph(
    session: requests.Session, pipeline_id: str, variant_id: str
) -> JsonDict:
    """Fetch the ``pipeline_graph_simple`` for the given pipeline variant."""
    response = session.get(f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30)
    response.raise_for_status()
    pipeline = response.json()
    for variant in pipeline.get("variants", []):
        if variant.get("id") == variant_id:
            simple_graph = variant.get("pipeline_graph_simple")
            assert simple_graph is not None, (
                f"Variant {variant_id} of pipeline {pipeline_id} has no pipeline_graph_simple"
            )
            return simple_graph
    pytest.fail(f"Variant {variant_id} not found in pipeline {pipeline_id}")


def convert_to_advanced(
    session: requests.Session,
    pipeline_id: str,
    variant_id: str,
    simple_graph: JsonDict,
) -> JsonDict:
    """POST the modified simple graph to convert-to-advanced and return the result."""
    url = (
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}/convert-to-advanced"
    )
    response = session.post(url, json=simple_graph, timeout=30)
    assert response.status_code == 200, (
        f"convert-to-advanced returned {response.status_code}: {response.text}"
    )
    advanced_graph = response.json()
    assert "nodes" in advanced_graph and "edges" in advanced_graph, (
        "convert-to-advanced response is missing 'nodes' or 'edges'"
    )
    logger.info(
        "Converted simple graph to advanced: %d node(s), %d edge(s)",
        len(advanced_graph.get("nodes", [])),
        len(advanced_graph.get("edges", [])),
    )
    return advanced_graph


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


def check_video_input_exists(session: requests.Session, filename: str) -> JsonDict:
    """Call ``GET /videos/check-video-input-exists?filename=...``.

    The endpoint always returns ``200``; the payload carries the ``exists``
    boolean. Tests use it to assert both the truthy and falsy branches.
    """
    response = session.get(
        f"{BASE_URL}/videos/check-video-input-exists",
        params={"filename": filename},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def upload_video(
    session: requests.Session,
    filename: str,
    payload: bytes,
    *,
    content_type: str = "video/mp4",
) -> requests.Response:
    """POST ``payload`` as a video file to ``/videos/upload``.

    Returns the raw ``requests.Response`` so callers can assert both the
    success path (201 + ``Video`` body) and any of the structured 422
    rejection bodies.
    """
    files = {"file": (filename, payload, content_type)}
    response = session.post(f"{BASE_URL}/videos/upload", files=files, timeout=120)
    logger.info(
        "POST /videos/upload filename=%s status=%d", filename, response.status_code
    )
    return response


def fetch_image_sets(session: requests.Session) -> list[JsonDict]:
    """Return the raw list of image sets from GET /images."""
    logger.info("Fetching image sets from %s/images", BASE_URL)
    response = session.get(f"{BASE_URL}/images", timeout=30)
    response.raise_for_status()
    payload = response.json()
    assert isinstance(payload, list), (
        f"Expected list response, got {type(payload).__name__}"
    )
    logger.info("Retrieved %d image sets", len(payload))
    return payload


def check_image_set_exists(session: requests.Session, name: str) -> JsonDict:
    """Call ``GET /images/check-image-set-exists?name=...``.

    Always returns 200; the payload contains an ``exists`` boolean.
    """
    response = session.get(
        f"{BASE_URL}/images/check-image-set-exists",
        params={"name": name},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def list_images_in_set(session: requests.Session, name: str) -> requests.Response:
    """Call ``GET /images/{name}``.

    Returns the raw response so callers can assert both 200 (with a list
    payload) and 404 (with a ``MessageResponse`` body).
    """
    response = session.get(f"{BASE_URL}/images/{name}", timeout=30)
    logger.info("GET /images/%s status=%d", name, response.status_code)
    return response


def upload_image_archive(
    session: requests.Session,
    filename: str,
    payload: bytes,
    *,
    content_type: str = "application/octet-stream",
) -> requests.Response:
    """POST ``payload`` as an image archive to ``/images/upload``.

    Returns the raw response so callers can assert both 201 success and
    the various structured 422 rejection bodies.
    """
    files = {"file": (filename, payload, content_type)}
    response = session.post(f"{BASE_URL}/images/upload", files=files, timeout=120)
    logger.info(
        "POST /images/upload filename=%s status=%d", filename, response.status_code
    )
    return response


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


def start_density_job(session: requests.Session, payload: JsonDict) -> str:
    """Submit a density test job and return the assigned job ID."""
    logger.info(
        "Starting density job \u2013 pipeline_id=%s variant_id=%s fps_floor=%d",
        payload["pipeline_density_specs"][0]["pipeline"]["pipeline_id"],
        payload["pipeline_density_specs"][0]["pipeline"]["variant_id"],
        payload["fps_floor"],
    )
    response = session.post(f"{BASE_URL}/tests/density", json=payload, timeout=30)
    response.raise_for_status()
    job_id: str = response.json().get("job_id", "")
    assert job_id, "Density test response missing 'job_id'"
    logger.info("Density job started: %s", job_id)
    return job_id


def start_optimization_job(
    session: requests.Session,
    pipeline_id: str,
    variant_id: str,
    payload: JsonDict,
) -> str:
    """Submit an optimization job and return the assigned job ID."""
    url = f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}/optimize"
    response = session.post(url, json=payload, timeout=30)
    response.raise_for_status()
    job_id: str = response.json().get("job_id", "")
    assert job_id, "Optimization response missing 'job_id'"
    logger.info("Optimization job started: %s", job_id)
    return job_id


def start_performance_job(session: requests.Session, payload: JsonDict) -> str:
    """Submit a performance test job and return the assigned ``job_id``."""
    response = session.post(f"{BASE_URL}/tests/performance", json=payload, timeout=30)
    response.raise_for_status()
    job_id: str = response.json().get("job_id", "")
    assert job_id, "Performance test response missing 'job_id'"
    logger.info("Performance job started: job_id=%s", job_id)
    return job_id


def stop_performance_job(session: requests.Session, job_id: str) -> None:
    """Send DELETE to stop a performance job.

    Accepts 200 (stopped) and 409 (already finished) as valid outcomes.
    """
    response = session.delete(f"{BASE_URL}/jobs/tests/performance/{job_id}", timeout=30)
    assert response.status_code in {200, 409}, (
        f"Expected 200 or 409 from stop endpoint, "
        f"got {response.status_code}: {response.text}"
    )
    logger.info(
        "Stop request for job_id=%s \u2192 %d: %s",
        job_id,
        response.status_code,
        response.json().get("message"),
    )


def poll_job_not_failed(
    session: requests.Session,
    status_url: str,
    duration_seconds: float,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> None:
    """Poll *status_url* for *duration_seconds* asserting the job never enters FAILED state.

    Also asserts the initial state is RUNNING before starting the timed monitoring.
    Exits early (without failure) if the job leaves RUNNING before the duration
    elapses, so that an unexpectedly fast COMPLETED job does not cause a spurious
    failure.
    """
    response = session.get(status_url, timeout=30)
    response.raise_for_status()
    initial = response.json()
    assert initial.get("state") == "RUNNING", (
        f"Expected initial job state RUNNING, got {initial.get('state')!r} "
        f"(error: {initial.get('error_message')!r})"
    )
    logger.info(
        "Job %s initial state=RUNNING \u2013 monitoring for %.1fs",
        status_url,
        duration_seconds,
    )

    deadline = time.monotonic() + duration_seconds
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        response = session.get(status_url, timeout=30)
        response.raise_for_status()
        last_status = response.json()
        state = last_status.get("state")
        logger.info(
            "Job state=%s elapsed=%s error=%s",
            state,
            last_status.get("elapsed_time"),
            last_status.get("error_message"),
        )
        assert state != "FAILED", (
            f"Performance job reached FAILED state after less than {duration_seconds}s: "
            f"error={last_status.get('error_message')!r}"
        )
        if state != "RUNNING":
            logger.warning(
                "Job at %s exited RUNNING state early with state=%s", status_url, state
            )
            break


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


# --------------------------------------------------------------------------- #
# Model management helpers (downloads, uploads, job polling).
# --------------------------------------------------------------------------- #


# OMZ downloads in CI can be slow; allow generous default.
MODEL_DOWNLOAD_TIMEOUT_SECONDS: float = 120.0


def start_model_download(
    session: requests.Session, names: list[str]
) -> requests.Response:
    """POST ``/models/download`` with the batch body ``{"names": [...]}``.

    Returns the raw response so callers can branch on the aggregate
    status code (202 / 207 / 400 / 404 / 409).
    """
    response = session.post(
        f"{BASE_URL}/models/download", json={"names": names}, timeout=60
    )
    logger.info("POST /models/download names=%s status=%d", names, response.status_code)
    return response


def fetch_model_jobs(session: requests.Session) -> list[JsonDict]:
    """Return the list from ``GET /jobs/models/status``."""
    response = session.get(f"{BASE_URL}/jobs/models/status", timeout=30)
    response.raise_for_status()
    payload = response.json()
    assert isinstance(payload, list), (
        f"Expected list response, got {type(payload).__name__}"
    )
    return payload


def get_model_job_summary(session: requests.Session, job_id: str) -> requests.Response:
    """Return the raw response of ``GET /jobs/models/{job_id}``."""
    response = session.get(f"{BASE_URL}/jobs/models/{job_id}", timeout=30)
    logger.info("GET /jobs/models/%s status=%d", job_id, response.status_code)
    return response


def get_model_job_status(session: requests.Session, job_id: str) -> requests.Response:
    """Return the raw response of ``GET /jobs/models/{job_id}/status``."""
    response = session.get(f"{BASE_URL}/jobs/models/{job_id}/status", timeout=30)
    logger.info("GET /jobs/models/%s/status status=%d", job_id, response.status_code)
    return response


def wait_for_model_download_completion(
    session: requests.Session,
    job_id: str,
    *,
    timeout: float = MODEL_DOWNLOAD_TIMEOUT_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> JsonDict:
    """Poll the model download job until it leaves ``RUNNING`` state.

    Returns the final status payload (``COMPLETED`` or ``FAILED``).
    Fails the test if the job is still ``RUNNING`` after ``timeout``.
    """
    deadline = time.monotonic() + timeout
    last_status: JsonDict = {}
    while time.monotonic() < deadline:
        response = get_model_job_status(session, job_id)
        if response.status_code == 404:
            pytest.fail(
                f"Model job {job_id} disappeared before reaching a terminal state"
            )
        response.raise_for_status()
        last_status = response.json()
        state = last_status.get("state")
        logger.info(
            "Model job %s state=%s elapsed=%s",
            job_id,
            state,
            last_status.get("elapsed_time"),
        )
        if state != "RUNNING":
            return last_status
        time.sleep(poll_interval)

    pytest.fail(
        f"Model job {job_id} did not finish within {timeout:.0f}s "
        f"(last state={last_status.get('state')!r})"
    )


def upload_model_file(
    session: requests.Session,
    model_name: str,
    category: str,
    payload: bytes,
    *,
    filename: str | None = None,
    content_type: str = "application/zip",
) -> requests.Response:
    """POST a multipart upload to ``/models/upload``.

    ``filename`` defaults to ``"<model_name>.zip"`` so the server has a
    stable basename to log/track. Returns the raw response so callers
    can assert both the 201 happy path and the 4xx/5xx error cases.
    """
    files = {"file": (filename or f"{model_name}.zip", payload, content_type)}
    data = {"model_name": model_name, "category": category}
    response = session.post(
        f"{BASE_URL}/models/upload", data=data, files=files, timeout=120
    )
    logger.info(
        "POST /models/upload model_name=%s category=%s status=%d",
        model_name,
        category,
        response.status_code,
    )
    return response


def find_model_in_list(
    models: list[JsonDict], name_or_display_name: str
) -> JsonDict | None:
    """Return the first model whose ``name`` or ``display_name`` matches."""
    for entry in models:
        if (
            entry.get("name") == name_or_display_name
            or entry.get("display_name") == name_or_display_name
        ):
            return entry
    return None
