# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from src.config import NodeConfig
from src.health import HealthMonitor


@pytest.fixture
def monitor(two_nodes):
    return HealthMonitor(two_nodes, interval=1, request_timeout=1.0)


@pytest.mark.asyncio
class TestHealthCheck:
    @respx.mock
    async def test_healthy_node(self, monitor):
        respx.get("http://node1:8080/pipelines").respond(json=[], status_code=200)
        result = await monitor._check_health(monitor.nodes["node-1"])
        assert result is True

    @respx.mock
    async def test_unhealthy_on_error_status(self, monitor):
        respx.get("http://node1:8080/pipelines").respond(status_code=500)
        result = await monitor._check_health(monitor.nodes["node-1"])
        assert result is False

    @respx.mock
    async def test_unhealthy_on_connection_error(self, monitor):
        respx.get("http://node1:8080/pipelines").mock(
            side_effect=httpx.ConnectError("refused")
        )
        result = await monitor._check_health(monitor.nodes["node-1"])
        assert result is False


@pytest.mark.asyncio
class TestHealthMonitorLifecycle:
    async def test_start_and_stop(self, monitor):
        with patch.object(monitor, "_check_health", new_callable=AsyncMock, return_value=True):
            monitor.start()
            await asyncio.sleep(0.1)
            assert monitor._task is not None
            await monitor.stop()
            assert monitor._task.cancelled() or monitor._task.done()


@pytest.mark.asyncio
class TestRestart:
    async def test_restart_skipped_without_ssh(self, monitor):
        node = NodeConfig(id="local", url="http://localhost:8080", ssh=None)
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            await monitor._restart_node(node)
            mock_exec.assert_not_called()

    async def test_restart_called_with_ssh(self, two_nodes):
        two_nodes[0].ssh = "user@host"
        monitor = HealthMonitor(two_nodes, interval=1)

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await monitor._restart_node(two_nodes[0])
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args[0]
            assert call_args[0] == "ssh"
            assert "user@host" in call_args
