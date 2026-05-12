# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for app/logging_config.py."""

import json
import logging
import sys
from unittest.mock import patch

import pytest

from app.logging_config import (
    JSONFormatter,
    TextFormatter,
    get_correlation_id,
    set_correlation_id,
    setup_logging,
)


def _make_record(msg="test message", level=logging.INFO, exc_info=None):
    record = logging.LogRecord(
        name="test.logger",
        level=level,
        pathname="test_file.py",
        lineno=42,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )
    return record


class TestJSONFormatter:
    def test_basic_format_produces_valid_json(self):
        formatter = JSONFormatter()
        record = _make_record("hello world")
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "hello world"
        assert data["level"] == "INFO"

    def test_format_includes_correlation_id_when_set(self):
        """Lines 63-64: correlation_id added when present."""
        set_correlation_id("test-cid-123")
        formatter = JSONFormatter()
        record = _make_record()
        data = json.loads(formatter.format(record))
        assert data["correlation_id"] == "test-cid-123"

    def test_format_without_correlation_id(self):
        from app.logging_config import correlation_id_var
        correlation_id_var.set(None)
        formatter = JSONFormatter()
        record = _make_record()
        data = json.loads(formatter.format(record))
        assert "correlation_id" not in data

    def test_format_with_exc_info(self):
        """Line 75: exception info is serialized."""
        formatter = JSONFormatter()
        try:
            raise ValueError("test error for logging")
        except ValueError:
            exc_info = sys.exc_info()

        record = _make_record(level=logging.ERROR, exc_info=exc_info)
        data = json.loads(formatter.format(record))
        assert "exception" in data
        assert "ValueError" in data["exception"]


class TestTextFormatter:
    """Lines 109-125: TextFormatter.format()."""

    def test_basic_format_contains_message(self):
        formatter = TextFormatter()
        record = _make_record("hello text")
        output = formatter.format(record)
        assert "hello text" in output
        assert "INFO" in output

    def test_format_includes_correlation_id_when_set(self):
        """Line 110: [cid] prefix when correlation_id is set."""
        set_correlation_id("abc-def")
        formatter = TextFormatter()
        record = _make_record("with cid")
        output = formatter.format(record)
        assert "abc-def" in output

    def test_format_no_cid_string_when_not_set(self):
        """Line 110: cid_str is empty when no correlation_id."""
        set_correlation_id(None)
        formatter = TextFormatter()
        record = _make_record("no cid")
        output = formatter.format(record)
        assert "[" not in output or "no cid" in output

    def test_format_color_applied_for_known_level(self):
        """Lines 112-113: ANSI color code injected for known levels."""
        formatter = TextFormatter()
        record = _make_record(level=logging.WARNING)
        output = formatter.format(record)
        assert "WARNING" in output
        # ANSI escape code present
        assert "\033[" in output

    def test_format_no_color_for_unknown_level(self):
        """Lines 112-113: no color for unknown level name."""
        formatter = TextFormatter()
        record = _make_record()
        record.levelname = "CUSTOM"
        output = formatter.format(record)
        assert "CUSTOM" in output

    def test_format_with_exc_info(self):
        """Lines 122-123: exception appended to message."""
        formatter = TextFormatter()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            exc_info = sys.exc_info()

        record = _make_record(level=logging.ERROR, exc_info=exc_info)
        output = formatter.format(record)
        assert "RuntimeError" in output
        assert "boom" in output


class TestSetupLogging:
    def test_setup_logging_json_format(self):
        from app.settings import Settings

        mock_settings = Settings(log_format="json", environment="production")
        with patch("app.logging_config.get_settings", return_value=mock_settings):
            setup_logging()
        root = logging.getLogger()
        assert any(isinstance(h.formatter, JSONFormatter) for h in root.handlers)

    def test_setup_logging_text_format(self):
        """Line 155: TextFormatter used when log_format=='text'."""
        from app.settings import Settings

        mock_settings = Settings(log_format="text", environment="production")
        with patch("app.logging_config.get_settings", return_value=mock_settings):
            setup_logging()
        root = logging.getLogger()
        assert any(isinstance(h.formatter, TextFormatter) for h in root.handlers)


class TestJSONFormatterTaskName:
    def test_taskname_excluded_from_json_output(self):
        """taskName (added in Python 3.12) must not appear in JSON log output."""
        formatter = JSONFormatter()
        record = _make_record("task name test")
        record.taskName = "some-asyncio-task"
        data = json.loads(formatter.format(record))
        assert "taskName" not in data


class TestSetCorrelationId:
    def test_set_generates_id_when_none_given(self):
        cid = set_correlation_id()
        assert cid is not None
        assert get_correlation_id() == cid

    def test_set_uses_provided_id(self):
        set_correlation_id("my-id")
        assert get_correlation_id() == "my-id"
