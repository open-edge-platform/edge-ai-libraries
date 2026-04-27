# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from src.filters import (
    ProxyFilterConfig,
    api_config_for,
    configured_name,
    load_filter_config,
)


class FilterConfigTests(unittest.TestCase):
    def test_api_entries_enable_expected_operations(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "enabled": True,
                "prefix": "demo",
                "apis": {
                    "GET /widgets": {"type": "resource", "name": "list_widgets"},
                    "PATCH /jobs/{jobId}/retry": {"type": "tool", "name": "retry_job"},
                    "GET /reports/{reportId}": {"type": "resource", "name": "get_report"},
                },
            }
        )

        self.assertEqual(
            configured_name(config, "GET", "/widgets"),
            "demo_list_widgets",
        )
        self.assertEqual(
            configured_name(config, "PATCH", "/jobs/{jobId}/retry"),
            "demo_retry_job",
        )
        self.assertEqual(
            configured_name(config, "GET", "/reports/{reportId}"),
            "demo_get_report",
        )
        self.assertIsNone(configured_name(config, "POST", "/widgets"))
        self.assertIsNone(api_config_for(config, "POST", "/widgets"))

    def test_resource_must_be_get(self) -> None:
        with self.assertRaisesRegex(ValidationError, "only GET operations"):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "prefix": "demo",
                    "apis": {
                        "DELETE /runs/{runId}": {"type": "resource", "name": "delete_run"},
                    },
                }
            )

    def test_wildcards_are_rejected_in_api_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "Wildcard API keys are not supported"):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "prefix": "demo",
                    "apis": {
                        "GET /search/*": {"type": "resource", "name": "search"},
                    },
                }
            )

    def test_name_is_required(self) -> None:
        with self.assertRaises(ValidationError):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "prefix": "demo",
                    "apis": {
                        "POST /widgets": {"type": "tool"},
                    },
                }
            )

    def test_type_is_required(self) -> None:
        with self.assertRaises(ValidationError):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "prefix": "demo",
                    "apis": {
                        "POST /widgets": {"name": "create_widget"},
                    },
                }
            )

    def test_unknown_type_value_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "prefix": "demo",
                    "apis": {
                        "GET /widgets": {"type": "both", "name": "list_widgets"},
                    },
                }
            )

    def test_extra_fields_are_rejected(self) -> None:
        # Old schema fields like "expose", "tool_name", "resource_name" must
        # be rejected so users can't accidentally use a stale filter file.
        with self.assertRaises(ValidationError):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "prefix": "demo",
                    "apis": {
                        "POST /widgets": {
                            "type": "tool",
                            "name": "create_widget",
                            "expose": "tool",
                        },
                    },
                }
            )

    def test_invalid_name_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "valid identifier"):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "prefix": "demo",
                    "apis": {
                        "POST /widgets": {"type": "tool", "name": "create-widget"},
                    },
                }
            )

    def test_duplicate_names_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, 'name "save_widget" is used by both'):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "prefix": "demo",
                    "apis": {
                        "POST /widgets": {"type": "tool", "name": "save_widget"},
                        "PATCH /widgets/{widgetId}": {"type": "tool", "name": "save_widget"},
                    },
                }
            )

    def test_duplicate_names_across_kinds_are_rejected(self) -> None:
        # Names live in a single namespace because the prefix is shared.
        with self.assertRaisesRegex(ValidationError, "is used by both"):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "prefix": "demo",
                    "apis": {
                        "GET /widgets": {"type": "resource", "name": "widget"},
                        "POST /widgets": {"type": "tool", "name": "widget"},
                    },
                }
            )

    def test_disabled_config_reports_nothing_enabled(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "enabled": False,
                "prefix": "demo",
                "apis": {
                    "GET /widgets": {"type": "resource", "name": "list_widgets"},
                    "POST /widgets": {"type": "tool", "name": "create_widget"},
                },
            }
        )

        self.assertIsNone(api_config_for(config, "GET", "/widgets"))
        self.assertIsNone(configured_name(config, "POST", "/widgets"))

    def test_load_filter_config_reads_generic_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "demo-filter.json"
            config_path.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "server_name": "demo_server",
                        "prefix": "demo",
                        "apis": {
                            "GET /widgets/{widgetId}": {
                                "type": "resource",
                                "name": "get_widget",
                                "description": "Get a widget by ID.",
                            },
                            "POST /widgets": {"type": "tool", "name": "create_widget"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = load_filter_config(str(config_path))

        self.assertEqual(config.server_name, "demo_server")
        self.assertEqual(config.prefix, "demo")
        self.assertEqual(
            api_config_for(config, "GET", "/widgets/{widgetId}").description,
            "Get a widget by ID.",
        )
        self.assertEqual(
            configured_name(config, "POST", "/widgets"),
            "demo_create_widget",
        )
        self.assertEqual(
            configured_name(config, "GET", "/widgets/{widgetId}"),
            "demo_get_widget",
        )


if __name__ == "__main__":
    unittest.main()
