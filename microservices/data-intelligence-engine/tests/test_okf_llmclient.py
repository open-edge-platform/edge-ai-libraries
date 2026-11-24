# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from okf_extractor.llmclient import parse_json


def test_parse_json_ignores_fences_and_complete_reasoning_blocks():
    response = '<think>\n{"draft": true}\n</think>\n```json\n{"result": 42}\n```'
    assert parse_json(response) == {"result": 42}


def test_parse_json_keeps_content_after_unclosed_reasoning_marker():
    assert parse_json('<think>\n{"result": 42}') == {"result": 42}


def test_parse_json_rejects_response_with_no_object():
    with pytest.raises(ValueError, match="no JSON object found"):
        parse_json("<think>draft</think>\n```json\n```")
