import os
from pathlib import Path

import pytest


REQUIRED_ENV_KEYS = [
    "VLM_BASE_URL",
    "LLM_BASE_URL",
    "VLM_MODEL_NAME",
    "LLM_MODEL_NAME",
]


def _has_required_external_env() -> bool:
    return all(os.getenv(key) for key in REQUIRED_ENV_KEYS)


VIDEO_URL = "https://videos.pexels.com/video-files/5992517/5992517-hd_1920_1080_30fps.mp4"

# Prompt-task content shipped next to the tests (used for the /v1/tasks cases).
RESOURCES = Path(__file__).resolve().parent.parent / "resources"

# A caption-only event log (SubRip) — no video/VLM needed, LLM-only path.
CAPTION_ONLY_SRT_FILE = RESOURCES / "caption_only_fridge_day.srt"
CAPTION_ONLY_SRT = CAPTION_ONLY_SRT_FILE.read_text(encoding="utf-8")


SUMMARY_CASES = [
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "SIMPLE",
            "processor_kwargs": {"process_fps": 1},
        },
        id="Multi-vs-06_basic_video_summarization",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "SIMPLE",
            "processor_kwargs": {"levels": 4, "level_sizes": [1, 6, 8, -1]},
        },
        id="Multi-vs-07_multilevel_configuration",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "USE_ALL_T-1",
            "processor_kwargs": {"process_fps": 1},
        },
        id="Multi-vs-08_temporal_all",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "USE_VLM_T-1",
            "processor_kwargs": {"process_fps": 1},
        },
        id="Multi-vs-08_temporal_vlm_only",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "USE_LLM_T-1",
            "processor_kwargs": {"process_fps": 1},
        },
        id="Multi-vs-08_temporal_llm_only",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "USE_ALL_T-1",
            "processor_kwargs": {"process_fps": 1, "chunking_method": "uniform"},
        },
        id="Multi-vs-09_chunking_uniform",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "USE_ALL_T-1",
            "processor_kwargs": {"process_fps": 1, "chunking_method": "pelt"},
        },
        id="Multi-vs-09_chunking_pelt",
    ),
    # ----- new in 2026.2: caption-only + built-in Chinese task -----
    pytest.param(
        {
            "video": "none",
            "video_subtitles": {"text": CAPTION_ONLY_SRT},
            "task": "summary",
            "method": "SIMPLE",
        },
        id="Multi-vs-13_caption_only_summary",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "task": "summary_zh",
            "method": "SIMPLE",
            "processor_kwargs": {"process_fps": 1},
        },
        id="Multi-vs-14_chinese_builtin_task",
    ),
]


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("ENABLE_EXTERNAL_SERVING_TESTS") != "1" or not _has_required_external_env(),
    reason="Set ENABLE_EXTERNAL_SERVING_TESTS=1 and export VLM/LLM endpoint envs to run this test.",
)
@pytest.mark.parametrize("payload", SUMMARY_CASES)
def test_summary_with_external_serving(test_client, payload):
    response = test_client.post(
        "/v1/summary",
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["completed", "failed"]
    assert data["job_id"]
    assert "summary" in data
    assert data["video_duration"] is not None


# ---------------------------------------------------------------------------
# New in 2026.2 — dynamic prompt-task registry (/v1/tasks) end-to-end.
# These exercise the registration fallbacks and then feed a registered task
# into /v1/summary against the external serving.
# ---------------------------------------------------------------------------
_external_serving = pytest.mark.skipif(
    os.getenv("ENABLE_EXTERNAL_SERVING_TESTS") != "1" or not _has_required_external_env(),
    reason="Set ENABLE_EXTERNAL_SERVING_TESTS=1 and export VLM/LLM endpoint envs to run this test.",
)


@pytest.mark.integration
@_external_serving
def test_caption_only_summary_from_srt_file(test_client):
    """Multi-vs-21: load subtitles by pointing the service at an .srt FILE via
    {"path": ...} — the same local-file workflow as Multi-vs-10 for video
    (`docker cp` the file into the container, then reference it by path).

    In-process (TestClient) the service reads the host path directly; in a
    container the file must first be copied in (see the test plan Multi-vs-21).
    """
    resp = test_client.post(
        "/v1/summary",
        json={
            "video": "none",
            "video_subtitles": {"path": str(CAPTION_ONLY_SRT_FILE)},
            "task": "summary",
            "method": "SIMPLE",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] in ["completed", "failed"]
    assert data["job_id"]
    assert "summary" in data
    assert data["video_duration"] is not None


@pytest.mark.integration
@_external_serving
def test_register_minimal_task_autofills_optional_sections(test_client):
    """Register with only GLOBAL_PROMPT + LOCAL_PROMPT; the service auto-fills
    MACRO_CHUNK_PROMPT / T_MINUS_1_PROMPT and scaffolds missing placeholders."""
    task_name = "it_minimal_report"
    content = (RESOURCES / "task_minimal_report.txt").read_text(encoding="utf-8")
    test_client.delete(f"/v1/tasks/{task_name}")  # ensure clean slate

    try:
        resp = test_client.post(
            "/v1/tasks",
            json={"task_name": task_name, "mode": "full", "content": {"text": content}},
        )
        assert resp.status_code == 201, resp.text

        detail = test_client.get(f"/v1/tasks/{task_name}")
        assert detail.status_code == 200, detail.text
        body = detail.json()["content"]
        # Optional sections were materialized, and time placeholders scaffolded.
        assert "MACRO_CHUNK_PROMPT" in body and "T_MINUS_1_PROMPT" in body
        assert "{st_tm}" in body and "{end_tm}" in body
        assert "{dur}" in body and "{past_summary}" in body
    finally:
        test_client.delete(f"/v1/tasks/{task_name}")


@pytest.mark.integration
@_external_serving
def test_summary_with_registered_dynamic_task(test_client):
    """Multi-vs-16 + Multi-vs-20: register a full custom task from a resource
    file, run /v1/summary against it with a real video, then clean up."""
    task_name = "it_playground_safety"
    content = (RESOURCES / "task_playground_safety.txt").read_text(encoding="utf-8")
    test_client.delete(f"/v1/tasks/{task_name}")  # ensure clean slate

    try:
        reg = test_client.post(
            "/v1/tasks",
            json={"task_name": task_name, "mode": "full", "content": {"text": content}},
        )
        assert reg.status_code == 201, reg.text
        assert reg.json()["source"] == "dynamic"

        listing = test_client.get("/v1/tasks").json()["tasks"]
        assert any(t["name"] == task_name and t["source"] == "dynamic" for t in listing)

        resp = test_client.post(
            "/v1/summary",
            json={
                "video": VIDEO_URL,
                "task": task_name,
                "method": "SIMPLE",
                "processor_kwargs": {"process_fps": 1},
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] in ["completed", "failed"]
        assert data["job_id"]
        assert "summary" in data
        assert data["video_duration"] is not None
    finally:
        assert test_client.delete(f"/v1/tasks/{task_name}").status_code in (204, 404)
