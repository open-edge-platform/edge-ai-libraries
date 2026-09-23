# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient

from src.config import FederationConfig, NodeConfig
from src.proxy import create_app


@pytest.fixture
def app(config):
    return create_app(config)


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


PIPELINE_TEMPLATES = [
    {"name": "object_detection", "version": "1", "type": "GStreamer", "description": "Detect objects"},
    {"name": "face_detection", "version": "1", "type": "GStreamer", "description": "Detect faces"},
]


@pytest.mark.asyncio
class TestListPipelines:
    @respx.mock
    async def test_deduplicates_across_nodes(self, client):
        respx.get("http://node1:8080/pipelines").respond(json=PIPELINE_TEMPLATES)
        respx.get("http://node2:8080/pipelines").respond(json=PIPELINE_TEMPLATES)

        resp = await client.get("/pipelines")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @respx.mock
    async def test_handles_node_failure(self, client):
        respx.get("http://node1:8080/pipelines").respond(json=PIPELINE_TEMPLATES)
        respx.get("http://node2:8080/pipelines").mock(
            side_effect=httpx.ConnectError("down")
        )

        resp = await client.get("/pipelines")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


@pytest.mark.asyncio
class TestGetAllStatus:
    @respx.mock
    async def test_aggregates_with_composite_ids(self, client):
        respx.get("http://node1:8080/pipelines/status").respond(
            json=[{"id": 1, "state": "RUNNING", "avg_fps": 30}]
        )
        respx.get("http://node2:8080/pipelines/status").respond(
            json=[{"id": 5, "state": "RUNNING", "avg_fps": 25}]
        )

        resp = await client.get("/pipelines/status")
        assert resp.status_code == 200
        statuses = resp.json()
        assert len(statuses) == 2
        assert statuses[0]["id"] == "node-1:1"
        assert statuses[0]["node"] == "node-1"
        assert statuses[1]["id"] == "node-2:5"

    @respx.mock
    async def test_skips_failed_nodes(self, client):
        respx.get("http://node1:8080/pipelines/status").respond(
            json=[{"id": 1, "state": "RUNNING", "avg_fps": 30}]
        )
        respx.get("http://node2:8080/pipelines/status").respond(status_code=500)

        resp = await client.get("/pipelines/status")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


@pytest.mark.asyncio
class TestStartPipeline:
    @respx.mock
    async def test_schedules_to_least_loaded(self, client):
        # Scheduler queries: node-1 has 2 running, node-2 has 0
        respx.get("http://node1:8080/pipelines/status").respond(
            json=[{"state": "RUNNING"}, {"state": "RUNNING"}]
        )
        respx.get("http://node2:8080/pipelines/status").respond(json=[])
        # Start on node-2
        respx.post("http://node2:8080/pipelines/object_detection/1").respond(json=42)

        resp = await client.post(
            "/pipelines/object_detection/1",
            json={"source": {"type": "uri", "uri": "file:///video.mp4"}},
        )
        assert resp.status_code == 200
        assert resp.json() == "node-2:42"

    @respx.mock
    async def test_returns_503_when_no_capacity(self, client):
        respx.get("http://node1:8080/pipelines/status").mock(
            side_effect=httpx.ConnectError("down")
        )
        respx.get("http://node2:8080/pipelines/status").mock(
            side_effect=httpx.ConnectError("down")
        )

        resp = await client.post(
            "/pipelines/object_detection/1",
            json={"source": {"type": "uri", "uri": "file:///video.mp4"}},
        )
        assert resp.status_code == 503


@pytest.mark.asyncio
class TestInstanceRouting:
    @respx.mock
    async def test_get_instance_status(self, client):
        respx.get("http://node1:8080/pipelines/42/status").respond(
            json={"id": 42, "state": "RUNNING", "avg_fps": 30}
        )

        resp = await client.get("/pipelines/node-1:42/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "node-1:42"
        assert data["node"] == "node-1"
        assert data["state"] == "RUNNING"

    @respx.mock
    async def test_get_instance(self, client):
        respx.get("http://node2:8080/pipelines/7").respond(
            json={"id": 7, "type": "GStreamer", "request": {}}
        )

        resp = await client.get("/pipelines/node-2:7")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "node-2:7"
        assert data["node"] == "node-2"

    @respx.mock
    async def test_delete_instance(self, client):
        respx.delete("http://node1:8080/pipelines/42").respond(
            json={"state": "ABORTED"}, status_code=200
        )

        resp = await client.delete("/pipelines/node-1:42")
        assert resp.status_code == 200

    @respx.mock
    async def test_invalid_composite_id(self, client):
        resp = await client.get("/pipelines/badid/status")
        assert resp.status_code == 400

    @respx.mock
    async def test_unknown_node(self, client):
        resp = await client.get("/pipelines/unknown-node:42/status")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestListNodes:
    @respx.mock
    async def test_lists_all_nodes(self, client):
        # Health monitor hasn't run, so nodes default to healthy=True
        resp = await client.get("/nodes")
        assert resp.status_code == 200
        nodes = resp.json()
        assert len(nodes) == 2
        assert nodes[0]["id"] == "node-1"
        assert nodes[1]["id"] == "node-2"
