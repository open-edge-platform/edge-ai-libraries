# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from src.core.utils import config_utils
from src.core.utils.config_utils import (
    _validate_config,
    parse_detection_classes,
    validate_detection_model_name,
)


def _detection_config(model_name, enabled=True, classes=None):
    return {"enabled": enabled, "model_name": model_name, "classes": classes}


@pytest.mark.parametrize(
    "model_name", ["OpenVINO/yolox_s-fp16-ov", "OpenVINO/YOLO11n-int8-ov", " OpenVINO/rtdetr_r50-fp16-ov "]
)
def test_accepts_openvino_namespace_models(model_name):
    assert validate_detection_model_name(model_name) == model_name.strip()


@pytest.mark.parametrize(
    "model_name",
    [
        "yolox_s",
        "Ultralytics/YOLO26",
        "openvino/yolox_s-fp16-ov",
        "OpenVINO/../yolox_s",
        "OpenVINO/a/b",
        "OpenVINO/.hidden",
        "OpenVINO/" + "a" * 97,
    ],
)
def test_rejects_models_outside_openvino_namespace(model_name):
    with pytest.raises(ValueError, match="'OpenVINO' namespace"):
        validate_detection_model_name(model_name)


def test_requires_detection_model_when_enabled():
    with pytest.raises(ValueError, match="MM_DATAPREP_DETECTION_MODEL_NAME"):
        _validate_config({}, _detection_config("  "))


def test_allows_missing_model_when_detection_disabled():
    config = _validate_config({}, _detection_config(None, enabled=False))

    assert config["object_detection"]["model_name"] is None


def test_parses_class_filter_case_and_space_insensitively():
    assert parse_detection_classes(" Person, traffic light,car,person ,") == (
        "person",
        "traffic_light",
        "car",
    )
    assert parse_detection_classes(" , ") is None


@pytest.mark.parametrize("classes", ["person;car", "../etc", "a" * 65])
def test_rejects_malformed_class_filter(classes):
    with pytest.raises(ValueError, match="MM_DATAPREP_DETECTION_CLASSES"):
        parse_detection_classes(classes)


def test_get_config_follows_environment_settings(monkeypatch):
    """Endpoint defaults come from MM_DATAPREP_* settings (no config file)."""
    from src.endpoints.video_processing.batch_ingest import _resolve_defaults

    monkeypatch.setattr(config_utils.settings, "ENABLE_OBJECT_DETECTION", False)
    monkeypatch.setattr(config_utils.settings, "FRAME_INTERVAL", 7)
    monkeypatch.setattr(config_utils.settings, "DETECTION_CLASSES", "person,car")

    config = config_utils.get_config()

    assert config["enable_object_detection"] is False
    assert config["object_detection"]["classes"] == ("person", "car")
    assert _resolve_defaults(None, None) == (7, False)
