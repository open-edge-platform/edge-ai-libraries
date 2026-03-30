import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_client(monkeypatch):
    monkeypatch.setenv("VLM_MODEL_NAME", os.getenv("VLM_MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct"))
    monkeypatch.setenv("LLM_MODEL_NAME", os.getenv("LLM_MODEL_NAME", "Qwen/Qwen3-32B-AWQ"))
    monkeypatch.setenv("VLM_BASE_URL", os.getenv("VLM_BASE_URL", "http://127.0.0.1:41091/v1"))
    monkeypatch.setenv("LLM_BASE_URL", os.getenv("LLM_BASE_URL", "http://127.0.0.1:41090/v1"))

    from video_analyzer.main import app

    return TestClient(app)
