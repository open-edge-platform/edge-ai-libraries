"""Functional tests for the /convert endpoints."""

import logging

import pytest
import requests

from helpers.config import BASE_URL
from helpers.api_helpers import JsonDict

logger = logging.getLogger(__name__)

_SIMPLE_DESCRIPTION = "videotestsrc ! videoconvert ! fakesink"

_SIMPLE_GRAPH: JsonDict = {
    "nodes": [
        {"id": "0", "type": "videotestsrc", "data": {}},
        {"id": "1", "type": "videoconvert", "data": {}},
        {"id": "2", "type": "fakesink", "data": {}},
    ],
    "edges": [
        {"id": "0", "source": "0", "target": "1"},
        {"id": "1", "source": "1", "target": "2"},
    ],
}

_EMPTY_GRAPH: JsonDict = {"nodes": [], "edges": []}


@pytest.mark.smoke
def test_convert_valid_pipeline_description_to_graph(
    http_client: requests.Session,
) -> None:
    """Posts a simple GStreamer description to POST /convert/to-graph and asserts 200 with non-empty nodes and edges."""
    response = http_client.post(
        f"{BASE_URL}/convert/to-graph",
        json={"pipeline_description": _SIMPLE_DESCRIPTION},
        timeout=30,
    )

    assert response.status_code == 200, (
        f"Expected 200 from /convert/to-graph, "
        f"got {response.status_code}, body={response.text}"
    )
    payload = response.json()
    assert isinstance(payload, dict), "Convert response must be an object"
    pipeline_graph = payload.get("pipeline_graph", {})
    pipeline_graph_simple = payload.get("pipeline_graph_simple", {})

    assert pipeline_graph.get("nodes"), "pipeline_graph must have non-empty nodes"
    assert pipeline_graph.get("edges") is not None, "pipeline_graph must have edges key"
    assert pipeline_graph_simple.get("nodes"), (
        "pipeline_graph_simple must have non-empty nodes"
    )
    logger.info(
        "Converted description to graph: %d nodes in advanced view, %d in simple view",
        len(pipeline_graph.get("nodes", [])),
        len(pipeline_graph_simple.get("nodes", [])),
    )


@pytest.mark.smoke
def test_convert_invalid_pipeline_description_returns_400(
    http_client: requests.Session,
) -> None:
    """Posts a syntactically invalid description to POST /convert/to-graph and asserts 400."""
    response = http_client.post(
        f"{BASE_URL}/convert/to-graph",
        json={
            "pipeline_description": "video/x-raw,width="
        },  # Invalid caps property without value
        timeout=30,
    )

    assert response.status_code == 400, (
        f"Expected 400 for invalid pipeline description, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_convert_valid_pipeline_graph_to_description(
    http_client: requests.Session,
) -> None:
    """Posts a valid pipeline graph to POST /convert/to-description and asserts 200 with a non-empty string."""
    response = http_client.post(
        f"{BASE_URL}/convert/to-description",
        json=_SIMPLE_GRAPH,
        timeout=30,
    )

    assert response.status_code == 200, (
        f"Expected 200 from /convert/to-description, "
        f"got {response.status_code}, body={response.text}"
    )
    payload = response.json()
    description = payload.get("pipeline_description", "")
    assert isinstance(description, str) and description.strip(), (
        f"Expected a non-empty pipeline_description string, got {description!r}"
    )
    logger.info("Converted graph to description: %s", description)


@pytest.mark.smoke
def test_convert_empty_graph_to_description_returns_400(
    http_client: requests.Session,
) -> None:
    """Posts an empty nodes/edges graph to POST /convert/to-description and asserts 400."""
    response = http_client.post(
        f"{BASE_URL}/convert/to-description",
        json=_EMPTY_GRAPH,
        timeout=30,
    )

    assert response.status_code == 400, (
        f"Expected 400 for empty graph, "
        f"got {response.status_code}, body={response.text}"
    )
