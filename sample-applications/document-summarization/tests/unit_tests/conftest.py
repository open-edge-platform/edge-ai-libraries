import pytest
from fastapi.testclient import TestClient

# application packages
from app.server import app

@pytest.fixture(scope="module")
def test_client():
    """A fixture to help send HTTP REST requests to API endpoints."""
    client = TestClient(app)
    yield client
