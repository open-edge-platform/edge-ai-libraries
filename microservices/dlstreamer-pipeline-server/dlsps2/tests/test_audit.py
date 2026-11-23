# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for core.audit (dedicated audit logger)."""

import logging
import sys
from unittest.mock import MagicMock

sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gst'] = MagicMock()

from core.audit import get_audit_logger


class TestGetAuditLogger:

    def test_returns_logger_named_audit(self):
        logger = get_audit_logger()
        assert logger.name == "audit"

    def test_does_not_propagate_to_root(self):
        logger = get_audit_logger()
        assert logger.propagate is False

    def test_has_at_least_a_stream_handler(self):
        logger = get_audit_logger()
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)

    def test_repeated_calls_do_not_duplicate_handlers(self):
        logger1 = get_audit_logger()
        handler_count = len(logger1.handlers)
        logger2 = get_audit_logger()
        assert logger2 is logger1
        assert len(logger2.handlers) == handler_count
