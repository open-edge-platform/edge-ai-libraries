import os

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
