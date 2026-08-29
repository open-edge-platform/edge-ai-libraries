# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile
import pytest

from src.sqlite_client import SQLiteClient


@pytest.fixture
def db():
    tmp = tempfile.mktemp(suffix=".db")
    client = SQLiteClient(tmp)
    yield client
    os.unlink(tmp)


def test_insert_and_query(db):
    db.insert_detection(1, "Rupture", 0.9, 10, 20, 50, 40)
    results = db.get_detections()
    assert len(results) == 1
    assert results[0]["label"] == "Rupture"
    assert results[0]["confidence"] == pytest.approx(0.9)


def test_insert_many(db):
    records = [
        {"frame_id": i, "label": "Deformation", "confidence": 0.5 + i * 0.05,
         "x": i, "y": i, "width": 10, "height": 10}
        for i in range(5)
    ]
    count = db.insert_many(records)
    assert count == 5
    assert db.count() == 5


def test_filter_by_label(db):
    db.insert_detection(1, "Rupture",    0.9,  10, 10, 50, 50)
    db.insert_detection(2, "Disconnect", 0.85, 20, 20, 60, 60)
    results = db.get_detections(label="Rupture")
    assert len(results) == 1
    assert results[0]["label"] == "Rupture"


def test_filter_by_confidence(db):
    db.insert_detection(1, "Rupture", 0.9,  10, 10, 50, 50)
    db.insert_detection(2, "Obstacle", 0.4, 20, 20, 30, 30)
    results = db.get_detections(min_confidence=0.8)
    assert len(results) == 1
    assert results[0]["label"] == "Rupture"


def test_summary(db):
    db.insert_detection(1, "Rupture", 0.9, 10, 10, 50, 50)
    db.insert_detection(2, "Rupture", 0.8, 10, 10, 50, 50)
    db.insert_detection(3, "Obstacle", 0.5, 20, 20, 30, 30)
    summary = db.get_summary()
    by_class = {c["label"]: c for c in summary["by_class"]}
    assert by_class["Rupture"]["count"] == 2
    assert by_class["Obstacle"]["count"] == 1


def test_clear(db):
    db.insert_detection(1, "Rupture", 0.9, 10, 10, 50, 50)
    db.clear()
    assert db.count() == 0


def test_limit(db):
    for i in range(10):
        db.insert_detection(i, "Deformation", 0.6, i, i, 20, 20)
    results = db.get_detections(limit=3)
    assert len(results) == 3
