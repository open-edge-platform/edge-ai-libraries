"""Functional test ensuring the models endpoint responds with data."""

import logging

import requests

from api_helpers import fetch_models

logger = logging.getLogger(__name__)

VALID_MODEL_CATEGORIES: set[str] = {"detection", "classification", "segmentation"}
VALID_MODEL_PRECISIONS: set[str] = {"FP32", "FP16", "INT8"}


def test_models_endpoint_returns_models(http_client: requests.Session) -> None:
    models = fetch_models(http_client)

    assert models, "Models endpoint returned an empty list"
    for model_entry in models:
        assert isinstance(model_entry, dict), "Each model entry must be an object"
        assert isinstance(model_entry.get("name"), str) and model_entry["name"], (
            "Model entry has invalid name"
        )
        assert (
            isinstance(model_entry.get("display_name"), str)
            and model_entry["display_name"]
        ), "Model entry has invalid display_name"
        assert (
            isinstance(model_entry.get("category"), str)
            and model_entry["category"] in VALID_MODEL_CATEGORIES
        ), f"Model entry has unsupported category: {model_entry.get('category')}"
        assert (
            isinstance(model_entry.get("precision"), str)
            and model_entry["precision"] in VALID_MODEL_PRECISIONS
        ), f"Model entry has unsupported precision: {model_entry.get('precision')}"
