# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import httpx
import pytest
import respx

from src.config import NodeConfig
from src.scheduler import FederationScheduler, NoCapacityError


@pytest.fixture
def scheduler(two_nodes):
    client = httpx.AsyncClient()
    sched = FederationScheduler(two_nodes, client)
    yield sched


class TestCompositeId:
    def test_make(self):
        assert FederationScheduler.make_composite_id("node-1", "42") == "node-1:42"

    def test_resolve(self):
        node_id, inst_id = FederationScheduler.resolve_composite_id("node-1:42")
        assert node_id == "node-1"
        assert inst_id == "42"

    def test_resolve_preserves_colons_in_instance_id(self):
        node_id, inst_id = FederationScheduler.resolve_composite_id("n:a:b:c")
        assert node_id == "n"
        assert inst_id == "a:b:c"

    def test_resolve_invalid(self):
        with pytest.raises(ValueError, match="Invalid composite"):
            FederationScheduler.resolve_composite_id("no-colon-here")


class TestInstanceMap:
    def test_register_and_unregister(self, scheduler):
        scheduler.register_instance("node-1:42", "node-1")
        assert scheduler.instance_map["node-1:42"] == "node-1"

        scheduler.unregister_instance("node-1:42")
        assert "node-1:42" not in scheduler.instance_map

    def test_unregister_missing_is_noop(self, scheduler):
        scheduler.unregister_instance("nonexistent")


@pytest.mark.asyncio
class TestSelectNode:
    @respx.mock
    async def test_selects_least_loaded(self, scheduler):
        respx.get("http://node1:8080/pipelines/status").respond(
            json=[{"state": "RUNNING"}, {"state": "RUNNING"}]
        )
        respx.get("http://node2:8080/pipelines/status").respond(json=[])

        node = await scheduler.select_node()
        assert node.id == "node-2"

    @respx.mock
    async def test_selects_by_utilization_ratio(self, two_nodes):
        two_nodes[0].max_pipelines = 100
        two_nodes[1].max_pipelines = 10
        client = httpx.AsyncClient()
        sched = FederationScheduler(two_nodes, client)

        # node-1: 5/100 = 5%, node-2: 1/10 = 10% → node-1 wins
        respx.get("http://node1:8080/pipelines/status").respond(
            json=[{"state": "RUNNING"}] * 5
        )
        respx.get("http://node2:8080/pipelines/status").respond(
            json=[{"state": "RUNNING"}]
        )

        node = await sched.select_node()
        assert node.id == "node-1"

    @respx.mock
    async def test_skips_unreachable_nodes(self, scheduler):
        respx.get("http://node1:8080/pipelines/status").mock(
            side_effect=httpx.ConnectError("refused")
        )
        respx.get("http://node2:8080/pipelines/status").respond(
            json=[{"state": "RUNNING"}]
        )

        node = await scheduler.select_node()
        assert node.id == "node-2"

    @respx.mock
    async def test_no_healthy_nodes_raises(self, scheduler):
        respx.get("http://node1:8080/pipelines/status").mock(
            side_effect=httpx.ConnectError("refused")
        )
        respx.get("http://node2:8080/pipelines/status").mock(
            side_effect=httpx.ConnectError("refused")
        )

        with pytest.raises(NoCapacityError):
            await scheduler.select_node()

    @respx.mock
    async def test_skips_full_nodes(self, two_nodes):
        two_nodes[0].max_pipelines = 2
        two_nodes[1].max_pipelines = 50
        client = httpx.AsyncClient()
        sched = FederationScheduler(two_nodes, client)

        # node-1 at capacity (2/2), node-2 has room
        respx.get("http://node1:8080/pipelines/status").respond(
            json=[{"state": "RUNNING"}, {"state": "RUNNING"}]
        )
        respx.get("http://node2:8080/pipelines/status").respond(json=[])

        node = await sched.select_node()
        assert node.id == "node-2"
