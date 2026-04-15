from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import json
import textwrap
import unittest

from src.config import Settings
from src.main import create_mcp


class ServerRegistrationTests(unittest.TestCase):
    def _write_demo_spec(self, directory: Path) -> Path:
        spec_path = directory / "openapi.yaml"
        spec_path.write_text(
            textwrap.dedent(
                """
                openapi: 3.0.0
                info:
                  title: Demo API
                  version: "1.0"
                servers:
                  - url: https://api.example.com/v1
                paths:
                  /health:
                    get:
                      operationId: checkHealth
                      summary: Check service health
                      responses:
                        "200":
                          description: ok
                  /widgets:
                    get:
                      operationId: listWidgets
                      responses:
                        "200":
                          description: ok
                    post:
                      operationId: createWidget
                      requestBody:
                        required: true
                        content:
                          application/json:
                            schema:
                              type: object
                      responses:
                        "201":
                          description: created
                  /widgets/{widgetId}:
                    get:
                      operationId: getWidget
                      parameters:
                        - name: widgetId
                          in: path
                          required: true
                          schema:
                            type: string
                      responses:
                        "200":
                          description: ok
                  /widgets/{widgetId}/status:
                    patch:
                      summary: Update widget status
                      parameters:
                        - name: widgetId
                          in: path
                          required: true
                          schema:
                            type: string
                      requestBody:
                        required: true
                        content:
                          application/json:
                            schema:
                              type: object
                      responses:
                        "200":
                          description: ok
                """
            ).strip(),
            encoding="utf-8",
        )
        return spec_path

    def _write_demo_filter(self, directory: Path) -> Path:
        filter_path = directory / "filter.json"
        filter_path.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "server_name": "demo_server",
                    "tool_prefix": "demo",
                    "resource_scheme": "demo",
                    "include": [
                        {"path": "/health", "methods": ["GET"]},
                        {"path": "/widgets", "methods": ["GET"]},
                        {"path": "/widgets/{widgetId}", "methods": ["GET"]},
                        {"path": "/widgets/{widgetId}/status", "methods": ["PATCH"]},
                    ],
                    "resource_methods": ["GET"],
                }
            ),
            encoding="utf-8",
        )
        return filter_path

    def _serve_directory(self, directory: Path):
        handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _settings(self, spec_url: str, filter_path: Path) -> Settings:
        return Settings(
            app_name="App Proxy MCP",
            app_version="0.2.0",
            spec_url=spec_url,
            filter_config_path=str(filter_path),
            target_base_url="http://localhost:12345/api",
            request_timeout_seconds=60.0,
            log_level="INFO",
            mcp_host="127.0.0.1",
            mcp_port=8000,
            mcp_path="/mcp",
            stateless_http=True,
        )

    def test_create_mcp_registers_generic_tools_and_resources(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self._write_demo_spec(temp_path)
            filter_path = self._write_demo_filter(temp_path)
            server, thread = self._serve_directory(temp_path)
            spec_url = f"http://127.0.0.1:{server.server_port}/openapi.yaml"
            try:
                mcp = create_mcp(self._settings(spec_url, filter_path))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

        self.assertIn("demo_check_health", mcp._tool_manager._tools)
        self.assertIn("demo_list_widgets", mcp._tool_manager._tools)
        self.assertIn("demo_get_widget", mcp._tool_manager._tools)
        self.assertIn("demo_patch_widgets_by_widget_id_status", mcp._tool_manager._tools)
        self.assertNotIn("demo_create_widget", mcp._tool_manager._tools)
        self.assertIn("demo://__meta/catalog", mcp._resource_manager._resources)
        self.assertIn("demo://__meta/filter", mcp._resource_manager._resources)
        self.assertIn("demo://health", mcp._resource_manager._resources)
        self.assertIn("demo://widgets/{widget_id}", mcp._resource_manager._templates)
        self.assertNotIn("demo://widgets/{widget_id}/status", mcp._resource_manager._templates)

    def test_generated_tool_schema_includes_generic_path_params(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self._write_demo_spec(temp_path)
            filter_path = self._write_demo_filter(temp_path)
            server, thread = self._serve_directory(temp_path)
            spec_url = f"http://127.0.0.1:{server.server_port}/openapi.yaml"
            try:
                mcp = create_mcp(self._settings(spec_url, filter_path))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

        patch_tool = mcp._tool_manager._tools["demo_patch_widgets_by_widget_id_status"]

        self.assertIn("widget_id", patch_tool.parameters["properties"])
        self.assertIn("widget_id", patch_tool.parameters["required"])


if __name__ == "__main__":
    unittest.main()
