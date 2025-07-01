# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from audio_analyzer.core.settings import settings
from audio_analyzer.schemas.types import WhisperModel


@pytest.mark.api
def test_get_available_models(test_client: TestClient):
    """Test the get available models API endpoint"""

    response = test_client.get("/api/v1/models")
    assert response.status_code == 200
    
    # Verify the response contains the expected structure
    data = response.json()
    assert "models" in data
    assert "default_model" in data
    
    # Check each model has the required fields
    for model in data["models"]:
        assert "model_id" in model
        assert "display_name" in model
        assert "description" in model
    
    # Verify the model IDs match the settings
    expected_models = [model.value for model in settings.ENABLED_WHISPER_MODELS]
    actual_model_ids = [model["model_id"] for model in data["models"]]
    assert sorted(actual_model_ids) == sorted(expected_models)
    assert data["default_model"] == settings.DEFAULT_WHISPER_MODEL.value


@pytest.mark.api
@patch("audio_analyzer.api.endpoints.models.settings")
def test_get_available_models_with_custom_settings(mock_settings, test_client: TestClient):
    """Test the models endpoint with custom settings"""

    # Mock settings with specific models enabled
    custom_models = [WhisperModel.TINY_EN, WhisperModel.SMALL]
    default_model = WhisperModel.TINY_EN
    mock_settings.ENABLED_WHISPER_MODELS = custom_models
    mock_settings.DEFAULT_WHISPER_MODEL = default_model
    
    response = test_client.get("/api/v1/models")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check each model has the required fields
    for model in data["models"]:
        assert "model_id" in model
        assert "display_name" in model
        assert "description" in model
    
    # Verify the model IDs match the custom models
    expected_model_ids = [model.value for model in custom_models]
    actual_model_ids = [model["model_id"] for model in data["models"]]
    assert sorted(actual_model_ids) == sorted(expected_model_ids)
    assert data["default_model"] == default_model.value
