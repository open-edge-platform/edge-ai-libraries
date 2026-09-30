# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for baseline token accounting."""

import pytest

# These tests require the optional `adaptive-token-compressor` library. When it
# is not installed, the whole module is skipped at collection time (instead of
# erroring on the imports below).
pytest.importorskip("adaptive_token_compressor")

pytestmark = pytest.mark.compressor

from adaptive_token_compressor.core.messages import HARNESS_LIKE_ROLES
from adaptive_token_compressor.core.metrics import (
    count_messages_tokens,
    count_tools_tokens,
)

from src.models import ChatCompletionMessage, ChatCompletionRequest
from src.observability.token_accounting import (
    HARNESS_LIKE_ROLES as LOCAL_HARNESS_LIKE_ROLES,
    compute_token_breakdown,
    count_messages_tokens as local_count_messages_tokens,
    count_tools_tokens as local_count_tools_tokens,
)


def _request(messages=None, tools=None):
    return ChatCompletionRequest(
        model="m",
        messages=messages
        or [
            ChatCompletionMessage(role="system", content="System instructions here, fairly long."),
            ChatCompletionMessage(role="user", content="What is 2+2?"),
            ChatCompletionMessage(role="assistant", content="4"),
        ],
        tools=tools,
    )


def test_breakdown_sums_to_overall():
    b = compute_token_breakdown(_request(tools=[
        {"type": "function", "function": {"name": "read", "description": "Read a file"}},
    ]))
    assert b.overall == b.system + b.tool + b.context
    assert b.system > 0 and b.tool > 0 and b.context > 0


def test_matches_compressor_counters():
    """Baseline must use the same library counters the compressors use."""
    msgs = [
        {"role": "system", "content": "System instructions here, fairly long."},
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "4"},
    ]
    tools = [{"type": "function", "function": {"name": "read", "description": "Read a file"}}]
    b = compute_token_breakdown(_request(tools=tools))

    # system == what harness compressor measures as tokens_before
    assert b.system == count_messages_tokens(msgs, roles=HARNESS_LIKE_ROLES)
    # tool == what tool compressor measures as tokens_before
    assert b.tool == count_tools_tokens(tools)
    # context == everything minus system
    assert b.context == count_messages_tokens(msgs) - b.system


def test_no_tools_zero_tool_tokens():
    b = compute_token_breakdown(_request(tools=None))
    assert b.tool == 0
    assert b.overall == b.system + b.context


def test_tool_role_message_counts_as_context():
    """role:tool (tool result) is context, not tool-schema."""
    b = compute_token_breakdown(_request(messages=[
        ChatCompletionMessage(role="system", content="System preamble text here."),
        ChatCompletionMessage(role="user", content="run it"),
        ChatCompletionMessage(role="tool", content="tool output result", tool_call_id="c1"),
    ]))
    assert b.system > 0
    assert b.context > 0       # user + tool-result message
    assert b.tool == 0         # no request.tools schema


@pytest.mark.parametrize(
    ("messages", "tools"),
    [
        ([], None),
        ([{"role": "system", "content": ""}], None),
        ([{"role": "system", "content": "  a  "}], []),
        ([{"role": "system", "content": ["x", {"text": "y"}, {"content": "z"}]}], None),
        ([{"role": "assistant", "content": "hello"}], None),
        ([{"role": "assistant", "content": "hello", "tool_calls": []}], None),
        ([{"role": "assistant", "content": "hello", "tool_calls": [
            {"id": "1", "type": "function", "function": {"name": "f", "arguments": '{"x":1}'}}
        ]}], None),
        ([{"role": "user", "content": "u"}, {"role": "system", "content": "s"}, {"role": "assistant", "content": "a"}], None),
        ([{"role": "tool", "content": "result"}], None),
        ([{"role": "system", "content": None}, {"role": "assistant", "content": None, "tool_calls": [
            {"id": "1", "type": "function", "function": {"name": "f", "arguments": '{"x":1, "y":2}'}}
        ]}], None),
    ],
)
def test_local_parity_matches_vendored_token_counters(messages, tools):
    """Local copies of the token counters must stay byte-for-byte aligned with vendor."""
    assert LOCAL_HARNESS_LIKE_ROLES == HARNESS_LIKE_ROLES

    assert local_count_messages_tokens(messages, roles=LOCAL_HARNESS_LIKE_ROLES) == (
        count_messages_tokens(messages, roles=HARNESS_LIKE_ROLES)
    )
    assert local_count_messages_tokens(messages) == count_messages_tokens(messages)
    assert local_count_tools_tokens(tools) == count_tools_tokens(tools)