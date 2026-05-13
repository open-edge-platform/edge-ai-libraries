# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for app/sse.py — SSE endpoint and metrics fetching."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.sse import event_stream, fetch_metrics


async def _one_shot_stream():
    """Finite async generator for SSE endpoint tests — yields one frame then stops."""
    yield 'data: {"timestamp": 1234, "metrics": []}\n\n'


class TestMetricsStreamEndpoint:
    def test_stream_endpoint_returns_event_stream_content_type(self, client: TestClient):
        with patch("app.sse.event_stream", return_value=_one_shot_stream()):
            with client.stream("GET", "/metrics/stream") as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]

    def test_stream_endpoint_returns_html_when_accept_is_html(self, client: TestClient):
        response = client.get("/metrics/stream", headers={"Accept": "text/html"})
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Metrics Stream" in response.text


class TestFetchMetrics:
    @pytest.mark.asyncio
    async def test_fetch_returns_json_with_timestamp_and_metrics(self):
        # Prometheus text format uses milliseconds for timestamps.
        # 1777463430000 ms in the text → prometheus_client returns 1777463430.0 s
        # → sse.py converts back to ms: int(1777463430.0 * 1000) = 1777463430000
        prometheus_text = (
            '# HELP cpu_usage_user CPU usage\n'
            '# TYPE cpu_usage_user gauge\n'
            'cpu_usage_user{cpu="cpu-total"} 0.14 1777463430000\n'
        )
        mock_resp = MagicMock()
        mock_resp.text = prometheus_text
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.sse.httpx.AsyncClient", return_value=mock_client):
            result_str = await fetch_metrics()

        result = json.loads(result_str)
        assert "timestamp" in result
        assert "metrics" in result
        assert isinstance(result["metrics"], list)
        assert len(result["metrics"]) == 1
        m = result["metrics"][0]
        assert m["name"] == "cpu_usage_user"
        assert m["labels"] == {"cpu": "cpu-total"}
        assert m["value"] == pytest.approx(0.14)
        assert m["timestamp"] == 1777463430000

    @pytest.mark.asyncio
    async def test_fetch_metric_without_timestamp_uses_current_time(self):
        prometheus_text = 'fps{pipeline="obj"} 29.97\n'
        mock_resp = MagicMock()
        mock_resp.text = prometheus_text
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.sse.httpx.AsyncClient", return_value=mock_client):
            result_str = await fetch_metrics()

        result = json.loads(result_str)
        assert len(result["metrics"]) == 1
        m = result["metrics"][0]
        assert m["name"] == "fps"
        assert m["value"] == pytest.approx(29.97)
        # timestamp is current time in ms — should be a large number
        assert m["timestamp"] > 1_000_000_000_000

    @pytest.mark.asyncio
    async def test_fetch_empty_prometheus_response_returns_empty_list(self):
        mock_resp = MagicMock()
        mock_resp.text = "# HELP cpu CPU\n# TYPE cpu gauge\n"
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.sse.httpx.AsyncClient", return_value=mock_client):
            result_str = await fetch_metrics()

        result = json.loads(result_str)
        assert result["metrics"] == []

    @pytest.mark.asyncio
    async def test_fetch_metric_without_labels_has_empty_labels_dict(self):
        mock_resp = MagicMock()
        mock_resp.text = "fps 30.0 1777463430\n"
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.sse.httpx.AsyncClient", return_value=mock_client):
            result_str = await fetch_metrics()

        result = json.loads(result_str)
        assert result["metrics"][0]["labels"] == {}

    @pytest.mark.asyncio
    async def test_fetch_multiple_metrics_returned_as_list(self):
        prometheus_text = (
            'cpu_usage_user{cpu="cpu-total"} 0.14 1777463430\n'
            'gpu_engine_usage_usage{engine="compute",gpu_id="0"} 12.5 1777463430\n'
        )
        mock_resp = MagicMock()
        mock_resp.text = prometheus_text
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.sse.httpx.AsyncClient", return_value=mock_client):
            result_str = await fetch_metrics()

        result = json.loads(result_str)
        assert len(result["metrics"]) == 2
        names = {m["name"] for m in result["metrics"]}
        assert "cpu_usage_user" in names
        assert "gpu_engine_usage_usage" in names


class TestEventStream:
    @pytest.mark.asyncio
    async def test_event_stream_yields_data_frame(self):
        payload = json.dumps({"timestamp": 1234, "metrics": []})

        async def mock_fetch():
            return payload

        with patch("app.sse.fetch_metrics", side_effect=mock_fetch):
            with patch("app.sse.asyncio.sleep", new=AsyncMock()):
                gen = event_stream()
                frame = await gen.__anext__()
                await gen.aclose()

        assert frame.startswith("data: ")
        assert frame.endswith("\n\n")
        inner = json.loads(frame[len("data: "):-2])
        assert inner["timestamp"] == 1234

    @pytest.mark.asyncio
    async def test_event_stream_yields_error_frame_on_exception(self):
        async def mock_fetch():
            raise ConnectionError("refused")

        with patch("app.sse.fetch_metrics", side_effect=mock_fetch):
            with patch("app.sse.asyncio.sleep", new=AsyncMock()):
                gen = event_stream()
                frame = await gen.__anext__()
                await gen.aclose()

        assert frame.startswith("data: ")
        inner = json.loads(frame[len("data: "):-2])
        assert "error" in inner
        assert "refused" in inner["error"]
