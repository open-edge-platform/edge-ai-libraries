# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging

import httpx

from .config import NodeConfig

logger = logging.getLogger(__name__)


class NoCapacityError(Exception):
    """Raised when no healthy nodes have available capacity."""


class FederationScheduler:
    """Capacity-aware least-loaded scheduling across federated DLS-PS nodes."""

    def __init__(self, nodes: list[NodeConfig], client: httpx.AsyncClient):
        self.nodes: dict[str, NodeConfig] = {n.id: n for n in nodes}
        self.instance_map: dict[str, str] = {}
        self._client = client

    async def select_node(self) -> NodeConfig:
        """Pick the node with the most remaining capacity."""
        tasks = [self._get_node_load(n) for n in self.nodes.values()]
        results = await asyncio.gather(*tasks)

        healthy = [
            (node, load)
            for node, load in zip(self.nodes.values(), results)
            if load is not None and load < node.max_pipelines
        ]
        if not healthy:
            raise NoCapacityError("No healthy nodes with available capacity")

        healthy.sort(key=lambda nl: nl[1] / nl[0].max_pipelines)
        return healthy[0][0]

    async def _get_node_load(self, node: NodeConfig) -> int | None:
        try:
            resp = await self._client.get(f"{node.url}/pipelines/status")
            resp.raise_for_status()
            statuses = resp.json()
            return sum(1 for s in statuses if s.get("state") == "RUNNING")
        except Exception:
            logger.debug("Node %s unreachable for load query", node.id)
            return None

    def register_instance(self, composite_id: str, node_id: str) -> None:
        self.instance_map[composite_id] = node_id

    def unregister_instance(self, composite_id: str) -> None:
        self.instance_map.pop(composite_id, None)

    @staticmethod
    def make_composite_id(node_id: str, instance_id: str) -> str:
        return f"{node_id}:{instance_id}"

    @staticmethod
    def resolve_composite_id(composite_id: str) -> tuple[str, str]:
        parts = composite_id.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid composite instance ID: {composite_id}")
        return parts[0], parts[1]
