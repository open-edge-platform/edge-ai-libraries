"""Integration test ensuring the models endpoint responds with data."""

import logging

import requests

from api_helpers import fetch_models

logger = logging.getLogger(__name__)

REQUIRED_MODEL_KEYS: set[str] = {"name", "precision", "task_type", "source"}


def test_models_endpoint_returns_models(http_client: requests.Session) -> None:
    models = fetch_models(http_client)

    assert models, "Models endpoint returned an empty list"
    for raw in models:
        assert isinstance(raw, dict), "Each model entry must be an object"
        assert REQUIRED_MODEL_KEYS.issubset(raw.keys()), (
            f"Model entry missing required keys: {REQUIRED_MODEL_KEYS - raw.keys()}"
        )
        assert isinstance(raw.get("name"), str) and raw["name"], (
            "Model entry has invalid name"
        )
