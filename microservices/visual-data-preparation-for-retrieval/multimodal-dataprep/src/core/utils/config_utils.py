# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Configuration Utilities Module

Builds the validated processing / object-detection configuration from the
``MM_DATAPREP_*`` environment settings (see ``src.common.settings``). There is
no configuration file: environment variables are the single source of truth.

Usage:
    from src.core.utils.config_utils import get_config

    config = get_config()
"""

import re
from typing import Optional, Tuple

from src.common import logger, settings

# Object detection models are pulled from the Hugging Face "OpenVINO" namespace
# (OpenVINO/<repo>). The repo name also becomes a directory name under
# the model directory, so keep it to Hugging Face's safe repo-name characters.
DETECTION_MODEL_NAMESPACE = "OpenVINO"
DETECTION_MODEL_NAME_RE = re.compile(r"OpenVINO/[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
DETECTION_MODEL_FORMAT = "OpenVINO/<repo>"

DETECTION_CLASS_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,63}")
MAX_DETECTION_CLASSES = 200


def normalize_class_name(name: str) -> str:
    """Normalize a class label for matching (case-, space- and hyphen-insensitive)."""
    return re.sub(r"[\s-]+", "_", str(name).strip()).lower()


def validate_detection_model_name(model_name: Optional[str]) -> Optional[str]:
    """Return the stripped model repo id, or None when unset.

    Raises:
        ValueError: If the name is not an ``OpenVINO/<repo>`` Hugging Face repo id.
    """
    if model_name is None:
        return None
    if not isinstance(model_name, str):
        raise ValueError(f"MM_DATAPREP_DETECTION_MODEL_NAME must be a string, got: {model_name!r}")
    model_name = model_name.strip()
    if not model_name:
        return None
    if not DETECTION_MODEL_NAME_RE.fullmatch(model_name) or ".." in model_name:
        raise ValueError(
            "MM_DATAPREP_DETECTION_MODEL_NAME must be a Hugging Face model repo in the "
            f"'{DETECTION_MODEL_NAMESPACE}' namespace ({DETECTION_MODEL_FORMAT}), "
            f"got: {model_name!r}"
        )
    return model_name


def parse_detection_classes(value) -> Optional[Tuple[str, ...]]:
    """Parse the optional class filter (comma-separated string or list).

    Returns:
        Tuple of normalized class names, or None to keep every class.

    Raises:
        ValueError: If a class name is malformed or the list is too long.
    """
    if value is None:
        return None
    items = value.split(",") if isinstance(value, str) else list(value)
    names = [str(item).strip() for item in items if str(item).strip()]
    if not names:
        return None
    if len(names) > MAX_DETECTION_CLASSES:
        raise ValueError(
            f"MM_DATAPREP_DETECTION_CLASSES accepts at most {MAX_DETECTION_CLASSES} names, "
            f"got {len(names)}"
        )
    for name in names:
        if not DETECTION_CLASS_NAME_RE.fullmatch(name):
            raise ValueError(
                "MM_DATAPREP_DETECTION_CLASSES entries may contain only letters, digits, "
                f"spaces, '_' or '-' (max 64 chars), got: {name!r}"
            )
    return tuple(dict.fromkeys(normalize_class_name(name) for name in names))


def get_config() -> dict:
    """
    Get the complete validated configuration from environment settings.

    Returns:
        Dictionary containing processing settings plus an ``object_detection`` section.

    Raises:
        ValueError: If configuration is invalid
    """
    try:
        processing_config = {
            "frame_interval": settings.FRAME_INTERVAL,
            "enable_object_detection": settings.ENABLE_OBJECT_DETECTION,
            "detection_confidence": settings.DETECTION_CONFIDENCE,
            "frames_temp_dir": settings.FRAMES_TEMP_DIR,
            "videos_temp_dir": settings.VIDEOS_TEMP_DIR,
            "metadata_temp_dir": settings.METADATA_TEMP_DIR,
        }

        object_detection_config = {
            "enabled": bool(settings.ENABLE_OBJECT_DETECTION),
            "device": settings.DETECTION_DEVICE or "CPU",
            "confidence_threshold": settings.DETECTION_CONFIDENCE,
            "model_dir": settings.DETECTION_MODEL_DIR,
            "model_name": settings.DETECTION_MODEL_NAME,
            "classes": settings.DETECTION_CLASSES,
            "roi_consolidation": {
                "enabled": bool(settings.ROI_CONSOLIDATION_ENABLED),
                "iou_threshold": (
                    settings.ROI_CONSOLIDATION_IOU_THRESHOLD
                    if settings.ROI_CONSOLIDATION_IOU_THRESHOLD is not None
                    else 0.2
                ),
                "class_aware": bool(settings.ROI_CONSOLIDATION_CLASS_AWARE),
                "context_scale": (
                    settings.ROI_CONSOLIDATION_CONTEXT_SCALE
                    if settings.ROI_CONSOLIDATION_CONTEXT_SCALE is not None
                    else 0.2
                ),
            },
        }

        validated_config = _validate_config(processing_config, object_detection_config)

        logger.debug(f"Complete configuration loaded and validated: {validated_config}")
        return validated_config

    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        raise ValueError(f"Failed to load configuration: {e}")


def _validate_config(processing_config: dict, object_detection_config: dict) -> dict:
    """
    Validate and sanitize configuration parameters.

    Args:
        processing_config: Processing configuration dictionary
        object_detection_config: Object detection configuration dictionary

    Returns:
        Validated configuration dictionary

    Raises:
        ValueError: If configuration is invalid
    """
    validated_config = processing_config.copy()

    frame_interval = validated_config.get("frame_interval", 15)
    if not isinstance(frame_interval, int) or frame_interval < 1:
        raise ValueError(f"frame_interval must be a positive integer, got: {frame_interval}")
    validated_config["frame_interval"] = frame_interval

    detection_confidence = validated_config.get("detection_confidence", 0.85)
    if not isinstance(detection_confidence, (int, float)) or not 0.0 <= detection_confidence <= 1.0:
        raise ValueError(
            f"detection_confidence must be between 0.0 and 1.0, got: {detection_confidence}"
        )
    validated_config["detection_confidence"] = float(detection_confidence)

    if validated_config.get("enable_object_detection") is not None:
        validated_config["enable_object_detection"] = bool(
            validated_config["enable_object_detection"]
        )

    # Object detection has no default model: require an explicit OpenVINO HF repo.
    object_detection_config = dict(object_detection_config)
    model_name = validate_detection_model_name(object_detection_config.get("model_name"))
    if object_detection_config.get("enabled") and model_name is None:
        raise ValueError(
            "Object detection is enabled but no detection model is configured. Set "
            "MM_DATAPREP_DETECTION_MODEL_NAME to a Hugging Face OpenVINO detection model "
            f"({DETECTION_MODEL_FORMAT}) or disable detection with "
            "MM_DATAPREP_ENABLE_OBJECT_DETECTION=false."
        )
    object_detection_config["model_name"] = model_name
    object_detection_config["classes"] = parse_detection_classes(
        object_detection_config.get("classes")
    )

    validated_config["object_detection"] = object_detection_config

    logger.debug("Configuration validation successful")
    return validated_config
