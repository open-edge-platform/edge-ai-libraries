"""Shared fixtures for VIPPET functional tests."""

from collections.abc import Generator
from typing import Any

import pytest
import requests
import yaml

from helpers.config import DEFAULT_RECORDINGS_YAML, SUPPORTED_MODELS_YAML


@pytest.fixture(scope="session")
def http_client() -> Generator[requests.Session, None, None]:
    """Reusable HTTP session shared across all functional tests."""
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    yield session
    session.close()


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
