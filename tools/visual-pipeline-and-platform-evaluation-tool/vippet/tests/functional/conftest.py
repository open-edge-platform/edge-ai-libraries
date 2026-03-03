"""Shared fixtures for VIPPET functional tests."""

from collections.abc import Generator

import pytest
import requests


@pytest.fixture(scope="session")
def http_client() -> Generator[requests.Session, None, None]:
    """Reusable HTTP session shared across all functional tests."""
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    yield session
    session.close()
