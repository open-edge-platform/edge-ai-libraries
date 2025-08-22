import pytest


# Mock model list
mock_model_list = [
        {
            "model": "phi3.5:latest",
            "name": "phi3.5:latest"
        },
        {
            "model": "nomic-embed-text:latest",
            "name": "nomic-embed-text:latest"
        }
    ]


# Mock metadata for each model
mock_model_metadata_map = {
    "phi3.5:latest": {
        "details": {
            "parent_model": "",
            "format": "gguf",
            "family": "phi3",
            "families": ["phi3"],
            "parameter_size": "3.8B",
            "quantization_level": "Q4_0"
        }
    },
    "nomic-embed-text:latest": {
        "details": {
            "parent_model": "",
            "format": "gguf",
            "family": "nomic-bert",
            "families": ["nomic-bert"],
            "parameter_size": "137M",
            "quantization_level": "F16"
        }
    }
}


def test_get_loaded_ollama_models(test_client, mocker, skip_if_not_ollama):
    """
    Tests the retrieval of loaded Ollama models via the API endpoint.
    This test mocks the `list_active_models` method of the OllamaBackend to return a predefined list of models.
    It then sends a GET request to the `/ollama-models` endpoint and verifies:
      - The response status code is 200 (OK).
      - The response JSON contains the "model_list" key.
      - The "model_list" value is a list.
      - Each item in the "model_list" contains both "model" and "name" keys.
    Args:
        test_client: The test client fixture for making HTTP requests to the API.
        mocker: The pytest-mock fixture for patching methods.
        skip_if_not_ollama: Fixture to skip the test if Ollama is not available.
    """

    mocker.patch('app.ollama_backend.OllamaBackend.list_active_models', return_value=mock_model_list)
    response = test_client.get("/ollama-models")
    assert response.status_code == 200
    assert "model_list" in response.json()
    assert isinstance(response.json()["model_list"], list)
    assert all("model" in m and "name" in m for m in response.json()["model_list"])


@pytest.mark.parametrize("model_id", list(mock_model_metadata_map.keys()))
def test_get_ollama_model_metadata(test_client, mocker, model_id, skip_if_not_ollama):
    """
    Tests the retrieval of Ollama model metadata via the API endpoint.
    This test mocks the OllamaBackend's `show_model_info` method to return
    expected metadata for a given model ID. It then sends a GET request to the
    corresponding API endpoint and asserts that the response status code is 200
    and the returned JSON matches the expected metadata.
    Args:
        test_client: The test client used to make HTTP requests to the API.
        mocker: The pytest-mock fixture used to patch methods.
        model_id (str): The identifier of the Ollama model to retrieve metadata for.
        skip_if_not_ollama: Fixture or marker to skip the test if Ollama is not available.
    """

    expected_metadata = mock_model_metadata_map[model_id]
    mocker.patch('app.ollama_backend.OllamaBackend.show_model_info', return_value=expected_metadata)
    response = test_client.get("/ollama-model?model_id={model_id}")
    assert response.status_code == 200
    assert response.json() == expected_metadata


def test_invalid_ollama_model_id(test_client, mocker, skip_if_not_ollama):
    """
    Test the API endpoint for retrieving Ollama model information with an invalid model ID.
    This test verifies that when an invalid or nonexistent model ID is requested,
    the backend properly handles the error by raising an exception, logging it, and
    returning a 404 response with the appropriate error message.
    Args:
        test_client: A test client fixture for making HTTP requests to the API.
        mocker: A pytest-mock fixture for patching and mocking objects.
        skip_if_not_ollama: A fixture to skip the test if Ollama is not available.
    Raises:
        AssertionError: If the response status code is not 404 or the error message is incorrect.
    """

    invalid_model_id = "nonexistent-model"

    mocker.patch('app.ollama_backend.OllamaBackend.show_model_info', side_effect=Exception("Error getting model metadata."))

    response = test_client.get(f"/ollama-model?model_id={invalid_model_id}")

    # Check for expected error response
    assert response.status_code == 404
    assert response.json() == {
        "detail": "Error getting model metadata."
    }
