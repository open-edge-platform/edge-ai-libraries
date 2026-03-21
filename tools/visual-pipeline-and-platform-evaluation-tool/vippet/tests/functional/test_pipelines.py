"""Functional tests for pipelines CRUD and read-only rules."""

import copy
import logging
from typing import Any
from uuid import uuid4

import pytest
import requests

from helpers.api_helpers import convert_to_advanced, fetch_pipelines
from helpers.config import BASE_URL

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


@pytest.mark.smoke
def test_get_pipelines_predefined_variants_are_read_only(
    http_client: requests.Session,
) -> None:
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


@pytest.mark.smoke
def test_create_pipeline_with_default_variant_and_add_custom_variant(
    http_client: requests.Session, created_pipeline_ids: list[str]
) -> None:
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


@pytest.mark.smoke
def test_predefined_pipeline_metadata_can_be_updated(
    http_client: requests.Session,
) -> None:
    """Test that PREDEFINED pipeline metadata (name, description, tags) can be updated."""
    predefined_pipeline = _find_predefined_pipeline(http_client)
    pipeline_id = predefined_pipeline["id"]

    original_name = predefined_pipeline.get("name", "")
    original_description = predefined_pipeline.get("description", "")
    original_tags = predefined_pipeline.get("tags", [])

    # Test metadata update is allowed
    update_payload = {
        "name": f"{original_name}-updated",
        "description": f"{original_description} updated",
        "tags": ["functional", "predefined"],
    }

    response = http_client.patch(
        f"{BASE_URL}/pipelines/{pipeline_id}",
        json=update_payload,
        timeout=30,
    )

    assert response.status_code == 200
    updated_pipeline = response.json()
    assert updated_pipeline.get("name") == update_payload["name"]
    assert updated_pipeline.get("description") == update_payload["description"]
    assert updated_pipeline.get("tags") == update_payload["tags"]

    # Cleanup - restore original metadata
    http_client.patch(
        f"{BASE_URL}/pipelines/{pipeline_id}",
        json={
            "name": original_name,
            "description": original_description,
            "tags": original_tags,
        },
        timeout=30,
    )


@pytest.mark.smoke
def test_predefined_pipeline_cannot_be_deleted(http_client: requests.Session) -> None:
    """Test that PREDEFINED pipelines cannot be deleted."""
    predefined_pipeline = _find_predefined_pipeline(http_client)
    pipeline_id = predefined_pipeline["id"]

    response = http_client.delete(f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30)

    assert response.status_code == 400, (
        f"Expected 400 for PREDEFINED pipeline delete, got "
        f"{response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_predefined_variants_cannot_be_modified(http_client: requests.Session) -> None:
    """Test that read-only variants from PREDEFINED pipelines cannot be modified."""
    predefined_pipeline = _find_predefined_pipeline(http_client)
    pipeline_id = predefined_pipeline["id"]
    variant_id = predefined_pipeline["variants"][0]["id"]

    # Test variant update is forbidden
    update_response = http_client.patch(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}",
        json={"name": "forbidden-update"},
        timeout=30,
    )
    assert update_response.status_code == 400

    # Test variant graph update is forbidden
    graph_update_response = http_client.patch(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}",
        json={"pipeline_graph": _graph_dict()},
        timeout=30,
    )
    assert graph_update_response.status_code == 400


@pytest.mark.smoke
def test_predefined_variants_cannot_be_deleted(http_client: requests.Session) -> None:
    """Test that read-only variants from PREDEFINED pipelines cannot be deleted."""
    predefined_pipeline = _find_predefined_pipeline(http_client)
    pipeline_id = predefined_pipeline["id"]
    variant_id = predefined_pipeline["variants"][0]["id"]

    response = http_client.delete(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}", timeout=30
    )

    assert response.status_code == 400, (
        f"Expected 400 for read-only variant delete, got "
        f"{response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
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


@pytest.mark.smoke
def test_create_pipeline_with_duplicate_variant_names(
    http_client: requests.Session, created_pipeline_ids: list[str]
) -> None:
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


@pytest.mark.smoke
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


@pytest.mark.smoke
def test_convert_advanced_to_simple_graph(http_client: requests.Session) -> None:
    """Test POST /pipelines/{id}/variants/{id}/convert-to-simple endpoint."""
    predefined_pipeline = _find_predefined_pipeline(http_client)
    pipeline_id = predefined_pipeline["id"]
    variant_id = predefined_pipeline["variants"][0]["id"]

    response = http_client.post(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}/convert-to-simple",
        json=_graph_dict(),
        timeout=30,
    )
    assert response.status_code == 200
    assert "nodes" in response.json()
    assert "edges" in response.json()


@pytest.mark.smoke
def test_convert_simple_to_advanced_graph_with_property_change(
    http_client: requests.Session,
) -> None:
    """Test POST convert-to-advanced maps a camera source node to v4l2src."""
    predefined_pipeline = _find_predefined_pipeline(http_client)
    pipeline_id = predefined_pipeline["id"]
    variant_id = predefined_pipeline["variants"][0]["id"]
    simple_graph = predefined_pipeline["variants"][0]["pipeline_graph_simple"]
    advanced_graph = predefined_pipeline["variants"][0]["pipeline_graph"]

    # Precondition: the predefined advanced graph uses a file-based source
    assert any(
        node.get("type") == "filesrc" for node in advanced_graph.get("nodes", [])
    ), "Expected filesrc node in predefined advanced graph"

    # Build a modified simple graph that switches the source to a camera device
    modified_simple_graph = copy.deepcopy(simple_graph)
    for node in modified_simple_graph.get("nodes", []):
        if node.get("type") == "source":
            node["data"]["kind"] = "camera"
            node["data"]["source"] = "/dev/video0"
            break

    # Convert the modified simple graph to an advanced graph
    result = convert_to_advanced(
        http_client, pipeline_id, variant_id, modified_simple_graph
    )

    # Camera source should map to v4l2src in the advanced graph
    assert any(node.get("type") == "v4l2src" for node in result.get("nodes", [])), (
        "Expected v4l2src node in advanced graph after converting camera source"
    )


@pytest.mark.smoke
def test_get_nonexistent_pipeline_returns_404(http_client: requests.Session) -> None:
    """Calls GET /pipelines/{id} with a random non-existent ID and asserts 404."""
    nonexistent_id = f"does-not-exist-{uuid4().hex[:8]}"
    response = http_client.get(f"{BASE_URL}/pipelines/{nonexistent_id}", timeout=30)

    assert response.status_code == 404, (
        f"Expected 404 for non-existent pipeline, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_create_variant_for_nonexistent_pipeline_returns_404(
    http_client: requests.Session,
) -> None:
    """Calls POST /pipelines/{id}/variants with a non-existent pipeline ID and asserts 404."""
    nonexistent_id = f"does-not-exist-{uuid4().hex[:8]}"
    response = http_client.post(
        f"{BASE_URL}/pipelines/{nonexistent_id}/variants",
        json={
            "name": "CPU",
            "pipeline_graph": _graph_dict(),
            "pipeline_graph_simple": _graph_dict(),
        },
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for variant creation on non-existent pipeline, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_delete_user_created_variant_succeeds(
    http_client: requests.Session, created_pipeline_ids: list[str]
) -> None:
    """Creates a pipeline with two variants, deletes one, and asserts it no longer appears in GET response."""
    unique_name = f"functional-pipeline-del-variant-{uuid4().hex[:8]}"
    create_payload = {
        "name": unique_name,
        "description": "Pipeline for variant deletion test",
        "tags": ["functional"],
        "variants": [
            {
                "name": "CPU",
                "pipeline_graph": _graph_dict(),
                "pipeline_graph_simple": _graph_dict(),
            },
            {
                "name": "GPU",
                "pipeline_graph": _graph_dict(),
                "pipeline_graph_simple": _graph_dict(),
            },
        ],
    }
    create_response = http_client.post(
        f"{BASE_URL}/pipelines", json=create_payload, timeout=30
    )
    assert create_response.status_code == 201
    pipeline_id = create_response.json()["id"]
    created_pipeline_ids.append(pipeline_id)

    get_response = http_client.get(f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30)
    assert get_response.status_code == 200
    variants = get_response.json()["variants"]
    assert len(variants) == 2
    variant_id_to_delete = variants[1]["id"]

    delete_response = http_client.delete(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id_to_delete}",
        timeout=30,
    )
    assert delete_response.status_code == 200, (
        f"Expected 200 deleting variant, "
        f"got {delete_response.status_code}, body={delete_response.text}"
    )

    get_after = http_client.get(f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30)
    remaining_ids = [v["id"] for v in get_after.json()["variants"]]
    assert variant_id_to_delete not in remaining_ids, (
        f"Deleted variant id={variant_id_to_delete} still present in pipeline"
    )


@pytest.mark.smoke
def test_delete_last_remaining_variant_returns_400(
    http_client: requests.Session, created_pipeline_ids: list[str]
) -> None:
    """Creates a pipeline with a single variant, attempts to delete it, and asserts 400."""
    unique_name = f"functional-pipeline-last-variant-{uuid4().hex[:8]}"
    create_payload = {
        "name": unique_name,
        "description": "Pipeline for last variant deletion test",
        "tags": ["functional"],
        "variants": [
            {
                "name": "CPU",
                "pipeline_graph": _graph_dict(),
                "pipeline_graph_simple": _graph_dict(),
            }
        ],
    }
    create_response = http_client.post(
        f"{BASE_URL}/pipelines", json=create_payload, timeout=30
    )
    assert create_response.status_code == 201
    pipeline_id = create_response.json()["id"]
    created_pipeline_ids.append(pipeline_id)

    get_response = http_client.get(f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30)
    variant_id = get_response.json()["variants"][0]["id"]

    delete_response = http_client.delete(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}",
        timeout=30,
    )
    assert delete_response.status_code == 400, (
        f"Expected 400 when deleting last variant, "
        f"got {delete_response.status_code}, body={delete_response.text}"
    )


@pytest.mark.smoke
def test_delete_nonexistent_variant_returns_404(
    http_client: requests.Session, created_pipeline_ids: list[str]
) -> None:
    """Calls DELETE /pipelines/{id}/variants/{id} with a valid pipeline but non-existent variant ID and asserts 404."""
    unique_name = f"functional-pipeline-no-variant-{uuid4().hex[:8]}"
    create_payload = {
        "name": unique_name,
        "description": "Pipeline for nonexistent variant deletion test",
        "tags": ["functional"],
        "variants": [
            {
                "name": "CPU",
                "pipeline_graph": _graph_dict(),
                "pipeline_graph_simple": _graph_dict(),
            }
        ],
    }
    create_response = http_client.post(
        f"{BASE_URL}/pipelines", json=create_payload, timeout=30
    )
    assert create_response.status_code == 201
    pipeline_id = create_response.json()["id"]
    created_pipeline_ids.append(pipeline_id)

    nonexistent_variant_id = f"does-not-exist-{uuid4().hex[:8]}"
    delete_response = http_client.delete(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{nonexistent_variant_id}",
        timeout=30,
    )
    assert delete_response.status_code == 404, (
        f"Expected 404 for non-existent variant, "
        f"got {delete_response.status_code}, body={delete_response.text}"
    )


@pytest.mark.smoke
def test_update_user_created_variant_name_succeeds(
    http_client: requests.Session, created_pipeline_ids: list[str]
) -> None:
    """Creates a pipeline, patches the variant name, and asserts 200 with the updated name."""
    unique_name = f"functional-pipeline-upd-variant-{uuid4().hex[:8]}"
    create_payload = {
        "name": unique_name,
        "description": "Pipeline for variant update test",
        "tags": ["functional"],
        "variants": [
            {
                "name": "CPU",
                "pipeline_graph": _graph_dict(),
                "pipeline_graph_simple": _graph_dict(),
            }
        ],
    }
    create_response = http_client.post(
        f"{BASE_URL}/pipelines", json=create_payload, timeout=30
    )
    assert create_response.status_code == 201
    pipeline_id = create_response.json()["id"]
    created_pipeline_ids.append(pipeline_id)

    get_response = http_client.get(f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30)
    variant_id = get_response.json()["variants"][0]["id"]
    new_variant_name = "CPU-UPDATED"

    patch_response = http_client.patch(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}",
        json={"name": new_variant_name},
        timeout=30,
    )
    assert patch_response.status_code == 200, (
        f"Expected 200 updating variant name, "
        f"got {patch_response.status_code}, body={patch_response.text}"
    )
    assert patch_response.json().get("name") == new_variant_name, (
        f"Expected variant name={new_variant_name!r}, got {patch_response.json().get('name')!r}"
    )


@pytest.mark.smoke
def test_update_variant_with_empty_name_returns_422(
    http_client: requests.Session, created_pipeline_ids: list[str]
) -> None:
    """Calls PATCH /pipelines/{id}/variants/{id} with an empty name and asserts 422."""
    unique_name = f"functional-pipeline-empty-variant-name-{uuid4().hex[:8]}"
    create_payload = {
        "name": unique_name,
        "description": "Pipeline for empty variant name test",
        "tags": ["functional"],
        "variants": [
            {
                "name": "CPU",
                "pipeline_graph": _graph_dict(),
                "pipeline_graph_simple": _graph_dict(),
            }
        ],
    }
    create_response = http_client.post(
        f"{BASE_URL}/pipelines", json=create_payload, timeout=30
    )
    assert create_response.status_code == 201
    pipeline_id = create_response.json()["id"]
    created_pipeline_ids.append(pipeline_id)

    get_response = http_client.get(f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30)
    variant_id = get_response.json()["variants"][0]["id"]

    patch_response = http_client.patch(
        f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}",
        json={"name": ""},
        timeout=30,
    )
    assert patch_response.status_code == 422, (
        f"Expected 422 for empty variant name, "
        f"got {patch_response.status_code}, body={patch_response.text}"
    )


@pytest.mark.smoke
def test_optimize_variant_for_nonexistent_pipeline_returns_404(
    http_client: requests.Session,
) -> None:
    """Calls POST /pipelines/{id}/variants/{id}/optimize with a non-existent pipeline ID and asserts 404."""
    nonexistent_pipeline_id = f"does-not-exist-{uuid4().hex[:8]}"
    response = http_client.post(
        f"{BASE_URL}/pipelines/{nonexistent_pipeline_id}/variants/cpu/optimize",
        json={
            "type": "preprocess",
            "parameters": {"search_duration": 5, "sample_duration": 2},
        },
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for optimize on non-existent pipeline, "
        f"got {response.status_code}, body={response.text}"
    )
