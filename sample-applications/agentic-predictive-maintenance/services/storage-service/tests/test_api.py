# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

# Point to a temp db before importing the app
_tmp = tempfile.mktemp(suffix=".db")
os.environ["SQLITE_DB_PATH"] = _tmp

from src.api import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clear_db(client):
    client.delete("/detections")
    yield


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "detections_count" in data


# ── Insert single detection ───────────────────────────────────────────────────

def test_insert_detection(client):
    payload = {
        "frame_id": 1, "label": "Rupture", "confidence": 0.92,
        "x": 100, "y": 200, "width": 50, "height": 40,
    }
    r = client.post("/detections", json=payload)
    assert r.status_code == 201
    assert r.json()["inserted"] == 1


def test_insert_detection_invalid_confidence(client):
    payload = {
        "frame_id": 1, "label": "Deformation", "confidence": 1.5,
        "x": 10, "y": 10, "width": 20, "height": 20,
    }
    r = client.post("/detections", json=payload)
    assert r.status_code == 422


# ── Batch insert ──────────────────────────────────────────────────────────────

def test_insert_batch(client):
    batch = {
        "detections": [
            {"frame_id": 1, "label": "Rupture",    "confidence": 0.9,  "x": 10, "y": 20, "width": 50, "height": 40},
            {"frame_id": 2, "label": "Disconnect", "confidence": 0.85, "x": 30, "y": 40, "width": 60, "height": 50},
            {"frame_id": 3, "label": "Obstacle",   "confidence": 0.6,  "x": 5,  "y": 10, "width": 30, "height": 25},
        ]
    }
    r = client.post("/detections/batch", json=batch)
    assert r.status_code == 201
    assert r.json()["inserted"] == 3


# ── Query detections ──────────────────────────────────────────────────────────

def test_get_all_detections(client):
    _insert_sample(client)
    r = client.get("/detections")
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_filter_by_label(client):
    _insert_sample(client)
    r = client.get("/detections?label=Rupture")
    assert r.status_code == 200
    results = r.json()
    assert all(d["label"] == "Rupture" for d in results)


def test_filter_by_confidence(client):
    _insert_sample(client)
    r = client.get("/detections?min_confidence=0.85")
    assert r.status_code == 200
    results = r.json()
    assert all(d["confidence"] >= 0.85 for d in results)


def test_filter_limit(client):
    _insert_sample(client)
    r = client.get("/detections?limit=1")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ── Summary ───────────────────────────────────────────────────────────────────

def test_summary(client):
    _insert_sample(client)
    r = client.get("/detections/summary")
    assert r.status_code == 200
    data = r.json()
    assert "by_class" in data
    assert len(data["by_class"]) > 0
    first = data["by_class"][0]
    assert "label" in first
    assert "count" in first
    assert "avg_confidence" in first


# ── Delete ────────────────────────────────────────────────────────────────────

def test_clear_detections(client):
    _insert_sample(client)
    r = client.delete("/detections")
    assert r.status_code == 204
    r2 = client.get("/detections")
    assert r2.json() == []


# ── Metrics ───────────────────────────────────────────────────────────────────

def test_metrics_endpoint(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "apm_storage_detections_total" in r.text


# ── Helpers ───────────────────────────────────────────────────────────────────

def _insert_sample(client):
    batch = {
        "detections": [
            {"frame_id": 1, "label": "Rupture",    "confidence": 0.92, "x": 10, "y": 20, "width": 50, "height": 40},
            {"frame_id": 2, "label": "Disconnect", "confidence": 0.87, "x": 30, "y": 40, "width": 60, "height": 50},
            {"frame_id": 3, "label": "Obstacle",   "confidence": 0.55, "x": 5,  "y": 10, "width": 30, "height": 25},
        ]
    }
    client.post("/detections/batch", json=batch)
