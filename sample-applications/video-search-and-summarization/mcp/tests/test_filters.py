from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from pydantic import ValidationError

from src.filters import (
    operation_config,
    ProxyFilterConfig,
    configured_tool_name,
    load_filter_config,
    operation_is_enabled,
    resource_is_enabled,
    tool_is_enabled,
)
from src.models import OperationSpec


class FilterConfigTests(unittest.TestCase):
    def _operation(self, *, method: str, path: str) -> OperationSpec:
        return OperationSpec(
            method=method,
            path=path,
            slug="example",
            operation_id=None,
            summary=None,
            description=None,
            tags=(),
            parameters=(),
            request_body=None,
            response_content_types=(),
        )

    def test_api_entries_enable_expected_operations(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "enabled": True,
                "tool_prefix": "demo",
                "resource_scheme": "demo",
                "apis": {
                    "GET /widgets": {"expose": "resource"},
                    "PATCH /jobs/{jobId}/retry": {
                        "expose": "tool",
                        "tool_name": "retry_job",
                    },
                    "GET /reports/{reportId}": {"expose": "resource"},
                    "DELETE /jobs/private/{jobId}": {"expose": "disabled"},
                },
            }
        )

        self.assertTrue(operation_is_enabled(config, self._operation(method="GET", path="/widgets")))
        self.assertFalse(tool_is_enabled(config, self._operation(method="GET", path="/widgets")))
        self.assertTrue(resource_is_enabled(config, self._operation(method="GET", path="/widgets")))
        self.assertTrue(tool_is_enabled(config, self._operation(method="PATCH", path="/jobs/{jobId}/retry")))
        self.assertFalse(
            resource_is_enabled(config, self._operation(method="PATCH", path="/jobs/{jobId}/retry"))
        )
        self.assertEqual(
            configured_tool_name(
                config,
                self._operation(method="PATCH", path="/jobs/{jobId}/retry"),
            ),
            "demo_retry_job",
        )
        self.assertFalse(tool_is_enabled(config, self._operation(method="GET", path="/reports/{reportId}")))
        self.assertTrue(resource_is_enabled(config, self._operation(method="GET", path="/reports/{reportId}")))
        self.assertFalse(operation_is_enabled(config, self._operation(method="POST", path="/widgets")))
        self.assertFalse(
            operation_is_enabled(config, self._operation(method="DELETE", path="/jobs/private/{jobId}"))
        )

    def test_resource_exposure_still_requires_read_only_requestless_endpoint(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "enabled": True,
                "tool_prefix": "demo",
                "resource_scheme": "demo",
                "apis": {
                    "GET /runs/{runId}": {"expose": "resource"},
                    "DELETE /runs/{runId}": {"expose": "resource"},
                },
            }
        )

        self.assertTrue(resource_is_enabled(config, self._operation(method="GET", path="/runs/{runId}")))
        self.assertFalse(
            resource_is_enabled(config, self._operation(method="DELETE", path="/runs/{runId}"))
        )

    def test_wildcards_are_rejected_in_api_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "Wildcard API keys are not supported"):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "tool_prefix": "demo",
                    "resource_scheme": "demo",
                    "apis": {
                        "GET /search/*": {"expose": "resource"},
                    },
                }
            )

    def test_tool_entries_require_tool_name(self) -> None:
        with self.assertRaisesRegex(ValidationError, 'tool_name is required when expose is "tool"'):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "tool_prefix": "demo",
                    "resource_scheme": "demo",
                    "apis": {
                        "POST /widgets": {"expose": "tool"},
                    },
                }
            )

    def test_resource_entries_reject_tool_name(self) -> None:
        with self.assertRaisesRegex(ValidationError, 'tool_name is only allowed when expose is "tool"'):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "tool_prefix": "demo",
                    "resource_scheme": "demo",
                    "apis": {
                        "GET /widgets": {
                            "expose": "resource",
                            "tool_name": "list_widgets",
                        },
                    },
                }
            )

    def test_both_exposure_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "tool_prefix": "demo",
                    "resource_scheme": "demo",
                    "apis": {
                        "GET /widgets": {"expose": "both"},
                    },
                }
            )

    def test_duplicate_tool_names_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, 'tool_name "save_widget" is used by both'):
            ProxyFilterConfig.model_validate(
                {
                    "enabled": True,
                    "tool_prefix": "demo",
                    "resource_scheme": "demo",
                    "apis": {
                        "POST /widgets": {
                            "expose": "tool",
                            "tool_name": "save_widget",
                        },
                        "PATCH /widgets/{widgetId}": {
                            "expose": "tool",
                            "tool_name": "save_widget",
                        },
                    },
                }
            )

    def test_load_filter_config_reads_generic_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "demo-filter.json"
            config_path.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "server_name": "demo_server",
                        "tool_prefix": "demo",
                        "resource_scheme": "demo",
                        "apis": {
                            "GET /widgets/{widgetId}": {
                                "expose": "resource",
                                "description": "Get a widget by ID.",
                            },
                            "POST /widgets": {
                                "expose": "tool",
                                "tool_name": "create_widget",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = load_filter_config(str(config_path))

        self.assertEqual(config.server_name, "demo_server")
        self.assertEqual(config.tool_prefix, "demo")
        operation = self._operation(method="GET", path="/widgets/{widgetId}")
        self.assertTrue(operation_is_enabled(config, operation))
        self.assertEqual(operation_config(config, operation).description, "Get a widget by ID.")
        self.assertEqual(
            configured_tool_name(config, self._operation(method="POST", path="/widgets")),
            "demo_create_widget",
        )


if __name__ == "__main__":
    unittest.main()
