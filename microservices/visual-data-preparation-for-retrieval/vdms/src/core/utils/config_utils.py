# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Configuration Utilities Module

This module provides configuration loading, validation, and caching utilities.
Supports both SDK mode (direct integration) and API mode (HTTP-based) processing.

Functions:
- read_config(): Read configuration files (YAML/JSON)
- get_config(): Get complete validated configuration with environment variable overrides
- clear_config_cache(): Clear configuration cache to force reload
- _load_base_config(): Internal function to load and cache base configuration
- _get_config_value(): Internal function to get config values with precedence
- _validate_config(): Internal function to validate configuration parameters

Usage:
    from src.core.utils.config_utils import get_config, read_config
    
    # Get complete configuration
    config = get_config()
    
    # Read specific config file
    custom_config = read_config("/path/to/config.yaml")
"""

import json
import pathlib
from typing import Optional, List, Dict, Any

import yaml

from src.common import logger, settings


def read_config(config_file: str | pathlib.Path, type: str = "yaml") -> dict | None:
    """Takes a yaml/json file path as input. Parses and returns
    the file content as dictionary.
    
    Args:
        config_file: Path to configuration file
        type: File type ('yaml' or 'json'), auto-detected from extension if not specified
        
    Returns:
        Configuration dictionary or None if error occurred
    """
    path = pathlib.Path(config_file)
    config: dict = {}

    try:
        with open(path.absolute(), "r") as f:
            if type == "yaml" or path.suffix.lower() == ".yaml":
                config = yaml.safe_load(f)
            elif type == "json" or path.suffix.lower() == ".json":
                config = json.load(f)

    except Exception as ex:
        logger.error(f"Error while reading config file: {ex}")
        config = None

    return config


def _load_base_config() -> dict:
    """Load base configuration from file once and cache it
    
    Returns:
        Base configuration dictionary (cached)
    """
    if not hasattr(_load_base_config, "_cache"):
        try:
            config = read_config(settings.CONFIG_FILEPATH, type="yaml")
            if not config:
                logger.warning("Could not load config file, using empty config")
                config = {}
            _load_base_config._cache = config
        except Exception as e:
            logger.error(f"Error loading base config file: {e}")
            _load_base_config._cache = {}
    
    return _load_base_config._cache


def _get_config_value(setting_name: str, config_path: list):
    """
    Get configuration value with precedence: env_var > config_file
    
    Args:
        setting_name: Name of the setting in environment/settings
        config_path: Path in config dict (e.g., ["frame_processing", "frame_interval"])
        
    Returns:
        Configuration value from environment or config file
    """
    # First try environment/settings
    env_value = getattr(settings, setting_name, None)
    if env_value is not None:
        return env_value
    
    # Then try config file
    config = _load_base_config()
    config_value = config
    for key in config_path:
        if isinstance(config_value, dict) and key in config_value:
            config_value = config_value[key]
        else:
            config_value = None
            break
    
    return config_value


def get_config() -> dict:
    """
    Get complete configuration with validation.
    Combines processing config with object detection configuration.
    Environment variables override config file settings.
    
    Returns:
        Dictionary containing complete validated configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    try:
        config = _load_base_config()
        
        # Build processing configuration
        processing_config = {
            "frame_interval": _get_config_value("FRAME_INTERVAL", ["frame_processing", "frame_interval"]) or 15,
            "enable_object_detection": _get_config_value("ENABLE_OBJECT_DETECTION", ["frame_processing", "enable_object_detection"]),
            "detection_confidence": _get_config_value("DETECTION_CONFIDENCE", ["frame_processing", "detection_confidence"]) or 0.85,
            "frames_temp_dir": _get_config_value("FRAMES_TEMP_DIR", ["frame_processing", "shared_volume", "frames_temp_dir"]) or "/tmp/dataprep/vdms_frames",
            "frames_bucket": _get_config_value("effective_bucket_name", ["frame_processing", "object_storage", "frames_bucket"]) or settings.effective_bucket_name,
            "fallback_order": _get_config_value("STRATEGY_FALLBACK_ORDER", ["frame_processing", "fallback_order"]) or ["shared_volume", "object_storage", "base64_transfer"]
        }
        
        # Build object detection configuration
        object_detection_config = {
            "enabled": processing_config["enable_object_detection"] if processing_config["enable_object_detection"] is not None else False,
            "device": _get_config_value("DETECTION_DEVICE", ["object_detection", "device"]) or "CPU",
            "confidence_threshold": processing_config["detection_confidence"],
            "nms_threshold": _get_config_value("NMS_THRESHOLD", ["object_detection", "nms_threshold"]) or 0.45,
            "input_size": _get_config_value("DETECTION_INPUT_SIZE", ["object_detection", "input_size"]) or [640, 640],
            "model_dir": settings.DETECTION_MODEL_DIR,  # Environment variable takes highest priority
            "model_name": _get_config_value("DETECTION_MODEL_NAME", ["object_detection", "model_name"]),  # No default - must be explicitly set
            "roi_consolidation": {
                "enabled": _get_config_value(
                    "ROI_CONSOLIDATION_ENABLED",
                    ["object_detection", "roi_consolidation", "enabled"],
                ),
                "iou_threshold": _get_config_value(
                    "ROI_CONSOLIDATION_IOU_THRESHOLD",
                    ["object_detection", "roi_consolidation", "iou_threshold"],
                )
                or 0.2,
                "class_aware": _get_config_value(
                    "ROI_CONSOLIDATION_CLASS_AWARE",
                    ["object_detection", "roi_consolidation", "class_aware"],
                )
                or False,
                "context_scale": _get_config_value(
                    "ROI_CONSOLIDATION_CONTEXT_SCALE",
                    ["object_detection", "roi_consolidation", "context_scale"],
                )
                or 0.2,
            },
        }

        if object_detection_config["roi_consolidation"]["enabled"] is None:
            object_detection_config["roi_consolidation"]["enabled"] = False
        
        # Validate configuration
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
    
    # Validate frame_interval
    frame_interval = validated_config.get("frame_interval", 15)
    if not isinstance(frame_interval, int) or frame_interval < 1:
        raise ValueError(f"frame_interval must be a positive integer, got: {frame_interval}")
    validated_config["frame_interval"] = frame_interval
    
    # Validate detection_confidence
    detection_confidence = validated_config.get("detection_confidence", 0.85)
    if not isinstance(detection_confidence, (int, float)) or not 0.0 <= detection_confidence <= 1.0:
        raise ValueError(f"detection_confidence must be between 0.0 and 1.0, got: {detection_confidence}")
    validated_config["detection_confidence"] = float(detection_confidence)
    
    # Validate boolean settings
    bool_settings = ["enable_object_detection"]
    for setting in bool_settings:
        if setting in validated_config and validated_config[setting] is not None:
            validated_config[setting] = bool(validated_config[setting])
    
    # Add object detection config
    validated_config["object_detection"] = object_detection_config
    
    logger.debug("Configuration validation successful")
    return validated_config


def clear_config_cache():
    """Clear the configuration cache to force reload from file."""
    if hasattr(_load_base_config, "_cache"):
        delattr(_load_base_config, "_cache")
        logger.debug("Configuration cache cleared")