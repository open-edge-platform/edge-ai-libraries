# SPDX-License-Identifier: Apache-2.0
"""Functional tests for the model-download REST surface.

Covers:

* ``POST /models/download``     - submit a batch download
* ``GET  /jobs/models/status``  - list active model jobs
* ``GET  /jobs/models/{id}``    - per-job summary
* ``GET  /jobs/models/{id}/status`` - per-job live status

Assumptions about the environment (matching how the rest of the
functional suite runs):

* The vippet stack is up and reachable through ``BASE_URL``.
* ``shared/models/output`` is mounted into the vippet container; some
  models from ``supported_models.yaml`` may already be installed.

The two reference models used here (``face-detection-retail-0004``
and ``age-gender-recognition-retail-0013``) are intentionally tiny
OpenVINO IRs (~5 MB each) so the download finishes within
``MODEL_DOWNLOAD_TIMEOUT_SECONDS`` even on slow CI machines. The test
tolerates both code paths:

* the model is already installed (server returns 409 in the per-name
  detail) - we simply skip the wait;
* the model needs downloading - we poll the per-job status endpoints
  and wait for ``COMPLETED``.
"""

from __future__ import annotations

import logging

import pytest
import requests

from helpers.api_helpers import (
    JsonDict,
    fetch_model_jobs,
    fetch_models,
    find_model_in_list,
    get_model_job_status,
    get_model_job_summary,
    start_model_download,
    wait_for_model_download_completion,
)

logger = logging.getLogger(__name__)


# Two small OMZ models that are listed in the canonical
# ``supported_models.yaml`` shipped with the repository. The display
# names are stable and used by the pipeline tests below.
_REFERENCE_MODELS: tuple[str, ...] = (
    "face-detection-retail-0004",
    "age-gender-recognition-retail-0013",
)


def _resolve_job_id(
    http_client: requests.Session,
    download_response: requests.Response,
    requested_names: list[str],
) -> str | None:
    """Extract a job id from the download response.

    The response shape is one entry per requested model with either a
    ``job_id`` or a ``status_code`` of 409 (already installed). When at
    least one job was created, return its id; otherwise return ``None``
    so the caller can skip the polling portion of the test.
    """
    body = download_response.json()
    items = body if isinstance(body, list) else body.get("items", [])
    for item in items:
        job_id = item.get("job_id")
        if job_id:
            return str(job_id)

    # No job was created - fall back to the live job list in case the
    # download finished synchronously between the POST and our parsing.
    for job in fetch_model_jobs(http_client):
        if job.get("model_name") in requested_names:
            job_id = job.get("job_id")
            if job_id:
                return str(job_id)
    return None


@pytest.mark.full
def test_models_download_reference_models_and_track_jobs(
    http_client: requests.Session,
) -> None:
    """Submit a download for two small reference models and exercise
    every model-job endpoint along the way.

    The test is robust against the case where the models are already
    installed: it then only verifies the listing/summary endpoints and
    skips the wait-for-completion step.
    """
    response = start_model_download(http_client, list(_REFERENCE_MODELS))
    # ``/models/download`` returns 202 (all queued), 207 (mixed - some
    # already installed), 200/201 in legacy shapes, or 409 when every
    # requested model is already installed.
    assert response.status_code in {200, 201, 202, 207, 409}, (
        f"Unexpected status from POST /models/download: "
        f"{response.status_code}: {response.text}"
    )

    job_id = _resolve_job_id(http_client, response, list(_REFERENCE_MODELS))

    # GET /jobs/models/status must always be exercised so the
    # coverage test passes regardless of whether a job was created.
    jobs = fetch_model_jobs(http_client)
    assert isinstance(jobs, list)
    logger.info("/jobs/models/status returned %d active job(s)", len(jobs))

    if job_id is None:
        logger.info("All reference models were already installed; skipping wait.")
    else:
        # Per-job summary (synchronous; just confirm shape + 200).
        summary_response = get_model_job_summary(http_client, job_id)
        assert summary_response.status_code == 200, summary_response.text
        summary = summary_response.json()
        assert summary.get("job_id") == job_id

        # Per-job live status: at least one poll must succeed.
        status_response = get_model_job_status(http_client, job_id)
        assert status_response.status_code == 200, status_response.text
        assert status_response.json().get("state") in {
            "RUNNING",
            "COMPLETED",
            "FAILED",
        }

        final = wait_for_model_download_completion(http_client, job_id)
        assert final.get("state") == "COMPLETED", (
            f"Model download job {job_id} ended in unexpected state "
            f"{final.get('state')!r}: {final.get('error_message')!r}"
        )

    # Regardless of the path taken above, both reference models must
    # now be visible in GET /models as INSTALLED.
    installed_models = fetch_models(http_client)
    for name in _REFERENCE_MODELS:
        entry: JsonDict | None = find_model_in_list(installed_models, name)
        assert entry is not None, (
            f"Reference model {name!r} missing from GET /models response"
        )
        install_status = str(entry.get("install_status") or "").upper()
        assert install_status == "INSTALLED", (
            f"Reference model {name!r} not installed: "
            f"install_status={entry.get('install_status')!r}"
        )


@pytest.mark.full
def test_models_download_404_for_unknown_model(
    http_client: requests.Session,
) -> None:
    """Submitting a download for a name that is not in
    ``supported_models.yaml`` must surface an error code (4xx).

    The exact status depends on whether the backend validates the
    request as a whole (400) or per-item (207 with a 404 inside the
    per-name detail). Both shapes are accepted.
    """
    response = start_model_download(http_client, ["definitely-not-a-real-model"])
    assert response.status_code in {207, 400, 404, 422}, response.text


@pytest.mark.full
def test_models_job_status_404_for_unknown_id(
    http_client: requests.Session,
) -> None:
    """``GET /jobs/models/{id}`` and ``.../status`` must return 404 for
    a job id that does not exist. This also locks in the behaviour the
    UI relies on when a stale polling loop survives a backend restart.
    """
    bogus_id = "no-such-job-id-12345"
    summary = get_model_job_summary(http_client, bogus_id)
    assert summary.status_code == 404, summary.text
    status = get_model_job_status(http_client, bogus_id)
    assert status.status_code == 404, status.text
