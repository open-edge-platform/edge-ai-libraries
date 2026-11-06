# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for scripts/line_protocol.py (tag-value escaping shared by the readers)."""

import pytest


@pytest.mark.parametrize(
    "raw, escaped",
    [
        ("plain-host", "plain-host"),
        ("rack 1", r"rack\ 1"),
        ("a,b", r"a\,b"),
        ("a=b", r"a\=b"),
        ("rack 1,node=a", r"rack\ 1\,node\=a"),
        ("", ""),
    ],
)
def test_escape_tag_value(load_reader, raw, escaped):
    module = load_reader("line_protocol", "UNUSED_LOG_ENV")
    assert module.escape_tag_value(raw) == escaped


@pytest.mark.parametrize(
    "script, log_env",
    [
        ("rapl_reader", "RAPL_READER_LOG_FILE"),
        ("dram_bw_reader", "DRAM_BW_READER_LOG_FILE"),
        ("gpu_throttle_reader", "GPU_THROTTLE_READER_LOG_FILE"),
    ],
)
def test_readers_escape_a_hostile_hostname(load_reader, monkeypatch, script, log_env):
    # A hostname with ',' / '=' / ' ' would otherwise split the tag set.
    monkeypatch.setenv("METRICS_MANAGER_HOSTNAME", "rack 1,node=a")
    reader = load_reader(script, log_env)
    assert reader.HOST_TAG == r"rack\ 1\,node\=a"
