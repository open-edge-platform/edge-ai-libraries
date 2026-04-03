"""Functional tests for the /models endpoint."""

import logging
from typing import Any

import pytest
import requests

from helpers.api_helpers import fetch_models

logger = logging.getLogger(__name__)

type ModelDict = dict[str, Any]

VALID_MODEL_CATEGORIES: set[str] = {"detection", "classification", "segmentation"}
VALID_MODEL_PRECISIONS: set[str] = {"FP32", "FP16", "INT8"}


def _expand_model_precisions(models: list[ModelDict]) -> list[ModelDict]:
    """Flatten a list of model config entries into one entry per precision variant."""
    return [
        {
            "name": m["name"],
            "display_name": m["display_name"],
            "type": m["type"],
            "precision": prec["precision"],
        }
        for m in models
        for prec in m.get("precisions", [])
    ]


def _assert_models_present_in_api(
    api_models: list[ModelDict],
    expected_models: list[ModelDict],
) -> None:
    """Assert that every expected model+precision combination exists in the API response."""
    for model_cfg in expected_models:
        name: str = model_cfg["name"]
        display_name: str = model_cfg["display_name"]
        category: str = model_cfg["type"]
        expected_precision: str = model_cfg["precision"]

        matches = [
            m
            for m in api_models
            if m.get("name", "").startswith(name)
            and m.get("display_name", "").startswith(display_name)
            and m.get("category") == category
            and m.get("precision") == expected_precision
        ]
        assert matches, (
            f"Model '{name}' with precision '{expected_precision}' is missing from API response"
        )


@pytest.mark.smoke
def test_models_endpoint_returns_models(http_client: requests.Session) -> None:
    """Basic schema validation: every entry returned by the API is well-formed."""
    models: list[ModelDict] = fetch_models(http_client)

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


@pytest.mark.smoke
def test_default_models_present_in_api(
    http_client: requests.Session,
    supported_models_config: list[ModelDict],
) -> None:
    """Every model marked as default=true in supported_models.yaml must be
    returned by the API with the correct display_name, precision and category."""
    api_models = fetch_models(http_client)

    default_models = _expand_model_precisions(
        [m for m in supported_models_config if m.get("default") is True]
    )
    assert default_models, "No default models found in supported_models.yaml"
    logger.info(
        "Verifying %d default model variant(s) from config", len(default_models)
    )

    _assert_models_present_in_api(api_models, default_models)


@pytest.mark.full
def test_all_models_present_in_api(
    http_client: requests.Session,
    supported_models_config: list[ModelDict],
) -> None:
    """Every model defined in supported_models.yaml must be returned by the API
    with the correct display_name, precision and category."""
    api_models = fetch_models(http_client)

    all_models = _expand_model_precisions(supported_models_config)
    assert all_models, "No models found in supported_models.yaml"
    logger.info("Verifying %d model variant(s) from config", len(all_models))

    _assert_models_present_in_api(api_models, all_models)
