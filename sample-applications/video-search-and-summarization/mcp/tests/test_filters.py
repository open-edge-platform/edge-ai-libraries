from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from src.filters import (
    ProxyFilterConfig,
    load_filter_config,
    operation_is_enabled,
    resource_is_enabled,
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

    def test_path_and_method_filters_enable_expected_operations(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "enabled": True,
                "tool_prefix": "demo",
                "resource_scheme": "demo",
                "include": [
                    {"path": "/widgets", "methods": ["GET"]},
                    {"path": "/jobs/*/retry", "methods": ["POST", "PATCH"]},
                ],
                "exclude": [{"path": "/jobs/private/*"}],
            }
        )

        self.assertTrue(operation_is_enabled(config, self._operation(method="GET", path="/widgets")))
        self.assertTrue(
            operation_is_enabled(config, self._operation(method="PATCH", path="/jobs/123/retry"))
        )
        self.assertFalse(operation_is_enabled(config, self._operation(method="POST", path="/widgets")))
        self.assertFalse(
            operation_is_enabled(config, self._operation(method="POST", path="/jobs/private/123"))
        )

    def test_single_segment_wildcard_does_not_match_nested_paths(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "enabled": True,
                "tool_prefix": "demo",
                "resource_scheme": "demo",
                "include": [{"path": "/search/*", "methods": ["GET"]}],
            }
        )

        self.assertTrue(operation_is_enabled(config, self._operation(method="GET", path="/search/query")))
        self.assertFalse(
            operation_is_enabled(config, self._operation(method="GET", path="/search/123/watch"))
        )

    def test_resources_follow_read_only_method_allowlist(self) -> None:
        config = ProxyFilterConfig.model_validate(
            {
                "enabled": True,
                "tool_prefix": "demo",
                "resource_scheme": "demo",
                "include": [{"path": "/runs/*", "methods": ["GET", "DELETE"]}],
                "resource_methods": ["GET"],
            }
        )

        self.assertTrue(resource_is_enabled(config, self._operation(method="GET", path="/runs/1")))
        self.assertFalse(resource_is_enabled(config, self._operation(method="DELETE", path="/runs/1")))

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
                        "guidance_markdown": "Use the demo API carefully.",
                        "include": [{"path": "/widgets/*", "methods": ["GET"]}],
                        "exclude": [{"path": "/widgets/private/*"}],
                        "resource_methods": ["GET"],
                    }
                ),
                encoding="utf-8",
            )

            config = load_filter_config(str(config_path))

        self.assertEqual(config.server_name, "demo_server")
        self.assertEqual(config.tool_prefix, "demo")
        self.assertIn("demo API", config.guidance_markdown or "")
        self.assertTrue(operation_is_enabled(config, self._operation(method="GET", path="/widgets/42")))
        self.assertFalse(
            operation_is_enabled(config, self._operation(method="GET", path="/widgets/private/42"))
        )


if __name__ == "__main__":
    unittest.main()
