# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: healthcheck.py
Description: Docker HEALTHCHECK probe for the encoder/decoder image. This confirms PID 1 in the container
is actually the star-image (semantic_img_comp) application and isn't a zombie,
by reading /proc/1/cmdline and /proc/1/status directly, then cross-checks readiness
via the in-process status server (see start_status_server()) on STATUS_SERVER_PORT.
"""
import json
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Shared readiness flags: other in-process modules (e.g. encoder/runner.py) import and
# flip these once their respective listener is actually ready to accept connections.
HTTP_READY = False
TCP_READY = False

STATUS_SERVER_PORT = 5999


class _StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        payload = json.dumps({"is_alive": True, "http_ready": HTTP_READY, "tcp_ready": TCP_READY}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - silence default stderr access logging
        pass


def start_status_server(port: int = STATUS_SERVER_PORT) -> ThreadingHTTPServer:
    """Serve the readiness JSON on *port* so the Docker HEALTHCHECK (a separate process)
    can observe this process's in-memory HTTP_READY/TCP_READY flags over HTTP.
    """
    server = ThreadingHTTPServer(("0.0.0.0", port), _StatusHandler)  # nosec B104 - container-internal status endpoint, probed by Docker HEALTHCHECK
    threading.Thread(target=server.serve_forever, daemon=True, name="status-server").start()
    return server


if __name__ == "__main__":
    try:
        with open("/proc/1/cmdline", "rb") as f:
            argv = f.read().decode().split("\0")[:-1]
        with open("/proc/1/status", "r") as f:
            status = f.read()
    except OSError:
        sys.exit(1)

    is_star_image = "semantic_img_comp.main" in " ".join(argv)
    is_alive = "\nState:\tZ" not in status

    try:
        with urllib.request.urlopen(f"http://localhost:{STATUS_SERVER_PORT}/", timeout=5) as resp:  # nosec B310 - fixed localhost URL, not user input
            status_payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        status_payload = {"is_alive": is_alive, "http_ready": False, "tcp_ready": False}

    print(json.dumps(status_payload))

    if not (is_star_image and is_alive):
        sys.exit(1)
