"""Functional tests for the Voice (audio pipeline) and audio job endpoints."""

import logging
import time
from typing import Any
from uuid import uuid4

import pytest
import requests

from helpers.config import BASE_URL, POLL_INTERVAL_SECONDS, POLL_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

type JsonDict = dict[str, Any]

_NONEXISTENT_JOB_ID = f"does-not-exist-{uuid4().hex[:8]}"
_TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}

STT_PIPELINE_ID = "speech-to-text"
TTS_PIPELINE_ID = "text-to-speech"
VARIANT_ID = "cpu"
RECORDING = "sample_male.wav"


def _start_stt_job(session: requests.Session) -> str:
    response = session.post(
        f"{BASE_URL}/voice/pipelines/{STT_PIPELINE_ID}/variants/{VARIANT_ID}/runs",
        json={"recording": RECORDING, "language": "en"},
        timeout=30,
    )
    assert response.status_code == 202, (
        f"Expected 202 starting STT job, got {response.status_code}, body={response.text}"
    )
    return response.json()["job_id"]


def _start_tts_job(session: requests.Session) -> str:
    response = session.post(
        f"{BASE_URL}/voice/pipelines/{TTS_PIPELINE_ID}/variants/{VARIANT_ID}/runs",
        json={"input": "Hello from the functional test.", "voice": "Ryan"},
        timeout=30,
    )
    assert response.status_code == 202, (
        f"Expected 202 starting TTS job, got {response.status_code}, body={response.text}"
    )
    return response.json()["job_id"]


def _wait_for_audio_job(session: requests.Session, job_id: str) -> JsonDict:
    """Poll GET /jobs/audio/{job_id}/status until the job reaches a terminal state."""
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        response = session.get(f"{BASE_URL}/jobs/audio/{job_id}/status", timeout=30)
        assert response.status_code == 200, (
            f"Expected 200 from audio job status, "
            f"got {response.status_code}, body={response.text}"
        )
        status: JsonDict = response.json()
        if status["state"] in _TERMINAL_STATES:
            return status
        if time.monotonic() >= deadline:
            pytest.fail(
                f"Audio job {job_id} still {status['state']} after "
                f"{POLL_TIMEOUT_SECONDS} seconds"
            )
        time.sleep(POLL_INTERVAL_SECONDS)


@pytest.mark.smoke
def test_list_audio_pipelines_returns_stt_and_tts(
    http_client: requests.Session,
) -> None:
    """GET /voice/pipelines lists the built-in speech-to-text and text-to-speech pipelines."""
    response = http_client.get(f"{BASE_URL}/voice/pipelines", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /voice/pipelines, "
        f"got {response.status_code}, body={response.text}"
    )
    pipelines = {p["id"]: p for p in response.json()}
    assert {STT_PIPELINE_ID, TTS_PIPELINE_ID} <= pipelines.keys(), (
        f"Missing built-in audio pipelines, got {sorted(pipelines)}"
    )
    assert pipelines[STT_PIPELINE_ID]["operation"] == "speech_to_text"
    assert pipelines[TTS_PIPELINE_ID]["operation"] == "text_to_speech"
    for pipeline in pipelines.values():
        assert pipeline["type"] == "audio"
        assert pipeline["variants"], f"Pipeline {pipeline['id']} has no variants"


@pytest.mark.smoke
def test_list_audio_recordings_contains_default_recordings(
    http_client: requests.Session,
) -> None:
    """GET /voice/recordings returns the default recordings with a playable audio_url."""
    response = http_client.get(f"{BASE_URL}/voice/recordings", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /voice/recordings, "
        f"got {response.status_code}, body={response.text}"
    )
    recordings = {r["filename"]: r for r in response.json()}
    assert RECORDING in recordings, (
        f"Default recording {RECORDING!r} missing, got {sorted(recordings)}"
    )
    assert recordings[RECORDING]["duration_seconds"] > 0
    assert recordings[RECORDING]["audio_url"].endswith(f"/{RECORDING}/audio")


@pytest.mark.smoke
def test_get_audio_recording_returns_wav(http_client: requests.Session) -> None:
    """GET /voice/recordings/{filename}/audio returns the recording as a WAV file."""
    response = http_client.get(
        f"{BASE_URL}/voice/recordings/{RECORDING}/audio", timeout=30
    )

    assert response.status_code == 200, (
        f"Expected 200 for recording audio, got {response.status_code}"
    )
    assert response.headers.get("content-type", "").startswith("audio/wav")
    assert response.content[:4] == b"RIFF" and response.content[8:12] == b"WAVE", (
        "Response body is not a WAV file"
    )


@pytest.mark.smoke
def test_get_audio_recording_for_nonexistent_file_returns_404(
    http_client: requests.Session,
) -> None:
    """GET /voice/recordings/{filename}/audio with an unknown filename returns 404."""
    response = http_client.get(
        f"{BASE_URL}/voice/recordings/does-not-exist.wav/audio", timeout=30
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown recording, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_run_audio_pipeline_for_nonexistent_pipeline_returns_404(
    http_client: requests.Session,
) -> None:
    """POST /voice/pipelines/{pipeline_id}/variants/{variant_id}/runs with an unknown pipeline returns 404."""
    response = http_client.post(
        f"{BASE_URL}/voice/pipelines/does-not-exist/variants/{VARIANT_ID}/runs",
        json={"input": "Hello", "voice": "Ryan"},
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown audio pipeline, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_run_audio_pipeline_with_invalid_body_returns_422(
    http_client: requests.Session,
) -> None:
    """POST /voice/pipelines/{pipeline_id}/variants/{variant_id}/runs with an invalid JSON body returns 422."""
    response = http_client.post(
        f"{BASE_URL}/voice/pipelines/{TTS_PIPELINE_ID}/variants/{VARIANT_ID}/runs",
        json={"unexpected": "field"},
        timeout=30,
    )

    assert response.status_code == 422, (
        f"Expected 422 for invalid run request, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_get_audio_artifact_for_nonexistent_job_returns_404(
    http_client: requests.Session,
) -> None:
    """GET /voice/jobs/{job_id}/artifact with an unknown job ID returns 404."""
    response = http_client.get(
        f"{BASE_URL}/voice/jobs/{_NONEXISTENT_JOB_ID}/artifact", timeout=30
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown audio job artifact, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_get_audio_job_status_for_nonexistent_job_returns_404(
    http_client: requests.Session,
) -> None:
    """GET /jobs/audio/{job_id}/status with an unknown job ID returns 404."""
    response = http_client.get(
        f"{BASE_URL}/jobs/audio/{_NONEXISTENT_JOB_ID}/status", timeout=30
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown audio job, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_stop_audio_job_for_nonexistent_job_returns_404(
    http_client: requests.Session,
) -> None:
    """DELETE /jobs/audio/{job_id} with an unknown job ID returns 404."""
    response = http_client.delete(
        f"{BASE_URL}/jobs/audio/{_NONEXISTENT_JOB_ID}", timeout=30
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown audio job stop, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_get_all_audio_job_statuses_returns_list(
    http_client: requests.Session,
) -> None:
    """GET /jobs/audio/status returns a list."""
    response = http_client.get(f"{BASE_URL}/jobs/audio/status", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /jobs/audio/status, "
        f"got {response.status_code}, body={response.text}"
    )
    assert isinstance(response.json(), list), "Response must be a list"


@pytest.mark.full
def test_speech_to_text_job_completes_with_transcript(
    http_client: requests.Session,
) -> None:
    """A speech-to-text job on a default recording completes, is listed, and cannot be stopped afterwards."""
    job_id = _start_stt_job(http_client)

    status = _wait_for_audio_job(http_client, job_id)

    assert status["state"] == "COMPLETED", (
        f"Expected COMPLETED STT job, got {status['state']}, error={status.get('error')}"
    )
    assert status["pipeline_id"] == STT_PIPELINE_ID
    assert status["variant_id"] == VARIANT_ID
    assert status["transcript"], "Completed STT job must have a transcript"
    assert status["artifact_url"] is None

    listing = http_client.get(f"{BASE_URL}/jobs/audio/status", timeout=30)
    assert listing.status_code == 200
    assert job_id in [s["id"] for s in listing.json()], (
        f"Job {job_id} not found in /jobs/audio/status"
    )

    stop = http_client.delete(f"{BASE_URL}/jobs/audio/{job_id}", timeout=30)
    assert stop.status_code == 409, (
        f"Expected 409 when stopping a completed audio job, "
        f"got {stop.status_code}, body={stop.text}"
    )


@pytest.mark.full
def test_text_to_speech_job_completes_with_wav_artifact(
    http_client: requests.Session,
) -> None:
    """A text-to-speech job completes and its artifact is downloadable as a WAV file."""
    job_id = _start_tts_job(http_client)

    status = _wait_for_audio_job(http_client, job_id)

    assert status["state"] == "COMPLETED", (
        f"Expected COMPLETED TTS job, got {status['state']}, error={status.get('error')}"
    )
    assert status["artifact_available"] is True
    assert status["artifact_url"], "Completed TTS job must expose artifact_url"

    artifact = http_client.get(f"{BASE_URL}/voice/jobs/{job_id}/artifact", timeout=60)
    assert artifact.status_code == 200, (
        f"Expected 200 for TTS artifact, got {artifact.status_code}"
    )
    assert artifact.headers.get("content-type", "").startswith("audio/wav")
    assert artifact.content[:4] == b"RIFF" and artifact.content[8:12] == b"WAVE", (
        "Artifact is not a WAV file"
    )


@pytest.mark.full
def test_get_audio_artifact_for_stt_job_returns_409(
    http_client: requests.Session,
) -> None:
    """GET /voice/jobs/{job_id}/artifact for a job without an artifact returns 409."""
    job_id = _start_stt_job(http_client)
    _wait_for_audio_job(http_client, job_id)

    response = http_client.get(f"{BASE_URL}/voice/jobs/{job_id}/artifact", timeout=30)

    assert response.status_code == 409, (
        f"Expected 409 for artifact of STT job, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.full
def test_stop_audio_job_cancels_job(http_client: requests.Session) -> None:
    """DELETE /jobs/audio/{job_id} right after start cancels the job (or 409 if it already finished)."""
    job_id = _start_tts_job(http_client)

    stop = http_client.delete(f"{BASE_URL}/jobs/audio/{job_id}", timeout=30)

    assert stop.status_code in (200, 409), (
        f"Expected 200 or 409 stopping audio job, "
        f"got {stop.status_code}, body={stop.text}"
    )
    status = _wait_for_audio_job(http_client, job_id)
    if stop.status_code == 200:
        assert status["state"] == "CANCELLED", (
            f"Expected CANCELLED after successful stop, got {status['state']}"
        )
