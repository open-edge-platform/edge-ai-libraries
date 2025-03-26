import pytest
from fastapi.testclient import TestClient

from app.server import app


@pytest.fixture(scope="module")
def test_client():
    client = TestClient(app)
    yield client
