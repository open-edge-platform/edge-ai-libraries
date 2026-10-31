# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ObjectDetector tests with Hugging Face and OpenVINO Model API mocked out."""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.core.object_detection import detector as detector_mod
from src.core.object_detection.detector import ObjectDetector

MODEL = "OpenVINO/yolox_s-fp16-ov"


def _bare_detector(tmp_path, class_names=("person", "car", "traffic_light"), class_filter=None):
    det = ObjectDetector.__new__(ObjectDetector)
    det.model_name = MODEL
    det.model_dir = str(tmp_path)
    det.model_path = tmp_path / "OpenVINO" / "yolox_s-fp16-ov"
    det.class_names = tuple(class_names)
    det.class_filter = class_filter
    det.detection_config = {"roi_consolidation": {"enabled": False}}
    det._local = threading.local()
    det.model = None
    return det


def _write_ir(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "yolox_s.xml").write_text("<net/>")
    (path / "yolox_s.bin").write_bytes(b"\0")


def test_downloads_only_ir_files_into_model_dir(tmp_path, monkeypatch):
    det = _bare_detector(tmp_path)
    calls = []

    def fake_snapshot_download(**kwargs):
        calls.append(kwargs)
        _write_ir(det.model_path)

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_snapshot_download)

    assert det._ensure_model_available() == det.model_path / "yolox_s.xml"
    assert calls == [
        {"repo_id": MODEL, "local_dir": str(det.model_path), "allow_patterns": ["*.xml", "*.bin"]}
    ]


def test_uses_cached_model_without_download(tmp_path, monkeypatch):
    det = _bare_detector(tmp_path)
    _write_ir(det.model_path)
    monkeypatch.setattr(
        "huggingface_hub.snapshot_download", MagicMock(side_effect=AssertionError("no download"))
    )

    assert det._ensure_model_available().name == "yolox_s.xml"


def test_rejects_repo_without_openvino_ir(tmp_path, monkeypatch):
    det = _bare_detector(tmp_path)
    monkeypatch.setattr("huggingface_hub.snapshot_download", lambda **_: None)

    with pytest.raises(FileNotFoundError, match="does not contain an OpenVINO IR model"):
        det._ensure_model_available()


def test_rejects_non_detection_models(tmp_path, monkeypatch):
    det = _bare_detector(tmp_path)
    det.device, det.confidence_threshold = "CPU", 0.5
    monkeypatch.setattr(detector_mod.Model, "create_model", lambda *a, **k: object())

    with pytest.raises(ValueError, match="is not an object detection model"):
        det._load_model(tmp_path / "m.xml")


def test_class_filter_must_match_model_labels(tmp_path):
    det = _bare_detector(tmp_path, class_filter=("person", "forklift"))

    with pytest.raises(ValueError, match="forklift.*Available classes: person, car, traffic_light"):
        det._validate_class_filter()


def test_class_filter_keeps_only_requested_classes(tmp_path):
    det = _bare_detector(tmp_path, class_filter=("person", "traffic_light"))
    det._infer = lambda image: SimpleNamespace(
        bboxes=np.array([[0, 0, 10, 10], [5, 5, 20, 20], [1, 1, 4, 4]]),
        scores=np.array([0.9, 0.8, 0.95]),
        labels=np.array([0, 1, 2]),
    )

    metadata = det.detect(np.zeros((32, 32, 3), dtype=np.uint8))

    assert [m["class_name"] for m in metadata] == ["person", "traffic_light"]
    assert [m["bbox"] for m in metadata] == [[0, 0, 10, 10], [1, 1, 4, 4]]


def test_infer_uses_one_request_per_thread(tmp_path):
    det = _bare_detector(tmp_path)
    compiled = MagicMock()
    compiled.create_infer_request.side_effect = lambda: MagicMock()
    adapter = SimpleNamespace(
        compiled_model=compiled,
        use_python_preprocessing=False,
        get_output_layers=lambda: {"boxes": None},
    )
    det.model = SimpleNamespace(
        inference_adapter=adapter,
        base_preprocess=lambda image: ({"image": image}, {}),
        postprocess=lambda raw, meta: raw,
    )

    det._infer(np.zeros((2, 2, 3)))
    det._infer(np.zeros((2, 2, 3)))
    worker = threading.Thread(target=det._infer, args=(np.zeros((2, 2, 3)),))
    worker.start()
    worker.join()

    assert compiled.create_infer_request.call_count == 2


def test_nms_only_sees_boxes_above_confidence_threshold():
    seen = {}

    def calculate_nms(boxes, scores, labels, include_boundaries=False):
        seen["scores"] = scores.tolist()
        return [1, 0]

    model = SimpleNamespace(
        params=SimpleNamespace(confidence_threshold=0.5), _calculate_nms=calculate_nms
    )
    ObjectDetector._prefilter_nms_by_confidence(model)

    keep = model._calculate_nms(
        boxes=np.zeros((4, 4)),
        scores=np.array([0.2, 0.9, 0.5, 0.7]),
        labels=np.zeros(4),
        include_boundaries=True,
    )

    assert seen["scores"] == [0.9, 0.7]
    assert keep == [3, 1]
