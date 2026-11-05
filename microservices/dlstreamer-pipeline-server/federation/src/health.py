# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging

import httpx

from .config import NodeConfig

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Polls node health and optionally restarts unhealthy nodes via SSH."""

    def __init__(
        self,
        nodes: list[NodeConfig],
        interval: int = 10,
        request_timeout: float = 3.0,
    ):
        self.nodes: dict[str, NodeConfig] = {n.id: n for n in nodes}
        self.interval = interval
        self.node_healthy: dict[str, bool] = {n.id: True for n in nodes}
        self._client = httpx.AsyncClient(timeout=request_timeout)
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()

    async def _monitor_loop(self) -> None:
        while True:
            for node in self.nodes.values():
                healthy = await self._check_health(node)
                prev = self.node_healthy.get(node.id, True)
                self.node_healthy[node.id] = healthy

                if not healthy and prev:
                    logger.warning("Node %s became unhealthy", node.id)
                    if node.ssh:
                        await self._restart_node(node)
                elif healthy and not prev:
                    logger.info("Node %s recovered", node.id)

            await asyncio.sleep(self.interval)

    async def _check_health(self, node: NodeConfig) -> bool:
        try:
            resp = await self._client.get(f"{node.url}/pipelines")
            return resp.status_code == 200
        except Exception:
            return False

    async def _restart_node(self, node: NodeConfig) -> None:
        if not node.ssh:
            return
        logger.info("Attempting restart of DLS-PS on %s via SSH", node.id)
        remote_cmd = "docker compose restart dlstreamer-pipeline-server"
        try:
            proc = await asyncio.create_subprocess_exec(
                "ssh",
                "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=accept-new",
                node.ssh,
                remote_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error(
                    "Restart failed for %s (rc=%d): %s",
                    node.id,
                    proc.returncode,
                    stderr.decode().strip(),
                )
            else:
                logger.info("Restart command sent to %s", node.id)
        except OSError as exc:
            logger.error("Could not execute SSH for %s: %s", node.id, exc)
