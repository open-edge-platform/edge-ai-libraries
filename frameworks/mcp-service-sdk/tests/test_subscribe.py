"""Tests for generic MCP subscription callback delivery."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from mcp_service_sdk import ServiceServer


class _Handler(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers["Content-Length"])
        self.__class__.received.append(json.loads(self.rfile.read(length)))
        self.send_response(202)
        self.end_headers()

    def log_message(self, *_args) -> None:
        pass


def test_subscriber_receives_matching_event_after_emit():
    _Handler.received = []
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    try:
        svc = ServiceServer(service="sad", store_id="store")
        callback = f"http://127.0.0.1:{server.server_port}/events"
        svc.subscribe("report_suspicious_activity", "severity == critical", callback)
        svc.emit("report_suspicious_activity", {"severity": "warning"}, ref_id="warning")
        svc.emit("report_suspicious_activity", {"severity": "critical"}, ref_id="critical")
        thread.join(timeout=2)
        assert len(_Handler.received) == 1
        assert _Handler.received[0]["event"]["ref_id"] == "critical"
    finally:
        server.server_close()
