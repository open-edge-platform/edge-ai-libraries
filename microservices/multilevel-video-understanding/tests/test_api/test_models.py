# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from fastapi.testclient import TestClient

@pytest.mark.api
def test_get_available_models(test_client: TestClient, monkeypatch):
    """Test the get available models API endpoint"""

    monkeypatch.setenv("LLM_MODEL_NAME", "Qwen/Qwen3-32B-AWQ")
    monkeypatch.setenv("VLM_MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:41090/v1")
    monkeypatch.setenv("VLM_BASE_URL", "http://127.0.0.1:41091/v1")

    response = test_client.get("/v1/models")
    assert response.status_code == 200

    data = response.json()
    assert "llms" in data
    assert "vlms" in data

    assert len(data["llms"]) == 1
    assert len(data["vlms"]) == 1

    llm = data["llms"][0]
    vlm = data["vlms"][0]

    assert llm["model_id"] == "Qwen/Qwen3-32B-AWQ"
    assert llm["display_name"] == "Qwen/Qwen3-32B-AWQ"
    assert llm["base_url"] == "http://127.0.0.1:41090/v1"
    assert "description" in llm

    assert vlm["model_id"] == "Qwen/Qwen2.5-VL-7B-Instruct"
    assert vlm["display_name"] == "Qwen/Qwen2.5-VL-7B-Instruct"
    assert vlm["base_url"] == "http://127.0.0.1:41091/v1"
    assert "description" in vlm
