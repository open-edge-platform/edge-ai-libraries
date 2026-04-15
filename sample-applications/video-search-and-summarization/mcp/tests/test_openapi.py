from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import textwrap
import unittest

from src.config import Settings
from src.openapi import load_api_catalog


class OpenApiCatalogTests(unittest.TestCase):
    def _settings(self, *, spec_url: str, target_base_url: str | None) -> Settings:
        return Settings(
            app_name="App Proxy MCP",
            app_version="0.2.0",
            spec_url=spec_url,
            filter_config_path="proxy-all.json",
            target_base_url=target_base_url,
            request_timeout_seconds=60.0,
            log_level="INFO",
            mcp_host="127.0.0.1",
            mcp_port=8000,
            mcp_path="/mcp",
            stateless_http=True,
        )

    def _serve_directory(self, directory: Path):
        handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def test_infers_missing_path_parameters_from_uri_template(self) -> None:
        with TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "openapi.yaml").write_text(
                textwrap.dedent(
                    """
                    openapi: 3.0.0
                    info:
                      title: Demo API
                      version: "1.0"
                    paths:
                      /users/{userId}:
                        get:
                          operationId: getUser
                          responses:
                            "200":
                              description: ok
                    """
                ).strip(),
                encoding="utf-8",
            )
            server, thread = self._serve_directory(Path(temp_dir))
            spec_url = f"http://127.0.0.1:{server.server_port}/openapi.yaml"
            try:
                catalog = load_api_catalog(
                    self._settings(spec_url=spec_url, target_base_url="https://api.example.com")
                )
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            operation = next(operation for operation in catalog.operations if operation.path == "/users/{userId}")

            self.assertEqual(operation.slug, "get_user")
            self.assertEqual([parameter.name for parameter in operation.path_parameters], ["userId"])
            self.assertEqual([parameter.field_name for parameter in operation.path_parameters], ["user_id"])

    def test_loads_swagger2_and_resolves_base_url(self) -> None:
        with TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "swagger.json").write_text(
                textwrap.dedent(
                    """
                    {
                      "swagger": "2.0",
                      "info": {
                        "title": "Pet API",
                        "version": "1.0"
                      },
                      "schemes": ["https"],
                      "host": "api.example.com",
                      "basePath": "/v1",
                      "paths": {
                        "/pets": {
                          "get": {
                            "operationId": "listPets",
                            "responses": {
                              "200": {
                                "description": "ok"
                              }
                            }
                          }
                        }
                      }
                    }
                    """
                ).strip(),
                encoding="utf-8",
            )
            server, thread = self._serve_directory(Path(temp_dir))
            spec_url = f"http://127.0.0.1:{server.server_port}/swagger.json"
            try:
                catalog = load_api_catalog(self._settings(spec_url=spec_url, target_base_url=None))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            self.assertEqual(catalog.spec_kind, "swagger2")
            self.assertEqual(catalog.base_url, "https://api.example.com/v1")
            self.assertEqual(catalog.operations[0].slug, "list_pets")


if __name__ == "__main__":
    unittest.main()
