"""Shared fixtures for VIPPET functional tests."""

from collections.abc import Generator
from typing import Any

import pytest
import requests
import yaml

from helpers.config import DEFAULT_RECORDINGS_YAML, PROJECT_ROOT, SUPPORTED_MODELS_YAML

# Session-wide accumulator: (HTTP_METHOD, full_url_without_query_string)
_recorded_api_calls: set[tuple[str, str]] = set()


# Pipelines with externally pre-downloaded models (path template uses lowercase
# device ``family``, rooted at PROJECT_ROOT); variants skipped if path missing.
_EXTERNAL_MODEL_PATH_TEMPLATES: dict[str, str] = {
    "Video Summarization VLM": (
        "shared/models/output/openvino_models/{family}/int4/google/gemma-3-4b-it"
    ),
}


# Pipelines with no video encoder/muxer branch; ``output_mode=file`` returns
# an empty ``video_output_paths`` list, so the file-output test is skipped.
_NO_FILE_VIDEO_OUTPUT_PIPELINES: frozenset[str] = frozenset(
    {
        "Video Summarization VLM",
    }
)


# API call recording – used by test_z_api_coverage.py to verify that all
# API endpoints have been exercised at least once during the full test run.
class _RecordingSession(requests.Session):
    """Thin requests.Session subclass that records every outgoing request."""

    def request(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, method: str | bytes, url: str | bytes, **kwargs: Any
    ) -> requests.Response:
        clean_url = str(url).split("?")[0].split("#")[0]
        _recorded_api_calls.add((str(method).upper(), clean_url))
        return super().request(str(method), url, **kwargs)


@pytest.fixture(scope="session")
def http_client() -> Generator[requests.Session, None, None]:
    """Reusable HTTP session shared across all functional tests."""
    session = _RecordingSession()
    session.headers.update({"Accept": "application/json"})
    yield session
    session.close()


@pytest.fixture(scope="session")
def recorded_api_calls() -> set[tuple[str, str]]:
    """Return the set of (METHOD, URL) pairs recorded during this test session.

    Populated automatically by the shared ``http_client`` fixture.  Consumed by
    ``test_z_api_coverage.py`` to check that every API route has been called at
    least once.
    """
    return _recorded_api_calls


@pytest.fixture(scope="session")
def supported_models_config() -> list[dict[str, Any]]:
    """Load supported_models.yaml as the source-of-truth for model tests."""
    with SUPPORTED_MODELS_YAML.open() as f:
        data = yaml.safe_load(f)
    assert isinstance(data, list), "supported_models.yaml must be a list"
    return data


@pytest.fixture(scope="session")
def default_recordings_config() -> list[dict[str, Any]]:
    """Load default_recordings.yaml as the source-of-truth for video tests."""
    with DEFAULT_RECORDINGS_YAML.open() as f:
        data = yaml.safe_load(f)
    assert isinstance(data, list), "default_recordings.yaml must be a list"
    return data


@pytest.fixture(autouse=True)
def _skip_when_external_model_missing(request: pytest.FixtureRequest) -> None:
    """Skip parametrized pipeline cases whose pre-downloaded model is absent.

    Applies to pipelines listed in ``_EXTERNAL_MODEL_PATH_TEMPLATES`` (e.g. the
    VLM Video Summarization pipeline, which hard-codes its model path instead
    of going through ``supported_models.yaml``).
    """
    case = getattr(request.node, "callspec", None)
    case_value = case.params.get("case") if case is not None else None
    pipeline_name = getattr(case_value, "pipeline_name", None)
    if pipeline_name not in _EXTERNAL_MODEL_PATH_TEMPLATES:
        return

    family = getattr(case_value, "device_family", "").lower()
    model_path = PROJECT_ROOT / _EXTERNAL_MODEL_PATH_TEMPLATES[pipeline_name].format(
        family=family
    )
    if not model_path.is_dir():
        pytest.skip(
            f"Pre-downloaded model for pipeline '{pipeline_name}' "
            f"({getattr(case_value, 'device_family', '')}) not found at {model_path}. "
            "Download the model before running this test."
        )


@pytest.fixture(autouse=True)
def _skip_file_output_for_pipelines_without_video_sink(
    request: pytest.FixtureRequest,
) -> None:
    """Skip ``output_mode=file`` tests for pipelines listed in
    ``_NO_FILE_VIDEO_OUTPUT_PIPELINES`` (no encoder branch -> empty
    ``video_output_paths``).
    """
    if "file_output" not in request.node.name:
        return
    case = getattr(request.node, "callspec", None)
    case_value = case.params.get("case") if case is not None else None
    pipeline_name = getattr(case_value, "pipeline_name", None)
    if pipeline_name in _NO_FILE_VIDEO_OUTPUT_PIPELINES:
        pytest.skip(
            f"Pipeline '{pipeline_name}' has no video encoder branch; "
            "file-output mode produces no recorded video files."
        )
