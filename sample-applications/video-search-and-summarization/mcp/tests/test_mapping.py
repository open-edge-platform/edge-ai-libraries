# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for converting filter rules into FastMCP OpenAPI mapping callbacks."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from fastmcp.server.providers.openapi import MCPType

from src.filters import ProxyFilterConfig
from src.openapi.mapping import build_component_fn, build_mcp_names, build_route_map_fn


def route(method: str, path: str) -> SimpleNamespace:
    """Create the route shape consumed by the mapping callbacks."""

    return SimpleNamespace(method=method, path=path)


class McpNameMappingTests(unittest.TestCase):
    def test_build_mcp_names_maps_only_filtered_operations_with_operation_ids(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "prefix": "vss",
                "apis": {
                    "GET /app/features": {"type": "resource", "name": "app_features"},
                    "POST /search/query": {"type": "tool", "name": "run_search_query"},
                    "DELETE /search/{queryId}": {"type": "tool", "name": "delete_query"},
                },
            }
        )
        spec = {
            "paths": {
                "/app/features": {
                    "get": {"operationId": "AppController_getFeatures"},
                },
                "/search/query": {
                    "post": {"operationId": "SearchController_search"},
                },
                "/search/{queryId}": {
                    "delete": {"operationId": "SearchController_delete"},
                    "parameters": [{"name": "queryId", "in": "path"}],
                },
                "/not-configured": {
                    "get": {"operationId": "NotConfigured_get"},
                },
                "/missing-operation-id": {
                    "get": {"summary": "No operationId"},
                },
            }
        }

        self.assertEqual(
            build_mcp_names(spec, config),
            {
                "AppController_getFeatures": "vss_app_features",
                "SearchController_search": "vss_run_search_query",
                "SearchController_delete": "vss_delete_query",
            },
        )

    def test_build_mcp_names_returns_empty_mapping_for_empty_apis(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "prefix": "vss",
                "apis": {},
            }
        )
        spec = {
            "paths": {
                "/app/features": {
                    "get": {"operationId": "AppController_getFeatures"},
                },
            }
        }

        self.assertEqual(build_mcp_names(spec, config), {})


class RouteMapTests(unittest.TestCase):
    def test_route_map_fn_classifies_tools_resources_templates_and_exclusions(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "apis": {
                    "GET /app/features": {"type": "resource", "name": "app_features"},
                    "GET /search/{queryId}": {"type": "resource", "name": "get_query"},
                    "POST /search/query": {"type": "tool", "name": "run_search_query"},
                },
            }
        )

        route_map_fn = build_route_map_fn(config)

        self.assertEqual(
            route_map_fn(route("GET", "/app/features"), MCPType.TOOL),
            MCPType.RESOURCE,
        )
        self.assertEqual(
            route_map_fn(route("GET", "/search/{queryId}"), MCPType.TOOL),
            MCPType.RESOURCE_TEMPLATE,
        )
        self.assertEqual(
            route_map_fn(route("POST", "/search/query"), MCPType.RESOURCE),
            MCPType.TOOL,
        )
        self.assertEqual(
            route_map_fn(route("DELETE", "/search/{queryId}"), MCPType.TOOL),
            MCPType.EXCLUDE,
        )
        self.assertEqual(
            route_map_fn.counters,
            {"tool": 1, "resource": 1, "resource_template": 1, "excluded": 1},
        )

    def test_route_map_fn_excludes_routes_not_in_filter(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "apis": {
                    "POST /search/query": {"type": "tool", "name": "run_search_query"},
                },
            }
        )

        route_map_fn = build_route_map_fn(config)

        # Route not listed in the filter is always excluded.
        self.assertEqual(
            route_map_fn(route("DELETE", "/search/query"), MCPType.TOOL),
            MCPType.EXCLUDE,
        )
        self.assertEqual(route_map_fn.counters["excluded"], 1)


class ComponentMappingTests(unittest.TestCase):
    def test_component_fn_prepends_description_override(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "apis": {
                    "POST /search/query": {
                        "type": "tool",
                        "name": "run_search_query",
                        "description": "Run a search immediately.",
                    },
                },
            }
        )
        component = SimpleNamespace(description="Generated from OpenAPI.")

        build_component_fn(config)(route("post", "/search/query"), component)

        self.assertEqual(
            component.description,
            "Run a search immediately.\n\nGenerated from OpenAPI.",
        )

    def test_component_fn_leaves_unconfigured_components_unchanged(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "apis": {
                    "POST /search/query": {"type": "tool", "name": "run_search_query"},
                },
            }
        )
        component = SimpleNamespace(description="Generated from OpenAPI.")

        build_component_fn(config)(route("GET", "/app/features"), component)

        self.assertEqual(component.description, "Generated from OpenAPI.")


if __name__ == "__main__":
    unittest.main()
