# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Configuration settings for BehavioralAnalysis Service."""

import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class DeploymentMode(str, Enum):
    """Supported deployment modes."""
    SEAWEEDFS_MQTT = "seaweedfs+mqtt"
    STANDALONE_API = "standalone+api"


class Settings(BaseSettings):
    """Service configuration loaded from environment variables."""

    # Service settings
    debug: bool = False
    log_level: str = "INFO"
    deployment_mode: DeploymentMode = DeploymentMode.STANDALONE_API

    # Pose confidence threshold
    pose_confidence_threshold: float = Field(default=0.5, alias="BA_CONFIDENCE")

    # Pose model settings
    yolo_pose_model: str = "/models/yolo_models/yolo26n-pose/yolo26n-pose.xml"
    gst_inference_device: str = Field(default="CPU", alias="BA_GST_DEVICE")

    # Frame analysis settings
    min_frames_for_detection: int = Field(default=3, alias="BA_MIN_FRAMES")
    max_frames_to_fetch: int = Field(default=20, alias="BA_MAX_FRAMES")
    pose_frames_count: int = Field(default=15, alias="BA_POSE_FRAMES")

    # SeaweedFS settings
    seaweedfs_endpoint: str = "http://localhost:8333"
    seaweedfs_bucket: str = "behavioral-frames"
    seaweedfs_access_key: str = ""
    seaweedfs_secret_key: str = ""

    # VLM settings
    vlm_endpoint: str = "http://ovms-vlm:8001"
    vlm_model_name: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    vlm_enabled: bool = False
    vlm_timeout: float = 300.0
    # Max concurrent VLM requests in flight against ovms-vlm. Continuous
    # batching is fine but unbounded fan-in lets the cache and per-request
    # latency grow without bound. 1–2 keeps OVMS responsive on a single
    # GPU.
    vlm_max_concurrency: int = 1
    vlm_max_tokens: int = 50
    vlm_temperature: float = 0.1
    vlm_max_image_size: int = 256

    # Pattern config file path
    pattern_config_path: str = "/app/config/patterns.yaml"

    # MQTT settings (for BA request/result queue)
    mqtt_host: str = "broker.scenescape.intel.com"
    mqtt_port: int = 1883
    ba_request_topic: str = "ba/requests"
    ba_result_topic: str = "ba/results"

    class Config:
        env_prefix = ""  # No prefix, use exact variable names
        case_sensitive = False
        populate_by_name = True  # Allow both field name and alias
    
    @property
    def use_seaweedfs(self) -> bool:
        """Check if SeaweedFS is enabled in current deployment mode."""
        return "seaweedfs" in self.deployment_mode.value
    
    @property
    def use_mqtt(self) -> bool:
        """Check if MQTT queue consumer is enabled in current deployment mode."""
        return "mqtt" in self.deployment_mode.value


def load_pattern_config(path: str) -> dict[str, Any]:
    """Load pattern definitions from YAML config file."""
    config_path = Path(path)
    if not config_path.exists():
        logger.warning(f"Pattern config not found: {path}, using defaults")
        return {}

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    patterns = config.get("patterns", {})
    enabled = {k: v for k, v in patterns.items() if v.get("enabled", True)}
    logger.info(f"Loaded {len(enabled)} enabled patterns from {path}")
    return patterns


def apply_vlm_settings(settings: Settings, path: str) -> None:
    """Apply VLM settings from the patterns YAML unless the corresponding env var is explicitly set."""
    config_path = Path(path)
    if not config_path.exists():
        return

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    vlm = config.get("vlm_settings")
    if not vlm:
        return

    field_map = {
        "endpoint": "vlm_endpoint",
        "model_name": "vlm_model_name",
        "timeout": "vlm_timeout",
        "max_tokens": "vlm_max_tokens",
        "temperature": "vlm_temperature",
        "max_image_size": "vlm_max_image_size",
        "max_concurrency": "vlm_max_concurrency",
    }
    applied = []
    for yaml_key, settings_attr in field_map.items():
        env_name = settings_attr.upper()
        if os.getenv(env_name) is not None:
            logger.info(
                f"Skipping YAML override for {settings_attr}: environment variable {env_name} is set."
            )
            continue

        if yaml_key in vlm:
            setattr(settings, settings_attr, vlm[yaml_key])
            applied.append(f"{yaml_key}={vlm[yaml_key]}")

    if applied:
        logger.info(f"VLM settings applied from config: {', '.join(applied)}")