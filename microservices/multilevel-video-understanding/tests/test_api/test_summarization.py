from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def _mock_ok_summarizer(mock_video_summarizer):
    summarizer_instance = MagicMock()
    summarizer_instance.summarize = AsyncMock(
        return_value=(
            "job-1234",
            {
                "summary": "A short summary",
                "video_duration": 11.5,
            },
        )
    )
    mock_video_summarizer.return_value = summarizer_instance
    return summarizer_instance


@pytest.mark.api
@patch("video_analyzer.api.endpoints.summarization.VideoSummarizer")
@patch("video_analyzer.api.endpoints.summarization.validate_video_path")
def test_summary_endpoint_success(mock_validate_video_path, mock_video_summarizer, test_client: TestClient):
    mock_validate_video_path.return_value = "/tmp/demo.mp4"
    _mock_ok_summarizer(mock_video_summarizer)

    with patch("video_analyzer.api.endpoints.summarization.model_cfg") as model_cfg:
        model_cfg.VLM_MODEL_NAME = "Qwen/Qwen2.5-VL-7B-Instruct"
        model_cfg.LLM_MODEL_NAME = "Qwen/Qwen3-32B-AWQ"
        model_cfg.VLM_BASE_URL = "http://127.0.0.1:41091/v1"
        model_cfg.LLM_BASE_URL = "http://127.0.0.1:41090/v1"
        model_cfg.VLM_API_KEY = "EMPTY"
        model_cfg.LLM_API_KEY = "EMPTY"

        response = test_client.post(
            "/v1/summary",
            json={
                "video": "https://example.com/video.mp4",
                "method": "USE_ALL_T-1",
                "processor_kwargs": {"levels": 3, "level_sizes": [1, 6, -1], "process_fps": 1},
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["summary"] == "A short summary"
    assert data["job_id"] == "job-1234"
    assert data["video_name"] == "/tmp/demo.mp4"
    assert data["video_duration"] == 11.5


@pytest.mark.api
@pytest.mark.parametrize(
    "method",
    ["SIMPLE", "USE_VLM_T-1", "USE_LLM_T-1", "USE_ALL_T-1"],
)
@patch("video_analyzer.api.endpoints.summarization.VideoSummarizer")
@patch("video_analyzer.api.endpoints.summarization.validate_video_path")
def test_summary_endpoint_accepts_all_supported_methods(
    mock_validate_video_path,
    mock_video_summarizer,
    method,
    test_client: TestClient,
):
    mock_validate_video_path.return_value = "/tmp/demo.mp4"
    _mock_ok_summarizer(mock_video_summarizer)

    response = test_client.post(
        "/v1/summary",
        json={
            "video": "https://example.com/video.mp4",
            "method": method,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert mock_video_summarizer.call_args.kwargs["method"] == method


@pytest.mark.api
@pytest.mark.parametrize(
    "method",
    ["", "use_all_t-1", "USE_ALL_T_1", "RANDOM_METHOD", None],
)
def test_summary_endpoint_rejects_invalid_method_values(method, test_client: TestClient):
    response = test_client.post(
        "/v1/summary",
        json={
            "video": "https://example.com/video.mp4",
            "method": method,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_message"] == "Summarization failed!"
    assert "Unsupported summarization method" in detail["details"]


@pytest.mark.api
def test_summary_endpoint_rejects_unsupported_method(test_client: TestClient):
    response = test_client.post(
        "/v1/summary",
        json={
            "video": "https://example.com/video.mp4",
            "method": "NOT_A_VALID_METHOD",
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_message"] == "Summarization failed!"
    assert "Unsupported summarization method" in detail["details"]


@pytest.mark.api
@pytest.mark.parametrize(
    "processor_kwargs",
    [
        {"process_fps": 1, "levels": 3, "level_sizes": [1, 6, -1], "chunking_method": "pelt"},
        {"process_fps": 0.5, "levels": 2, "level_sizes": [1, -1], "chunking_method": "uniform"},
        {"process_fps": 2, "levels": 1, "level_sizes": [1], "chunking_method": "uniform"},
    ],
)
@patch("video_analyzer.api.endpoints.summarization.VideoSummarizer")
@patch("video_analyzer.api.endpoints.summarization.validate_video_path")
def test_summary_endpoint_passes_processor_kwargs_to_summarizer(
    mock_validate_video_path,
    mock_video_summarizer,
    processor_kwargs,
    test_client: TestClient,
):
    mock_validate_video_path.return_value = "/tmp/demo.mp4"
    _mock_ok_summarizer(mock_video_summarizer)

    response = test_client.post(
        "/v1/summary",
        json={
            "video": "https://example.com/video.mp4",
            "method": "USE_ALL_T-1",
            "processor_kwargs": processor_kwargs,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    call_kwargs = mock_video_summarizer.call_args.kwargs
    for key, value in processor_kwargs.items():
        assert call_kwargs[key] == value


@pytest.mark.api
@pytest.mark.parametrize(
    "bad_kwargs,error_details",
    [
        (
            {"levels": 0, "level_sizes": [1]},
            "Invalid levels is specified",
        ),
        (
            {"levels": 3, "level_sizes": [1, 6]},
            "should match with total levels",
        ),
        (
            {"process_fps": 0},
            "Invalid process_fps is specified",
        ),
        (
            {"chunking_method": "invalid-method"},
            "Unsupported video chunking method",
        ),
    ],
)
@patch("video_analyzer.api.endpoints.summarization.VideoSummarizer")
@patch("video_analyzer.api.endpoints.summarization.validate_video_path")
def test_summary_endpoint_returns_400_for_invalid_processor_kwargs(
    mock_validate_video_path,
    mock_video_summarizer,
    bad_kwargs,
    error_details,
    test_client: TestClient,
):
    mock_validate_video_path.return_value = "/tmp/demo.mp4"
    mock_video_summarizer.side_effect = HTTPException(
        status_code=400,
        detail={"error_message": "Summarization failed!", "details": error_details},
    )

    response = test_client.post(
        "/v1/summary",
        json={
            "video": "https://example.com/video.mp4",
            "method": "USE_ALL_T-1",
            "processor_kwargs": bad_kwargs,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_message"] == "Summarization failed!"
    assert error_details in detail["details"]


@pytest.mark.api
@patch("video_analyzer.api.endpoints.summarization.VideoSummarizer")
@patch("video_analyzer.api.endpoints.summarization.validate_video_path")
def test_summary_endpoint_returns_failed_status_on_model_error(
    mock_validate_video_path,
    mock_video_summarizer,
    test_client: TestClient,
):
    mock_validate_video_path.return_value = "/tmp/demo.mp4"

    summarizer_instance = MagicMock()
    summarizer_instance.summarize = AsyncMock(
        return_value=(
            "job-1234",
            {
                "summary": "Error: upstream model returned invalid output",
                "video_duration": 8.0,
            },
        )
    )
    mock_video_summarizer.return_value = summarizer_instance

    response = test_client.post(
        "/v1/summary",
        json={
            "video": "https://example.com/video.mp4",
            "method": "USE_ALL_T-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["summary"].startswith("Error:")
    assert data["job_id"] == "job-1234"


@pytest.mark.api
@patch("video_analyzer.api.endpoints.summarization.VideoSummarizer")
@patch("video_analyzer.api.endpoints.summarization.validate_video_path")
def test_summary_endpoint_returns_500_on_unexpected_exception(
    mock_validate_video_path,
    mock_video_summarizer,
    test_client: TestClient,
):
    mock_validate_video_path.return_value = "/tmp/demo.mp4"
    mock_video_summarizer.side_effect = RuntimeError("boom")

    response = test_client.post(
        "/v1/summary",
        json={
            "video": "https://example.com/video.mp4",
            "method": "USE_ALL_T-1",
        },
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["error_message"] == "Summarization failed!"


@pytest.mark.api
@patch("video_analyzer.api.endpoints.summarization.validate_video_path")
def test_summary_endpoint_bubbles_http_exception(mock_validate_video_path, test_client: TestClient):
    mock_validate_video_path.side_effect = HTTPException(
        status_code=400,
        detail={"error_message": "Invalid video path", "details": "empty"},
    )

    response = test_client.post(
        "/v1/summary",
        json={
            "video": "bad-path",
            "method": "USE_ALL_T-1",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_message"] == "Invalid video path"
