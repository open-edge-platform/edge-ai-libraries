"""Functional tests for pipelines CRUD and read-only rules."""

import logging
from typing import Any
from uuid import uuid4

import pytest
import requests

from api_helpers import fetch_pipelines
from config import BASE_URL

logger = logging.getLogger(__name__)


def _graph_dict() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "0", "type": "videotestsrc", "data": {}},
            {"id": "1", "type": "fakesink", "data": {}},
        ],
        "edges": [{"id": "0", "source": "0", "target": "1"}],
    }


def _find_predefined_pipeline(session: requests.Session) -> dict[str, Any]:
    pipelines = fetch_pipelines(session)
    for pipeline in pipelines:
        if pipeline.get("source") == "PREDEFINED":
            return pipeline
    pytest.skip("No PREDEFINED pipelines available in current environment")


@pytest.fixture
def created_pipeline_ids(http_client: requests.Session):
    ids: list[str] = []
    yield ids

    for pipeline_id in ids:
        response = http_client.delete(f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30)
        if response.status_code != 200:
            logger.warning(
                "Cleanup: failed to delete pipeline id=%s status=%s body=%s",
                pipeline_id,
                response.status_code,
                response.text,
            )


def test_get_pipelines_predefined_variants_are_read_only(http_client: requests.Session) -> None:
    pipelines = fetch_pipelines(http_client)
    predefined = [p for p in pipelines if p.get("source") == "PREDEFINED"]

    if not predefined:
        pytest.skip("No PREDEFINED pipelines available in current environment")

    for pipeline in predefined:
        variants = pipeline.get("variants", [])
        assert variants, f"PREDEFINED pipeline '{pipeline.get('id')}' has no variants"
        for variant in variants:
            assert variant.get("read_only") is True, (
                f"Expected read_only=True for PREDEFINED variant id={variant.get('id')}"
            )


def test_create_pipeline_with_default_variant_and_add_custom_variant(http_client: requests.Session, created_pipeline_ids: list[str]) -> None:
    default_variant_name = "CPU"
    custom_variant_name = "CUSTOM_GPU"
    unique_name = f"functional-pipeline-{uuid4().hex[:8]}"

    create_payload = {
        "name": unique_name,
        "description": "Functional test pipeline",
        "tags": ["functional", "pipelines"],
        "variants": [
            {
                "name": default_variant_name,
                "pipeline_graph": _graph_dict(),
                "pipeline_graph_simple": _graph_dict(),
            }
        ],
    }

    create_response = http_client.post(
        f"{BASE_URL}/pipelines", json=create_payload, timeout=30
    )
    assert create_response.status_code == 201, (
        f"create_pipeline failed: {create_response.status_code} {create_response.text}"
    )

    pipeline_id = create_response.json().get("id")
    assert isinstance(pipeline_id, str) and pipeline_id
    created_pipeline_ids.append(pipeline_id)

    get_response = http_client.get(f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30)
    assert get_response.status_code == 200, (
        f"get_pipeline failed: {get_response.status_code} {get_response.text}"
    )
    pipeline_data = get_response.json()
    assert pipeline_data.get("source") == "USER_CREATED"

    default_variant = pipeline_data["variants"][0]
    assert default_variant.get("name") == default_variant_name
    assert default_variant.get("read_only") is False

    create_custom_variant_payload = {
        "name": custom_variant_name,
        "pipeline_graph": _graph_dict(),
        "pipeline_graph_simple": _graph_dict(),
    }
    custom_variant_response = http_client.post(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants",
        json=create_custom_variant_payload,
        timeout=30,
    )
    assert custom_variant_response.status_code == 201, (
        f"create_variant failed: {custom_variant_response.status_code} "
        f"{custom_variant_response.text}"
    )

    custom_variant = custom_variant_response.json()
    assert custom_variant.get("name") == custom_variant_name
    assert custom_variant.get("read_only") is False


def test_predefined_pipeline_modification_is_forbidden(http_client: requests.Session) -> None:
    predefined_pipeline = _find_predefined_pipeline(http_client)
    pipeline_id = predefined_pipeline["id"]
    variant_id = predefined_pipeline["variants"][0]["id"]

    update_pipeline_response = http_client.patch(
        f"{BASE_URL}/pipelines/{pipeline_id}",
        json={"name": "forbidden-update"},
        timeout=30,
    )
    assert update_pipeline_response.status_code == 400, (
        f"Expected 400 for PREDEFINED pipeline update, got "
        f"{update_pipeline_response.status_code}, body={update_pipeline_response.text}"
    )

    delete_pipeline_response = http_client.delete(
        f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30
    )
    assert delete_pipeline_response.status_code == 400, (
        f"Expected 400 for PREDEFINED pipeline delete, got "
        f"{delete_pipeline_response.status_code}, body={delete_pipeline_response.text}"
    )

    update_variant_response = http_client.patch(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}",
        json={"name": "forbidden-variant-update"},
        timeout=30,
    )
    assert update_variant_response.status_code == 400, (
        f"Expected 400 for read-only variant update, got "
        f"{update_variant_response.status_code}, body={update_variant_response.text}"
    )

    delete_variant_response = http_client.delete(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}", timeout=30
    )
    assert delete_variant_response.status_code == 400, (
        f"Expected 400 for read-only variant delete, got "
        f"{delete_variant_response.status_code}, body={delete_variant_response.text}"
    )


def test_create_pipeline_with_empty_name(http_client: requests.Session) -> None:
    payload = {
        "name": "",
        "description": "Should fail due to empty name",
        "tags": ["functional", "validation"],
        "variants": [
            {
                "name": "CPU",
                "pipeline_graph": _graph_dict(),
                "pipeline_graph_simple": _graph_dict(),
            }
        ],
    }

    response = http_client.post(f"{BASE_URL}/pipelines", json=payload, timeout=30)

    # Pydantic validation for min_length=1 should reject empty name.
    assert response.status_code == 422, (
        f"Expected 422 for empty pipeline name, got {response.status_code}, body={response.text}"
    )


def test_create_pipeline_with_duplicate_variant_names(http_client: requests.Session, created_pipeline_ids: list[str]) -> None:
    unique_name = f"functional-pipeline-dup-variants-{uuid4().hex[:8]}"
    duplicate_variant_name = "CPU"
    payload = {
        "name": unique_name,
        "description": "Pipeline with duplicate variant names",
        "tags": ["functional", "variants"],
        "variants": [
            {
                "name": duplicate_variant_name,
                "pipeline_graph": _graph_dict(),
                "pipeline_graph_simple": _graph_dict(),
            },
            {
                "name": duplicate_variant_name,
                "pipeline_graph": _graph_dict(),
                "pipeline_graph_simple": _graph_dict(),
            },
        ],
    }

    response = http_client.post(f"{BASE_URL}/pipelines", json=payload, timeout=30)
    assert response.status_code == 201, (
        f"Expected 201 when creating pipeline with duplicate variant names, got "
        f"{response.status_code}, body={response.text}"
    )

    pipeline_id = response.json().get("id")
    assert isinstance(pipeline_id, str) and pipeline_id
    created_pipeline_ids.append(pipeline_id)

    get_response = http_client.get(f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30)
    assert get_response.status_code == 200, (
        f"get_pipeline failed: {get_response.status_code} {get_response.text}"
    )
    pipeline_data = get_response.json()
    variants = pipeline_data.get("variants", [])

    assert len(variants) == 2, "Expected two variants in created pipeline"
    assert all(v.get("name") == duplicate_variant_name for v in variants)

    variant_ids = [v.get("id") for v in variants]
    assert len(set(variant_ids)) == 2, (
        f"Expected unique variant ids for duplicate names, got ids={variant_ids}"
    )


def test_update_nonexistent_pipeline(http_client: requests.Session) -> None:
    nonexistent_pipeline_id = f"does-not-exist-{uuid4().hex[:8]}"
    response = http_client.patch(
        f"{BASE_URL}/pipelines/{nonexistent_pipeline_id}",
        json={"name": "new-name"},
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for non-existent pipeline update, got "
        f"{response.status_code}, body={response.text}"
    )
