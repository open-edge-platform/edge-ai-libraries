# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from src.common.logger import sanitize_for_log


def test_sanitize_for_log_escapes_newlines_and_carriage_returns():
    assert sanitize_for_log("line1\nline2\rline3") == "line1\\nline2\\rline3"


def test_sanitize_for_log_escapes_non_printable_characters():
    assert sanitize_for_log("ok\x01done") == "ok\\x01done"


def test_sanitize_for_log_applies_truncation():
    assert sanitize_for_log("1234567", max_length=5) == "12345...<truncated:2>"


def test_sanitize_for_log_handles_none():
    assert sanitize_for_log(None) == "None"
