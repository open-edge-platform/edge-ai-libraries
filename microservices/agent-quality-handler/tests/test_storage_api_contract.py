# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for the storage API that AQH depends on.

These tests start a lightweight mock storage server and verify that the
StorageClient correctly consumes both required endpoints:

  GET /detections      — JSON array of detection records
  GET /detections/summary — JSON object with per-class aggregates

Run with:  pytest tests/test_storage_api_contract.py -v
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from src.utility.storage_client import (
    StorageClient,
    StorageContractError,
    StorageHTTPError,
)

# ---------------------------------------------------------------------------
# Sample data returned by the mock storage server
# ---------------------------------------------------------------------------

DETECTIONS = [
    {"id": 101, "frame_id": 10, "label": "Rupture", "confidence": 0.92, "x": 50, "y": 60, "width": 30, "height": 40},
    {"id": 102, "frame_id": 10, "label": "Rupture", "confidence": 0.88, "x": 55, "y": 65, "width": 28, "height": 38},
    {"id": 103, "frame_id": 11, "label": "Deformation", "confidence": 0.65, "x": 100, "y": 120, "width": 50, "height": 45},
    {"id": 150, "frame_id": 20, "label": "Rupture", "confidence": 0.95, "x": 52, "y": 62, "width": 31, "height": 41},
    {"id": 200, "frame_id": 30, "label": "Deformation", "confidence": 0.72, "x": 105, "y": 125, "width": 48, "height": 44},
    {"id": 250, "frame_id": 40, "label": "Scratch", "confidence": 0.55, "x": 10, "y": 20, "width": 15, "height": 12},
]

STATS = {
    "by_class": [
        {"label": "Rupture", "count": 3, "avg_confidence": 0.917, "max_confidence": 0.95},
        {"label": "Deformation", "count": 2, "avg_confidence": 0.685, "max_confidence": 0.72},
        {"label": "Scratch", "count": 1, "avg_confidence": 0.55, "max_confidence": 0.55},
    ]
}


# ---------------------------------------------------------------------------
# Mock storage HTTP server
# ---------------------------------------------------------------------------

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
        pass  # suppress console noise during tests


@pytest.fixture(scope="module")
def mock_storage_server():
    server = HTTPServer(("127.0.0.1", 0), MockStorageHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
def client(mock_storage_server):
    return StorageClient(
        base_url=mock_storage_server,
        connect_timeout_seconds=5.0,
        read_timeout_seconds=5.0,
        read_max_attempts=1,
        retry_backoff_seconds=0.0,
    )


# ---------------------------------------------------------------------------
# GET /detections
# ---------------------------------------------------------------------------

class TestGetDetections:
    def test_returns_all_records_without_filters(self, client):
        result = client.get_detections(limit=None)
        assert isinstance(result, list)
        assert len(result) == len(DETECTIONS)

    def test_filters_by_id_window(self, client):
        result = client.get_detections(min_id=100, max_id=150, limit=None)
        ids = {d["id"] for d in result}
        assert all(100 < i <= 150 for i in ids)
        assert ids == {101, 102, 103, 150}

    def test_filters_by_label(self, client):
        result = client.get_detections(label="Rupture", limit=None)
        assert all(d["label"] == "Rupture" for d in result)
        assert len(result) == 3

    def test_filters_by_min_confidence(self, client):
        result = client.get_detections(min_confidence=0.8, limit=None)
        assert all(d["confidence"] >= 0.8 for d in result)

    def test_respects_limit(self, client):
        result = client.get_detections(limit=2)
        assert len(result) == 2

    def test_combined_filters(self, client):
        result = client.get_detections(
            label="Rupture", min_confidence=0.9, min_id=100, max_id=250, limit=10
        )
        assert all(d["label"] == "Rupture" for d in result)
        assert all(d["confidence"] >= 0.9 for d in result)
        assert all(100 < d["id"] <= 250 for d in result)

    def test_each_record_has_required_fields(self, client):
        required = {"id", "frame_id", "label", "confidence", "x", "y", "width", "height"}
        result = client.get_detections(limit=None)
        for record in result:
            missing = required - record.keys()
            assert not missing, f"Record missing fields: {missing}"

    def test_empty_window_returns_empty_list(self, client):
        result = client.get_detections(min_id=9999, max_id=10000, limit=None)
        assert result == []


# ---------------------------------------------------------------------------
# GET /detections/summary
# ---------------------------------------------------------------------------

class TestGetSummary:
    def test_returns_object_with_by_class(self, client):
        result = client.get_summary()
        assert isinstance(result, dict)
        assert "by_class" in result
        assert isinstance(result["by_class"], list)

    def test_each_class_has_required_fields(self, client):
        required = {"label", "count", "avg_confidence", "max_confidence"}
        result = client.get_summary()
        for entry in result["by_class"]:
            missing = required - entry.keys()
            assert not missing, f"Class entry missing fields: {missing}"

    def test_summary_reflect_all_detections(self, client):
        result = client.get_summary()
        total = sum(c["count"] for c in result["by_class"])
        assert total == len(DETECTIONS)

    def test_summary_filtered_by_id_window(self, client):
        result = client.get_summary(min_id=100, max_id=150)
        labels = {c["label"] for c in result["by_class"]}
        # IDs 101,102 = Rupture; 103 = Deformation; 150 = Rupture
        assert labels == {"Rupture", "Deformation"}
        rupture = next(c for c in result["by_class"] if c["label"] == "Rupture")
        assert rupture["count"] == 3

    def test_empty_window_returns_empty_by_class(self, client):
        result = client.get_summary(min_id=9999, max_id=10000)
        assert result == {"by_class": []}

    def test_avg_confidence_is_correct(self, client):
        result = client.get_summary()
        rupture = next(c for c in result["by_class"] if c["label"] == "Rupture")
        expected_avg = round((0.92 + 0.88 + 0.95) / 3, 3)
        assert rupture["avg_confidence"] == expected_avg

    def test_max_confidence_is_correct(self, client):
        result = client.get_summary()
        rupture = next(c for c in result["by_class"] if c["label"] == "Rupture")
        assert rupture["max_confidence"] == 0.95


# ---------------------------------------------------------------------------
# Contract violation scenarios
# ---------------------------------------------------------------------------

class TestContractViolations:
    def test_detections_rejects_object_response(self, monkeypatch, client):
        """Storage must return a JSON array for /detections, not an object."""
        import src.utility.storage_client as sc

        monkeypatch.setattr(
            sc.requests, "get",
            lambda *a, **kw: type("R", (), {"status_code": 200, "json": lambda self: {"wrong": True}})(),
        )
        with pytest.raises(StorageContractError, match="must be a JSON array"):
            client.get_detections()

    def test_summary_rejects_array_response(self, monkeypatch, client):
        """Storage must return a JSON object for /detections/summary, not an array."""
        import src.utility.storage_client as sc

        monkeypatch.setattr(
            sc.requests, "get",
            lambda *a, **kw: type("R", (), {"status_code": 200, "json": lambda self: []})(),
        )
        with pytest.raises(StorageContractError, match="must be a JSON object"):
            client.get_summary()

    def test_non_2xx_raises_http_error(self, monkeypatch, client):
        import src.utility.storage_client as sc

        monkeypatch.setattr(
            sc.requests, "get",
            lambda *a, **kw: type("R", (), {"status_code": 404, "json": lambda self: {}})(),
        )
        with pytest.raises(StorageHTTPError) as exc_info:
            client.get_detections()
        assert exc_info.value.status_code == 404
