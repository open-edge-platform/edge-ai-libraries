# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Structured logging configuration for production-ready observability.

Provides JSON-formatted logs with correlation IDs, request context,
and proper log levels for different environments.
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from .settings import get_settings

# Context variable for request correlation ID
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    """Get current correlation ID from context."""
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str | None = None) -> str:
    """Set correlation ID in context. Generates one if not provided."""
    cid = correlation_id or str(uuid.uuid4())[:8]
    correlation_id_var.set(cid)
    return cid


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Produces logs in JSON format suitable for log aggregation systems
    like ELK, Loki, or cloud logging services.
    """

    def __init__(self, service_name: str = "metrics-manager", service_version: str = "2026.1.0"):
        super().__init__()
        self.service_name = service_name
        self.service_version = service_version

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "version": self.service_version,
        }

        # Add correlation ID if available
        correlation_id = get_correlation_id()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        # Add source location
        log_data["source"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "message", "asctime",
                "taskName",  # added in Python 3.12
            }:
                log_data[key] = value

        return json.dumps(log_data, default=str)


class TextFormatter(logging.Formatter):
    """
    Human-readable text formatter for development.

    Includes correlation ID and colored output for terminals.
    """

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as colored text."""
        correlation_id = get_correlation_id()
        cid_str = f"[{correlation_id}] " if correlation_id else ""

        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET if color else ""

        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        message = (
            f"{timestamp} {color}{record.levelname:8}{reset} "
            f"{cid_str}{record.name}: {record.getMessage()}"
        )

        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return message


def setup_logging() -> None:
    """
    Configure logging for the application.

    Sets up JSON or text formatting based on settings,
    configures log levels, and adds handlers.
    """
    settings = get_settings()

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, settings.log_level))

    # Select formatter based on settings
    if settings.log_format == "json":
        formatter = JSONFormatter(
            service_name=settings.service_name,
            service_version=settings.service_version,
        )
    else:
        formatter = TextFormatter()

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Configure third-party loggers to be less verbose
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    # httpx logs every outbound request at INFO. The SSE endpoint polls
    # Telegraf's /metrics every ~500ms, so leaving this at INFO produces
    # one log line per poll per connected client. Demote to WARNING in
    # the normal case, but stay out of the way when the operator asked
    # for DEBUG: NOTSET (== 0) makes the logger inherit the root level
    # so per-request lines reappear under LOG_LEVEL=DEBUG.
    if settings.log_level == "DEBUG":
        httpx_level = logging.NOTSET
    else:
        httpx_level = logging.WARNING
    logging.getLogger("httpx").setLevel(httpx_level)
    logging.getLogger("httpcore").setLevel(httpx_level)

    # Create service logger
    logger = logging.getLogger("metrics-manager")
    logger.info(
        "Logging configured",
        extra={
            "log_level": settings.log_level,
            "log_format": settings.log_format,
            "environment": settings.environment,
        },
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the service prefix."""
    return logging.getLogger(f"metrics-manager.{name}")
