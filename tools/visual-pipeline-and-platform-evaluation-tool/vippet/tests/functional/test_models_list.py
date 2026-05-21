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
    """Flatten YAML model config entries into one entry per precision variant."""
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


def _api_model_variants(api_models: list[ModelDict]) -> list[ModelDict]:
    """Flatten the API response into one entry per ``ModelVariant``.

    The /models endpoint exposes each model as a single object with a
    nested ``variants`` array (one entry per precision / model-proc).
    These tests assert at the variant level so the helper flattens the
    response to align with the YAML expectations produced by
    :func:`_expand_model_precisions`.
    """
    flattened: list[ModelDict] = []
    for model in api_models:
        category = model.get("category")
        for variant in model.get("variants", []):
            flattened.append(
                {
                    "name": variant.get("name", ""),
                    "display_name": variant.get("display_name", ""),
                    "category": category,
                    "precision": variant.get("precision", ""),
                }
            )
    return flattened


def _assert_models_present_in_api(
    api_models: list[ModelDict],
    expected_models: list[ModelDict],
) -> None:
    """Assert that every expected model+precision combination exists in the API response."""
    api_variants = _api_model_variants(api_models)
    for model_cfg in expected_models:
        name: str = model_cfg["name"]
        display_name: str = model_cfg["display_name"]
        category: str = model_cfg["type"]
        expected_precision: str = model_cfg["precision"]

        matches = [
            v
            for v in api_variants
            if v.get("name", "").startswith(name)
            and v.get("display_name", "").startswith(display_name)
            and v.get("category") == category
            and v.get("precision") == expected_precision
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
        variants = model_entry.get("variants")
        assert isinstance(variants, list) and variants, (
            "Model entry has missing or empty variants list"
        )
        for variant in variants:
            assert isinstance(variant, dict), "Each variant must be an object"
            assert isinstance(variant.get("name"), str) and variant["name"], (
                "Variant has invalid name"
            )
            assert (
                isinstance(variant.get("display_name"), str) and variant["display_name"]
            ), "Variant has invalid display_name"
            assert (
                isinstance(variant.get("precision"), str)
                and variant["precision"] in VALID_MODEL_PRECISIONS
            ), f"Variant has unsupported precision: {variant.get('precision')}"


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
