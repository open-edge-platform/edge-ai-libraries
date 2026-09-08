# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path

import pytest
import requests


SERVICE_BASE_URL = os.getenv("MULTILEVEL_SERVICE_BASE_URL", "http://localhost:8192").rstrip(
    "/"
)
REQUEST_TIMEOUT_SECONDS = int(os.getenv("MULTILEVEL_SERVICE_TIMEOUT_SECONDS", "900"))
RESOURCES = Path(__file__).resolve().parent.parent / "resources"
CAPTION_ONLY_SRT = (RESOURCES / "caption_only_fridge_day.srt").read_text(encoding="utf-8")
VIDEO_URL = "https://videos.pexels.com/video-files/5992517/5992517-hd_1920_1080_30fps.mp4"


SUMMARY_CASES = [
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "SIMPLE",
            "processor_kwargs": {"process_fps": 1},
        },
        "Basic Video Summarization - Generate summary for standard video input",
        id="Multi-vs-06_basic_video_summarization",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "SIMPLE",
            "processor_kwargs": {"levels": 4, "level_sizes": [1, 6, 8, -1]},
        },
        "Multi-level Architecture Configuration - Test configurable analysis levels",
        id="Multi-vs-07_multilevel_configuration",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "USE_ALL_T-1",
            "processor_kwargs": {"process_fps": 1},
        },
        "Enhanced Temporal Modeling - Enable VLM and LLM temporal context",
        id="Multi-vs-08_temporal_all",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "USE_VLM_T-1",
            "processor_kwargs": {"process_fps": 1},
        },
        "Enhanced Temporal Modeling - Enable VLM temporal context only",
        id="Multi-vs-08_temporal_vlm_only",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "USE_LLM_T-1",
            "processor_kwargs": {"process_fps": 1},
        },
        "Enhanced Temporal Modeling - Enable LLM temporal context only",
        id="Multi-vs-08_temporal_llm_only",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "USE_ALL_T-1",
            "processor_kwargs": {"process_fps": 1, "chunking_method": "uniform"},
        },
        "Change Video Chunking Method - Use uniform chunking",
        id="Multi-vs-09_chunking_uniform",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "method": "USE_ALL_T-1",
            "processor_kwargs": {"process_fps": 1, "chunking_method": "pelt"},
        },
        "Change Video Chunking Method - Use PELT chunking",
        id="Multi-vs-09_chunking_pelt",
    ),
    pytest.param(
        {
            "video": "none",
            "video_subtitles": {"text": CAPTION_ONLY_SRT},
            "task": "summary",
            "method": "SIMPLE",
        },
        "Caption-only Summarization - Generate a report from subtitles only",
        id="Multi-vs-13_caption_only_summary",
    ),
    pytest.param(
        {
            "video": VIDEO_URL,
            "task": "summary_zh",
            "method": "SIMPLE",
            "processor_kwargs": {"process_fps": 1},
        },
        "Chinese Built-in Task - Generate a Chinese video summary",
        id="Multi-vs-14_chinese_builtin_task",
    ),
]


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("ENABLE_EXTERNAL_SERVING_TESTS") != "1",
    reason=(
        "Set ENABLE_EXTERNAL_SERVING_TESTS=1 after starting the multilevel "
        "service to run this deployed-service integration test."
    ),
)
def test_deployed_service_health():
    """Verify the deployed multilevel service is reachable and healthy."""
    health_response = requests.get(
        f"{SERVICE_BASE_URL}/v1/health", timeout=REQUEST_TIMEOUT_SECONDS
    )
    assert health_response.status_code == 200, health_response.text
    assert health_response.json()["status"] == "healthy"
    print("√ Deployed Service Health - Verify the multilevel service is healthy")


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("ENABLE_EXTERNAL_SERVING_TESTS") != "1",
    reason=(
        "Set ENABLE_EXTERNAL_SERVING_TESTS=1 after starting the multilevel "
        "service to run this deployed-service integration test."
    ),
)
@pytest.mark.parametrize("payload, description", SUMMARY_CASES)
def test_summary_via_deployed_service(payload, description):
    """Run the external-serving summary case matrix through the deployed API."""
    summary_response = requests.post(
        f"{SERVICE_BASE_URL}/v1/summary",
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    assert summary_response.status_code == 200, summary_response.text
    data = summary_response.json()
    assert data["status"] == "completed", data
    assert data["job_id"]
    assert isinstance(data["summary"], str) and data["summary"].strip()
    assert data["video_duration"] is not None
    print(f"√ {description}")