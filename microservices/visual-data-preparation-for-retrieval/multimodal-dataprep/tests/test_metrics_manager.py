# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the non-blocking Metrics Manager publisher."""

import asyncio
import json

import httpx
import pytest

from src.core.embedding.embedding_orchestrator import _record_pipeline
from src.core.metrics_manager import METRIC_NAME, METRIC_TAGS, MetricsManagerPublisher


@pytest.mark.asyncio
async def test_publish_posts_expected_simple_metric():
    received = []
    request_received = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        request_received.set()
        return httpx.Response(202, json={"accepted": 1})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = MetricsManagerPublisher("http://metrics-manager:9090/", 0.5, client=client)
    await publisher.start()

    assert publisher.publish(12.5, 1_774_963_430.25)
    await asyncio.wait_for(request_received.wait(), timeout=1)
    await publisher.stop()
    await client.aclose()

    assert received[0].url == "http://metrics-manager:9090/api/v1/metrics/simple"
    assert received[0].read()
    assert received[0].content

    payload = json.loads(received[0].content)
    assert payload == {
        "name": METRIC_NAME,
        "value": 12.5,
        "timestamp": 1_774_963_430.25,
        "tags": METRIC_TAGS,
    }


@pytest.mark.asyncio
async def test_empty_url_disables_publisher():
    publisher = MetricsManagerPublisher("", 0.5)
    await publisher.start()

    assert publisher.enabled is False
    assert publisher.publish(1.0, 1.0) is False
    await publisher.stop()


@pytest.mark.asyncio
async def test_latest_value_supersedes_failed_retry():
    values = []
    first_attempt = asyncio.Event()
    replacement_received = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        value = json.loads(request.content)["value"]
        values.append(value)
        if len(values) == 1:
            first_attempt.set()
            raise httpx.ConnectError("offline", request=request)
        replacement_received.set()
        return httpx.Response(202)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = MetricsManagerPublisher(
        "http://metrics-manager:9090",
        0.5,
        client=client,
        initial_retry_seconds=1,
    )
    await publisher.start()

    assert publisher.publish(1.0, 1.0)
    await asyncio.wait_for(first_attempt.wait(), timeout=1)
    assert publisher.publish(2.0, 2.0)
    assert publisher.publish(3.0, 3.0)
    await asyncio.wait_for(replacement_received.wait(), timeout=1)
    await publisher.stop()
    await client.aclose()

    assert values == [1.0, 3.0]


@pytest.mark.asyncio
async def test_invalid_values_are_ignored():
    publisher = MetricsManagerPublisher("http://metrics-manager:9090", 0.5)
    await publisher.start()

    assert publisher.publish(-1, 1) is False
    assert publisher.publish(float("nan"), 1) is False
    assert publisher.publish(float("inf"), 1) is False
    assert publisher.publish(1, float("nan")) is False
    assert publisher.publish("invalid", 1) is False
    await publisher.stop()


@pytest.mark.asyncio
async def test_shutdown_cancels_an_inflight_request():
    request_started = asyncio.Event()
    never_complete = asyncio.Event()

    async def handler(_request: httpx.Request) -> httpx.Response:
        request_started.set()
        await never_complete.wait()
        return httpx.Response(202)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = MetricsManagerPublisher("http://metrics-manager:9090", 0.5, client=client)
    await publisher.start()
    assert publisher.publish(1, 1)
    await asyncio.wait_for(request_started.wait(), timeout=1)

    await asyncio.wait_for(publisher.stop(), timeout=1)
    await client.aclose()


def test_completed_telemetry_record_is_enqueued(mocker):
    record = mocker.MagicMock()
    record.stage_throughput = {"embeddings_throughput": 17.25}
    mocker.patch(
        "src.core.embedding.embedding_orchestrator.record_video_telemetry",
        return_value=record,
    )
    mocker.patch("src.core.embedding.embedding_orchestrator._log_telemetry_record")
    publish = mocker.patch(
        "src.core.embedding.embedding_orchestrator.publish_embeddings_throughput"
    )

    context = {"requested_at": 1.0}
    _record_pipeline(
        context=context,
        bucket_name="bucket",
        video_id="video",
        filename="video.mp4",
        frame_interval=15,
        tags=[],
        enable_object_detection=False,
        detection_confidence=0.85,
        metadata_dict={},
        pipeline_result={"metrics": {"embed": {"throughput": 17.25}}},
    )

    publish.assert_called_once_with(17.25, context["completed_at"])
