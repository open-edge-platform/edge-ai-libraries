import os

# Configure the environment variable prior to importing the app
# This ensures the app operates in test mode, bypassing the startup function responsible for model downloading and conversion
os.environ['RUN_TEST'] = "True"

import pytest
from fastapi.testclient import TestClient

from app.server import app


@pytest.fixture(scope="module")
def test_client():
    client = TestClient(app)
    yield client
