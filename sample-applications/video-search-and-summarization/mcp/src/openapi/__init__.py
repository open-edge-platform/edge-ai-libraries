# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenAPI ingestion and MCP-mapping helpers.

This package isolates the logic that translates an OpenAPI/Swagger document
into the inputs required by :func:`fastmcp.FastMCP.from_openapi` — namely the
spec dictionary itself, the resolved backend base URL, the operation-id to
MCP-name map, and the route classification / component customisation
callables.
"""

from .loader import fetch_openapi_spec
from .mapping import build_component_fn, build_mcp_names, build_route_map_fn

__all__ = [
    "fetch_openapi_spec",
    "build_mcp_names",
    "build_route_map_fn",
    "build_component_fn",
]
