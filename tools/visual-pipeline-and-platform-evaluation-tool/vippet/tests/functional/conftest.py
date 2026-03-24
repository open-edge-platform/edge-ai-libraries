"""Shared fixtures for VIPPET functional tests."""

from collections.abc import Generator
from typing import Any

import pytest
import requests
import yaml

from helpers.config import DEFAULT_RECORDINGS_YAML, SUPPORTED_MODELS_YAML

# Session-wide accumulator: (HTTP_METHOD, full_url_without_query_string)
_recorded_api_calls: set[tuple[str, str]] = set()


# API call recording – used by test_z_api_coverage.py to verify that all
# API endpoints have been exercised at least once during the full test run.
class _RecordingSession(requests.Session):
    """Thin requests.Session subclass that records every outgoing request."""

    def request(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, method: str | bytes, url: str | bytes, **kwargs: Any
    ) -> requests.Response:
        clean_url = str(url).split("?")[0].split("#")[0]
        _recorded_api_calls.add((str(method).upper(), clean_url))
        return super().request(method, url, **kwargs)


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
