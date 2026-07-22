# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Standalone mock storage server for manual validation.

Implements the two endpoints AQH requires:
  GET /detections       — JSON array of detection records
  GET /detections/summary — JSON object with per-class aggregates

Start locally:  python3 tests/mock_storage_server.py
Via Compose:    docker compose -f docker/compose.yaml --profile dev up mock-storage
"""

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger("mock-storage")

DETECTIONS = [
    {"id": 101, "frame_id": 10, "label": "Rupture", "confidence": 0.92, "x": 50, "y": 60, "width": 30, "height": 40},
    {"id": 102, "frame_id": 10, "label": "Rupture", "confidence": 0.88, "x": 55, "y": 65, "width": 28, "height": 38},
    {"id": 103, "frame_id": 11, "label": "Deformation", "confidence": 0.65, "x": 100, "y": 120, "width": 50, "height": 45},
    {"id": 150, "frame_id": 20, "label": "Rupture", "confidence": 0.95, "x": 52, "y": 62, "width": 31, "height": 41},
    {"id": 200, "frame_id": 30, "label": "Deformation", "confidence": 0.72, "x": 105, "y": 125, "width": 48, "height": 44},
    {"id": 250, "frame_id": 40, "label": "Scratch", "confidence": 0.55, "x": 10, "y": 20, "width": 15, "height": 12},
]


class MockStorageHandler(BaseHTTPRequestHandler):
    """Minimal handler implementing the two storage endpoints."""

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/detections":
            self._handle_detections(qs)
        elif parsed.path == "/detections/summary":
            self._handle_stats(qs)
        else:
            self._respond(404, {"error": "not found"})

    def _handle_detections(self, qs):
        result = list(DETECTIONS)

        min_id = int(qs["min_id"][0]) if "min_id" in qs else None
        max_id = int(qs["max_id"][0]) if "max_id" in qs else None
        label = qs.get("label", [None])[0]
        min_conf = float(qs["min_confidence"][0]) if "min_confidence" in qs else None
        limit = int(qs["limit"][0]) if "limit" in qs else None

        if min_id is not None:
            result = [d for d in result if d["id"] > min_id]
        if max_id is not None:
            result = [d for d in result if d["id"] <= max_id]
        if label is not None:
            result = [d for d in result if d["label"] == label]
        if min_conf is not None:
            result = [d for d in result if d["confidence"] >= min_conf]
        if limit is not None:
            result = result[:limit]

        self._respond(200, result)

    def _handle_stats(self, qs):
        min_id = int(qs["min_id"][0]) if "min_id" in qs else None
        max_id = int(qs["max_id"][0]) if "max_id" in qs else None

        filtered = list(DETECTIONS)
        if min_id is not None:
            filtered = [d for d in filtered if d["id"] > min_id]
        if max_id is not None:
            filtered = [d for d in filtered if d["id"] <= max_id]

        classes: dict[str, list[float]] = {}
        for d in filtered:
            classes.setdefault(d["label"], []).append(d["confidence"])

        by_class = []
        for lbl, confs in sorted(classes.items()):
            by_class.append({
                "label": lbl,
                "count": len(confs),
                "avg_confidence": round(sum(confs) / len(confs), 3),
                "max_confidence": round(max(confs), 3),
            })

        self._respond(200, {"by_class": by_class})

    def _respond(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        log.info("%s %s %s", self.client_address[0], self.command, self.path)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 5001), MockStorageHandler)
    log.info("Mock storage server listening on :5001")
    server.serve_forever()
