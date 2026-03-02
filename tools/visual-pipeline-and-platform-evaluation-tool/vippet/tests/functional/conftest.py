"""Shared fixtures for VIPPET functional tests."""

import pytest
import requests


@pytest.fixture(scope="session")
def http_client() -> requests.Session:
    """Reusable HTTP session shared across all functional tests."""
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    yield session
    session.close()
