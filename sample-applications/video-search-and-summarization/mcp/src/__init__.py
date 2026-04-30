# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Spec-driven MCP REST proxy package.

Re-exports the public entrypoints so callers can simply
``from src import main`` or ``from src import create_mcp``.
"""

from .main import main
from .server import create_mcp, get_mcp

__all__ = ["create_mcp", "get_mcp", "main"]
