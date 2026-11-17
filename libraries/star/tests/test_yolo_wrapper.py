# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from semantic_img_comp.utils import yolo_wrapper
from semantic_img_comp.utils.yolo_wrapper import run_rtdetr, run_yolo


class _FakeTensor:
    def __init__(self, arr):
        self._arr = np.asarray(arr)

    def cpu(self):
        return self

    def numpy(self):
        return self._arr


class _FakeBoxes:
    def __init__(self, boxes, confs, classes):
        self.xyxy = _FakeTensor(boxes)
        self.conf = _FakeTensor(confs)
        self.cls = _FakeTensor(classes)


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class _FakeYolo:
    def __init__(self, boxes, confs, classes):
        self._result = _FakeResult(_FakeBoxes(boxes, confs, classes))
        self.calls = []

    def predict(self, img, **kwargs):
        self.calls.append((img, kwargs))
        if isinstance(img, list):
            return [self._result for _ in img]
        return [self._result]


def _cfg(tile_overlap=None, allowed_classes=None):
    return SimpleNamespace(
        app=SimpleNamespace(device="cpu"),
        model=SimpleNamespace(
            pre_comp_conf=0.25,
            iou_threshold=0.45,
            max_detections=100,
            valid_obj_categories=allowed_classes,
            tile_overlap=tile_overlap,
            tile_batch_size=8,
        ),
    )


def test_run_yolo_non_tile_filters_classes_and_returns_tuples():
    yolo = _FakeYolo(
        boxes=[[1, 2, 10, 20], [3, 4, 8, 9]],
        confs=[0.9, 0.8],
        classes=[1, 2],
    )
    img = np.zeros((16, 16, 3), dtype=np.uint8)

    dets = run_yolo(img, yolo, _cfg(allowed_classes={2}), tile_size=None, imgsz=320)

    assert dets == [(3.0, 4.0, 8.0, 9.0, 0.8, 2)]
    assert yolo.calls[0][1]["imgsz"] == 320


def test_run_yolo_tile_mode_defaults_none_overlap_to_zero():
    yolo = _FakeYolo(boxes=[[0, 0, 1, 1]], confs=[0.7], classes=[0])
    img = np.zeros((4, 4, 3), dtype=np.uint8)

    dets = run_yolo(img, yolo, _cfg(tile_overlap=None), tile_size=2, imgsz=160)

    assert len(dets) == 4
    assert (0.0, 0.0, 1.0, 1.0, 0.7, 0) in dets
    assert (2.0, 0.0, 3.0, 1.0, 0.7, 0) in dets
    assert (0.0, 2.0, 1.0, 3.0, 0.7, 0) in dets
    assert (2.0, 2.0, 3.0, 3.0, 0.7, 0) in dets


def test_run_yolo_rejects_invalid_tile_overlap():
    yolo = _FakeYolo(boxes=[[0, 0, 1, 1]], confs=[0.5], classes=[0])
    img = np.zeros((4, 4, 3), dtype=np.uint8)

    with pytest.raises(ValueError, match="tile_overlap must be smaller than tile_size"):
        run_yolo(img, yolo, _cfg(tile_overlap=8), tile_size=8)


def test_run_yolo_tile_mode_accepts_grayscale_2d_images(caplog):
    yolo = _FakeYolo(boxes=[[0, 0, 1, 1]], confs=[0.7], classes=[0])
    img_gray = np.zeros((4, 4), dtype=np.uint8)
    caplog.set_level("DEBUG")

    dets = run_yolo(img_gray, yolo, _cfg(tile_overlap=None), tile_size=2, imgsz=160)

    assert len(dets) == 4
    seen_shapes = []
    for call_img, _ in yolo.calls:
        if isinstance(call_img, list):
            seen_shapes.extend(tile.shape for tile in call_img)
        else:
            seen_shapes.append(call_img.shape)
    assert seen_shapes
    assert all(shape == (2, 2, 3) for shape in seen_shapes)
    assert "Auto-expanded YOLO input shape" in caplog.text


def test_run_yolo_tile_mode_batches_predictions():
    yolo = _FakeYolo(boxes=[[0, 0, 1, 1]], confs=[0.7], classes=[0])
    cfg = _cfg(tile_overlap=0)
    cfg.model.tile_batch_size = 3
    img = np.zeros((4, 4, 3), dtype=np.uint8)

    dets = run_yolo(img, yolo, cfg, tile_size=2, imgsz=160)

    assert len(dets) == 4
    assert len(yolo.calls) == 2
    assert isinstance(yolo.calls[0][0], list)
    assert len(yolo.calls[0][0]) == 3
    assert len(yolo.calls[1][0]) == 1


def test_run_yolo_tile_batch_size_1_sends_single_array_each_call():
    """batch_size=1 must pass individual numpy arrays, not lists — identical to legacy per-tile path."""
    yolo = _FakeYolo(boxes=[[0, 0, 1, 1]], confs=[0.7], classes=[0])
    cfg = _cfg(tile_overlap=0)
    cfg.model.tile_batch_size = 1
    img = np.zeros((4, 4, 3), dtype=np.uint8)  # 4 tiles of 2x2

    dets = run_yolo(img, yolo, cfg, tile_size=2, imgsz=160)

    assert len(dets) == 4
    # Each call receives a plain ndarray, not a list
    assert len(yolo.calls) == 4
    assert all(isinstance(call_img, np.ndarray) for call_img, _ in yolo.calls)


def test_tile_nms_is_class_agnostic_for_overlapping_boxes():
    dets = [
        (0.0, 0.0, 10.0, 10.0, 0.95, 3),
        (1.0, 1.0, 11.0, 11.0, 0.90, 1),
    ]

    kept = yolo_wrapper._nms_classwise(dets, iou_threshold=0.5)

    assert kept == [(0.0, 0.0, 10.0, 10.0, 0.95, 3)]


def test_tile_nms_suppresses_nested_boxes_with_iom_rule():
    dets = [
        (0.0, 0.0, 100.0, 100.0, 0.95, 3),
        (10.0, 10.0, 30.0, 30.0, 0.90, 1),
    ]

    kept = yolo_wrapper._nms_classwise(dets, iou_threshold=0.1)

    assert kept == [(0.0, 0.0, 100.0, 100.0, 0.95, 3)]


def test_tile_nms_keeps_nested_boxes_when_iom_rule_disabled():
    dets = [
        (0.0, 0.0, 100.0, 100.0, 0.95, 3),
        (10.0, 10.0, 30.0, 30.0, 0.90, 1),
    ]

    kept = yolo_wrapper._nms_classwise(dets, iou_threshold=0.1, iom_threshold=1.0)

    assert len(kept) == 2


def test_run_rtdetr_requires_optional_transformers_dependency(monkeypatch):
    monkeypatch.setattr(yolo_wrapper, "_RTDETR_IMPORT_ERROR", ImportError("transformers missing"))

    with pytest.raises(ImportError, match="transformers"):
        run_rtdetr(Image.new("RGB", (4, 4)), processor=object(), model=object())


