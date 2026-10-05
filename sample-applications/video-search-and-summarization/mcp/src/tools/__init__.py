# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Hand-declared MCP tools over the VSS API."""

from __future__ import annotations

from fastmcp import FastMCP

from . import discovery, ingest, search, summary
from ._deps import Deps

__all__ = ["Deps", "register_all"]


def register_all(mcp: FastMCP, deps: Deps) -> None:
    """Register every tool module on ``mcp``."""

    discovery.register(mcp, deps)
    ingest.register(mcp, deps)
    summary.register(mcp, deps)
    search.register(mcp, deps)
