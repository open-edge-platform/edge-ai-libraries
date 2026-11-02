# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the image embedding orchestration path.

The embedding client and object detector are mocked so these tests exercise the
orchestration logic (decode, optional crop metadata, sub-batching, content_type
tagging, None-embedding filtering) without loading a real model.
"""

import asyncio
import io

import pytest
from PIL import Image

import src.core.embedding.embedding_orchestrator as orch


def _png_bytes(size=(32, 32), color=(255, 0, 0)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class _FakeClient:
    """Records calls and returns deterministic fake embeddings."""

    def __init__(self, supports_image=True, none_indices=()):
        self.supports_image = supports_image
        self._none_indices = set(none_indices)
        self.stored = []  # list of (embeddings, metadatas)

    def generate_embeddings_for_images(self, images, metrics_out=False):
        return [
            None if i in self._none_indices else [0.1, 0.2, 0.3, 0.4]
            for i in range(len(images))
        ]

    def store_frame_embeddings(self, embeddings, metadatas):
        self.stored.append((embeddings, metadatas))
        base = len(self.stored) * 1000
        return [f"id_{base + i}" for i in range(len(embeddings))]


class _FakeDetector:
    def __init__(self, detections):
        self._detections = detections

    def detect(self, image, return_metadata=True):
        return self._detections


def _run(**overrides):
    kwargs = dict(
        image_content=_png_bytes(),
        bucket_name="b1",
        video_id="dp_image_1",
        filename="pic.png",
        enable_object_detection=False,
        detection_confidence=0.85,
        tags=["t1"],
    )
    kwargs.update(overrides)
    return asyncio.run(orch.generate_image_embedding_from_content(**kwargs))


def test_full_image_only_no_detection(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(orch, "get_embedding_client", lambda: client)
    monkeypatch.setattr(orch, "get_global_detector", lambda *a, **k: None)

    ids = _run(enable_object_detection=False)

    assert len(ids) == 1
    embeddings, metadatas = client.stored[0]
    assert len(embeddings) == 1
    md = metadatas[0]
    assert md["content_type"] == "image"
    assert md["frame_type"] == "full_frame"
    assert md["video_id"] == "dp_image_1"
    assert md["filename"] == "pic.png" and md["video_name"] == "pic.png"
    assert md["tags"] == ["t1"]


def test_detection_adds_crop_embeddings(monkeypatch):
    client = _FakeClient()
    detector = _FakeDetector(
        [
            {
                "bbox": [1, 1, 20, 20],
                "confidence": 0.9,
                "class_id": 3,
                "class_name": "car",
                "merged_boxes_count": 1,
                "context_expansion_applied": False,
            }
        ]
    )
    monkeypatch.setattr(orch, "get_embedding_client", lambda: client)
    monkeypatch.setattr(orch, "get_global_detector", lambda *a, **k: detector)

    ids = _run(enable_object_detection=True)

    # full image + 1 crop
    assert len(ids) == 2
    _, metadatas = client.stored[0]
    crop_md = metadatas[1]
    assert crop_md["frame_type"] == "detected_crop"
    assert crop_md["is_detected_crop"] is True
    assert crop_md["crop_index"] == 0
    assert crop_md["detected_label"] == "car"
    assert crop_md["crop_bbox"] == [1, 1, 20, 20]
    assert crop_md["content_type"] == "image"


def test_tiny_crop_is_skipped(monkeypatch):
    client = _FakeClient()
    detector = _FakeDetector(
        [{"bbox": [0, 0, 3, 3], "confidence": 0.9, "class_id": 1, "class_name": "x"}]
    )
    monkeypatch.setattr(orch, "get_embedding_client", lambda: client)
    monkeypatch.setattr(orch, "get_global_detector", lambda *a, **k: detector)

    ids = _run(enable_object_detection=True)
    # crop < 10px on a side is dropped -> only the full image remains
    assert len(ids) == 1


def test_none_embeddings_are_filtered(monkeypatch):
    client = _FakeClient(none_indices=(0,))
    monkeypatch.setattr(orch, "get_embedding_client", lambda: client)
    monkeypatch.setattr(orch, "get_global_detector", lambda *a, **k: None)

    ids = _run(enable_object_detection=False)
    # the single image embedding returned None -> nothing stored
    assert ids == []
    assert client.stored == []


def test_unsupported_model_raises(monkeypatch):
    client = _FakeClient(supports_image=False)
    monkeypatch.setattr(orch, "get_embedding_client", lambda: client)
    monkeypatch.setattr(orch, "get_global_detector", lambda *a, **k: None)

    with pytest.raises(ValueError):
        _run()


def test_invalid_image_bytes_raise(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(orch, "get_embedding_client", lambda: client)
    monkeypatch.setattr(orch, "get_global_detector", lambda *a, **k: None)

    with pytest.raises(ValueError):
        _run(image_content=b"not-an-image")


def test_subbatching_respects_batch_size(monkeypatch):
    client = _FakeClient()
    detector = _FakeDetector(
        [
            {
                "bbox": [1, 1, 25, 25],
                "confidence": 0.9,
                "class_id": i,
                "class_name": f"c{i}",
                "merged_boxes_count": 1,
                "context_expansion_applied": False,
            }
            for i in range(3)
        ]
    )
    monkeypatch.setattr(orch, "get_embedding_client", lambda: client)
    monkeypatch.setattr(orch, "get_global_detector", lambda *a, **k: detector)
    monkeypatch.setattr(orch.settings, "EMBEDDING_BATCH_SIZE", 2)

    ids = _run(enable_object_detection=True)
    # 1 full image + 3 crops = 4 items -> ceil(4/2) = 2 store calls
    assert len(ids) == 4
    assert len(client.stored) == 2
