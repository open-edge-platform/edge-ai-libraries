# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for call-flow logging: one line per call, tagged and redacted."""

from __future__ import annotations

import logging

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from src.call_log import safe_args
from src.core.logging import CallIdFilter, current_call_id
from tests.fakes import FakeVss, make_mcp, make_stream

pytestmark = pytest.mark.anyio


def test_safe_args_masks_credentials_and_shortens_bulk() -> None:
    args = {
        "url": "rtsp://admin:secret@10.0.0.5:554/cam",
        "image": "data:image/jpeg;base64," + "A" * 5000,
        "query": "x" * 500,
        "stream_ids": [str(n) for n in range(25)],
        "limit": 5,
        "note": "see https://bob:pw@example.com/x",
    }

    safe = safe_args(args)

    assert "secret" not in str(safe)
    assert safe["url"] == "rtsp://***@10.0.0.5:554/cam"
    assert safe["image"].startswith("<data:image/jpeg;base64,...")
    assert len(safe["query"]) < 300
    assert safe["stream_ids"][-1] == "... 5 more"
    assert safe["limit"] == 5
    assert safe["note"] == "see https://***@example.com/x"


def test_call_id_filter_tags_only_inside_a_call() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "m", None, None)
    CallIdFilter().filter(record)
    assert record.call_tag == ""

    token = current_call_id.set("abcd1234")
    try:
        CallIdFilter().filter(record)
    finally:
        current_call_id.reset(token)
    assert record.call_tag == "[abcd1234] "


async def test_tool_call_logs_its_flow_under_one_call_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeVss()
    fake.streams = [make_stream("cam-1")]
    caplog.set_level(logging.DEBUG)
    caplog.handler.addFilter(CallIdFilter())

    async with Client(make_mcp(fake=fake)) as client:
        await client.call_tool("vss_list_streams", {"state": "running"})

    calls = [r for r in caplog.records if r.name == "vss_mcp.calls"]
    requests = [r for r in caplog.records if r.name == "src.clients.vss"]
    assert [r.getMessage() for r in calls][0] == (
        "tool vss_list_streams called with {'state': 'running'}"
    )
    assert calls[-1].getMessage().startswith("tool vss_list_streams ok in ")
    assert any("GET /streams -> 200" in r.getMessage() for r in requests)
    tags = {r.call_tag for r in calls + requests}
    assert len(tags) == 1 and tags != {""}


async def test_failed_tool_call_is_logged_without_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    async with Client(make_mcp(fake=FakeVss())) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "vss_add_stream", {"url": "http://user:pw@cam/x"}  # not a parameter
            )

    lines = [r.getMessage() for r in caplog.records if r.name == "vss_mcp.calls"]
    assert any(line.startswith("tool vss_add_stream failed in ") for line in lines)
    assert "pw@" not in caplog.text
