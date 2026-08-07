# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""CI integration test for the VSS summarization pipeline.

Exercises the real Pipeline Manager REST lifecycle through the nginx gateway:
upload a fixture video, start a summary job with a 30s chunk duration, poll
until the pipeline reports completion (or times out), and assert the
resulting summary is non-empty and marked complete.

Requires a running VSS deployment (``source setup.sh --summary`` or
``--summary-and-search``) reachable at ``VSS_BASE_URL``
(default: http://localhost:12345/manager).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("VSS_BASE_URL", "http://localhost:12345/manager")
FIXTURE_VIDEO = Path(os.environ.get("VSS_FIXTURE_VIDEO", "./fixtures/sample.mp4"))

# Chunk duration matches the required 30-second sampling window.
SAMPLING = {
    "chunkDuration": 30,
    "samplingFrame": 4,
    "frameOverlap": 1,
    "multiFrame": 5,
}
EVAM = {"evamPipeline": "video_ingestion"}

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600  # 10 minutes: reasonable ceiling for a short fixture clip


def _poll_until_complete(state_id: str, timeout: int = POLL_TIMEOUT_SECONDS, interval: int = POLL_INTERVAL_SECONDS) -> dict:
    """Poll GET /summary/{stateId} until videoSummaryStatus is complete or timeout elapses."""
    deadline = time.monotonic() + timeout
    last_payload: dict = {}
    while time.monotonic() < deadline:
        resp = requests.get(f"{BASE_URL}/summary/{state_id}", timeout=60)
        resp.raise_for_status()
        last_payload = resp.json()
        if last_payload.get("videoSummaryStatus") == "complete":
            return last_payload
        time.sleep(interval)
    pytest.fail(
        f"Summary pipeline {state_id} did not reach 'complete' within {timeout}s; "
        f"last status={last_payload.get('videoSummaryStatus')!r}"
    )


def test_summary_pipeline_completes_with_non_empty_summary():
    assert FIXTURE_VIDEO.is_file(), f"missing fixture video: {FIXTURE_VIDEO}"

    # 1. Health check before doing anything else.
    health = requests.get(f"{BASE_URL}/health", timeout=30)
    assert health.ok, f"Pipeline Manager is not healthy: {health.status_code} {health.text}"

    # 2. Upload the fixture video.
    with FIXTURE_VIDEO.open("rb") as video_file:
        upload_resp = requests.post(
            f"{BASE_URL}/videos",
            files={"video": (FIXTURE_VIDEO.name, video_file, "video/mp4")},
            data={"tags": "ci-integration"},
            timeout=300,
        )
    assert upload_resp.ok, f"video upload failed: {upload_resp.status_code} {upload_resp.text}"
    video_id = upload_resp.json()["videoId"]

    # 3. Start summarization with a 30-second chunk duration.
    summary_resp = requests.post(
        f"{BASE_URL}/summary",
        json={
            "videoId": video_id,
            "title": "CI integration test summary",
            "sampling": SAMPLING,
            "evam": EVAM,
        },
        timeout=120,
    )
    assert summary_resp.ok, f"failed to start summary pipeline: {summary_resp.status_code} {summary_resp.text}"
    state_id = summary_resp.json()["summaryPipelineId"]

    # 4. Wait for the pipeline to finish (up to a reasonable timeout).
    final_summary = _poll_until_complete(state_id)

    # 5. Assert completion and non-empty summary text.
    assert final_summary.get("videoSummaryStatus") == "complete"
    summary_text = final_summary.get("summary") or ""
    assert summary_text.strip(), "expected non-empty summary text"
