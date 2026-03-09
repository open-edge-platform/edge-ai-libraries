import pytest
import sys
from types import ModuleType
from fastapi.testclient import TestClient

chain_stub = ModuleType("app.chain")
chain_stub.process_chunks = lambda *_args, **_kwargs: iter([])
sys.modules["app.chain"] = chain_stub

# application packages
from app.server import app

@pytest.fixture(scope="module")
def test_client():
    """A fixture to help send HTTP REST requests to API endpoints."""
    client = TestClient(app)
    yield client
