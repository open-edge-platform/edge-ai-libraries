"""Functional tests for the /pipeline-templates endpoints."""

import logging
from uuid import uuid4

import pytest
import requests

from helpers.api_helpers import fetch_pipeline_templates
from helpers.config import BASE_URL

logger = logging.getLogger(__name__)


def _find_any_template(session: requests.Session) -> dict:
    templates = fetch_pipeline_templates(session)
    if not templates:
        pytest.skip("No pipeline templates available in current environment")
    return templates[0]


@pytest.mark.smoke
def test_get_pipeline_templates_returns_list(http_client: requests.Session) -> None:
    """Calls GET /pipeline-templates and asserts the response is 200 with a list."""
    response = http_client.get(f"{BASE_URL}/pipeline-templates", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /pipeline-templates, "
        f"got {response.status_code}, body={response.text}"
    )
    assert isinstance(response.json(), list), (
        "Pipeline templates response must be a list"
    )
    logger.info(
        "Pipeline templates endpoint returned %d template(s)", len(response.json())
    )


@pytest.mark.smoke
def test_pipeline_templates_have_source_template(
    http_client: requests.Session,
) -> None:
    """Asserts every object returned by GET /pipeline-templates has source=TEMPLATE."""
    templates = fetch_pipeline_templates(http_client)

    if not templates:
        pytest.skip("No pipeline templates available in current environment")

    for template in templates:
        assert template.get("source") == "TEMPLATE", (
            f"Expected source=TEMPLATE for template id={template.get('id')!r}, "
            f"got {template.get('source')!r}"
        )


@pytest.mark.smoke
def test_pipeline_template_variants_are_read_only(
    http_client: requests.Session,
) -> None:
    """Asserts that all variants in every template returned by GET /pipeline-templates have read_only=True."""
    templates = fetch_pipeline_templates(http_client)

    if not templates:
        pytest.skip("No pipeline templates available in current environment")

    for template in templates:
        variants = template.get("variants", [])
        assert variants, f"Template id={template.get('id')!r} has no variants"
        for variant in variants:
            assert variant.get("read_only") is True, (
                f"Expected read_only=True for template variant id={variant.get('id')!r} "
                f"in template id={template.get('id')!r}"
            )


@pytest.mark.smoke
def test_get_pipeline_template_by_id_returns_correct_template(
    http_client: requests.Session,
) -> None:
    """Fetches the first template and calls GET /pipeline-templates/{id} to assert the IDs match."""
    first_template = _find_any_template(http_client)
    template_id = first_template["id"]

    response = http_client.get(
        f"{BASE_URL}/pipeline-templates/{template_id}", timeout=30
    )

    assert response.status_code == 200, (
        f"Expected 200 for GET /pipeline-templates/{template_id}, "
        f"got {response.status_code}, body={response.text}"
    )
    assert response.json().get("id") == template_id, (
        f"Returned template id does not match requested id={template_id!r}"
    )


@pytest.mark.smoke
def test_get_pipeline_template_by_nonexistent_id_returns_404(
    http_client: requests.Session,
) -> None:
    """Calls GET /pipeline-templates/{id} with a random non-existent ID and asserts the response is 404."""
    nonexistent_id = f"does-not-exist-{uuid4().hex[:8]}"
    response = http_client.get(
        f"{BASE_URL}/pipeline-templates/{nonexistent_id}", timeout=30
    )

    assert response.status_code == 404, (
        f"Expected 404 for non-existent template id={nonexistent_id!r}, "
        f"got {response.status_code}, body={response.text}"
    )
