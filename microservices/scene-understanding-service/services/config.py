# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Configuration service for Store-wide Loss Prevention."""

import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional

import structlog
import yaml

try:
    from stream_density import expand_scene_configs
except ImportError:
    def expand_scene_configs(base_scene: dict, density: int) -> list:
        """Inline fallback when stream_density module is not installed."""
        if density <= 1:
            return [base_scene]
        configs = []
        base_name = base_scene.get("scene_name", "scene")
        base_cams = base_scene.get("cameras", [base_scene.get("camera_name", "camera")])
        base_camera = base_cams[0] if isinstance(base_cams, list) else base_cams
        for i in range(1, density + 1):
            suffix = "" if i == 1 else f"-{i}"
            scene = dict(base_scene)
            scene["scene_name"] = f"{base_name}{suffix}"
            cam_name = f"{base_camera}{suffix}"
            if "cameras" in scene and isinstance(scene["cameras"], list):
                scene["cameras"] = [cam_name]
            else:
                scene["camera_name"] = cam_name
            configs.append(scene)
        return configs

logger = structlog.get_logger(__name__)


class ConfigService:
    """Loads and exposes scene-config.yaml (the single, self-contained service config).

    The service owns this file end-to-end: MQTT connection, SceneScape API, and the
    scenes/cameras/zones it monitors. It is intentionally decoupled from how SceneScape
    itself is provisioned, so any consuming application can supply its own scene-config.yaml
    regardless of its SceneScape deployment.
    """

    def __init__(self) -> None:
        self._config_dir = Path(os.environ.get("CONFIG_DIR", "/app/configs"))
        if not self._config_dir.exists():
            # Fallback for local development: configs/ next to src/
            self._config_dir = Path(__file__).resolve().parent.parent.parent / "configs"
        _cfg = self._load_yaml("scene-config.yaml")
        self._app_cfg = _cfg
        self._zone_cfg = _cfg
        self._rules_settings = self._load_rules_settings()

        # Stream density: number of scene copies to run
        self._stream_density = int(self._zone_cfg.get("stream_density", 1))

        # Multi-scene support: build scene configs list
        self._scene_configs: List[dict] = self._zone_cfg.get("scenes", [])
        # Backward compat: if old flat format, wrap into scenes list
        if not self._scene_configs and self._zone_cfg.get("scene_name"):
            base = {
                "scene_name": self._zone_cfg["scene_name"],
                "scene_zip": self._zone_cfg.get("scene_zip", ""),
                "cameras": [self._zone_cfg["camera_name"]] if self._zone_cfg.get("camera_name") else [],
                "video_file": self._zone_cfg.get("video_file", ""),
                "zones": self._zone_cfg.get("zones", {}),
            }
            if expand_scene_configs:
                self._scene_configs = expand_scene_configs(base, self._stream_density)
            else:
                self._scene_configs = [base]

        # Zone name → type per scene: {"scene_name": {"region_name": "HIGH_VALUE"}}
        self._zone_name_map_per_scene: Dict[str, Dict[str, str]] = {}
        for sc in self._scene_configs:
            name = sc.get("scene_name", "")
            self._zone_name_map_per_scene[name] = dict(sc.get("zones", {}))

        # Flat zone name map (all scenes merged) for backward compat
        self._zone_name_map: Dict[str, str] = {}
        for sc in self._scene_configs:
            self._zone_name_map.update(sc.get("zones", {}))

        # Runtime zone map: {region_uuid: {name, type, scene_id}} — populated by SceneScapeClient
        self._zones: Dict[str, dict] = {}
        # Resolved scene_name → scene_id mapping
        self._resolved_scene_ids: Dict[str, str] = {}  # scene_name → scene_uuid
        self._zone_lock = threading.Lock()

        logger.info(
            "ConfigService initialized",
            store_id=self.get_store_id(),
            num_scenes=len(self._scene_configs),
            num_zones=len(self._zone_name_map),
        )

    # ---- loaders ----
    def _load_yaml(self, filename: str) -> dict:
        path = self._config_dir / filename
        if not path.exists():
            logger.warning("Config file not found, using empty dict", path=str(path))
            return {}
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}

    def _load_json(self, filename: str) -> dict:
        path = self._config_dir / filename
        if not path.exists():
            logger.warning("Config file not found, using empty dict", path=str(path))
            return {}
        with open(path, "r") as f:
            return json.load(f)

    def _load_rules_settings(self) -> dict:
        path = self._config_dir / "rules.yaml"
        if not path.exists():
            logger.warning("rules.yaml not found, using empty settings")
            self._session_flag_defs: Dict[str, dict] = {}
            self._service_defs: Dict[str, dict] = {}
            self._rules_variables: Dict[str, object] = {}
            return {}
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        self._session_flag_defs = data.get("session_flags", {})
        self._service_defs = data.get("services", {})
        self._rules_variables = data.get("variables", {}) or {}
        # Merge `variables` into the runtime settings dict so existing
        # callers that look up rule thresholds via get_rules_config()
        # transparently see the same values the rule engine uses.
        # Explicit `settings:` entries still take precedence.
        merged = {**self._rules_variables, **(data.get("settings", {}) or {})}
        return merged

    # ---- store ----
    def get_store_id(self) -> str:
        return os.environ.get("STORE_ID", "store_001")

    # ---- cameras (derived from scene configs) ----
    def get_cameras(self) -> List[dict]:
        cameras = []
        for sc in self._scene_configs:
            for cam in sc.get("cameras", []):
                cameras.append({
                    "name": cam,
                    "number": len(cameras) + 1,
                    "description": sc.get("scene_name", ""),
                    "data_topic": f"scenescape/data/camera/{cam}",
                    "image_topic": f"scenescape/image/camera/{cam}",
                })
        if not cameras:
            return self._app_cfg.get("cameras", [])
        return cameras

    def get_camera_topics(self) -> List[str]:
        return [c["data_topic"] for c in self.get_cameras()]

    def get_image_topics(self) -> List[str]:
        return [c["image_topic"] for c in self.get_cameras()]

    # ---- mqtt ----
    def get_mqtt_config(self) -> dict:
        return self._app_cfg.get("mqtt", {})

    def get_mqtt_host(self) -> str:
        return os.environ.get(
            "MQTT_HOST", self.get_mqtt_config().get("host", "localhost")
        )

    def get_mqtt_port(self) -> int:
        return int(
            os.environ.get("MQTT_PORT", self.get_mqtt_config().get("port", 1883))
        )

    def get_scene_name(self) -> Optional[str]:
        """Return first configured scene name (backward compat). Use get_scene_names() for multi-scene."""
        if self._scene_configs:
            return self._scene_configs[0].get("scene_name")
        return None

    def get_scene_names(self) -> List[str]:
        """Return all configured scene names."""
        return [sc.get("scene_name", "") for sc in self._scene_configs if sc.get("scene_name")]

    def get_scene_configs(self) -> List[dict]:
        """Return the list of scene configuration dicts."""
        return list(self._scene_configs)

    def get_stream_density(self) -> int:
        """Return the configured stream density."""
        return self._stream_density

    def get_scene_id(self) -> Optional[str]:
        """Return first resolved scene UUID (backward compat). Use get_scene_ids() for multi-scene."""
        if self._resolved_scene_ids:
            return next(iter(self._resolved_scene_ids.values()))
        return None

    def get_scene_ids(self) -> Dict[str, str]:
        """Return {scene_name: scene_uuid} mapping for all resolved scenes."""
        return dict(self._resolved_scene_ids)

    def get_scene_id_for_name(self, scene_name: str) -> Optional[str]:
        """Return scene UUID for a given scene name."""
        return self._resolved_scene_ids.get(scene_name)

    def get_accepted_scene_ids(self) -> set:
        """Return set of all resolved scene UUIDs to accept MQTT messages from."""
        return set(self._resolved_scene_ids.values())

    def set_scene_id(self, scene_id: str) -> None:
        """Set the resolved scene UUID at runtime (backward compat for single scene)."""
        if self._scene_configs:
            name = self._scene_configs[0].get("scene_name", "")
            self._resolved_scene_ids[name] = scene_id
        logger.info("Scene ID resolved", scene_id=scene_id)

    def set_scene_id_for_name(self, scene_name: str, scene_id: str) -> None:
        """Set the resolved scene UUID for a specific scene name."""
        self._resolved_scene_ids[scene_name] = scene_id
        logger.info("Scene ID resolved", scene_name=scene_name, scene_id=scene_id)

    def get_scene_id_reverse(self, scene_id: str) -> Optional[str]:
        """Return scene name for a given scene UUID."""
        for name, sid in self._resolved_scene_ids.items():
            if sid == scene_id:
                return name
        return None

    def get_scene_data_topic(self) -> str:
        return self.get_mqtt_config().get(
            "scene_data_topic_pattern", "scenescape/data/scene/+/+"
        )

    def get_region_event_topic(self) -> str:
        return self.get_mqtt_config().get(
            "region_event_topic_pattern", "scenescape/event/region/+/+/+"
        )

    def get_image_topic_pattern(self) -> str:
        return self.get_mqtt_config().get(
            "image_topic_pattern", "scenescape/image/camera/+"
        )

    def get_cmd_topic_pattern(self) -> str:
        return self.get_mqtt_config().get(
            "cmd_topic_pattern", "scenescape/cmd/camera/{camera_name}"
        )

    def get_alert_topic_prefix(self) -> str:
        return self.get_mqtt_config().get("alert_topic_prefix", "lp/alerts")

    def get_ba_request_topic(self) -> str:
        return os.environ.get(
            "BA_REQUEST_TOPIC",
            self.get_mqtt_config().get("ba_request_topic", "ba/requests"),
        )

    def get_ba_result_topic(self) -> str:
        return os.environ.get(
            "BA_RESULT_TOPIC",
            self.get_mqtt_config().get("ba_result_topic", "ba/results"),
        )

    # ---- seaweedfs ----
    def get_seaweedfs_config(self) -> dict:
        return self._app_cfg.get("seaweedfs", {})

    # ---- external services ----
    def get_behavioral_analysis_config(self) -> dict:
        return self._app_cfg.get("behavioral_analysis", {})

    def get_alert_service_config(self) -> dict:
        return self._app_cfg.get("alert_service", {})

    def get_rule_service_config(self) -> dict:
        return self._app_cfg.get("rule_service", {})

    # ---- rules ----
    def get_rules_config(self) -> dict:
        return self._rules_settings

    def get_rules_yaml_path(self) -> Path:
        return self._config_dir / "rules.yaml"

    def get_session_flag_defs(self) -> Dict[str, dict]:
        """Return {flag_name: {trigger, zone_type, ...}} from rules.yaml session_flags."""
        return dict(self._session_flag_defs)

    def get_service_defs(self) -> Dict[str, dict]:
        """Return {service_name: {handler, ...}} from rules.yaml services."""
        return dict(self._service_defs)

    # ---- zones (dynamic) ----
    def get_zones(self) -> Dict[str, dict]:
        """Return {region_uuid: {name, type}} — live, thread-safe."""
        with self._zone_lock:
            return dict(self._zones)

    def get_zone_type(self, region_id: str) -> Optional[str]:
        with self._zone_lock:
            zone = self._zones.get(region_id)
        if zone:
            return zone["type"]
        # Fallback: region_id may be a region name (e.g. from MQTT topic)
        return self._zone_name_map.get(region_id)

    def get_zone_name(self, region_id: str) -> Optional[str]:
        with self._zone_lock:
            zone = self._zones.get(region_id)
        if zone:
            return zone["name"]
        # Fallback: if region_id is already the name, return it if known
        if region_id in self._zone_name_map:
            return region_id
        return None

    def get_zone_scene_id(self, region_id: str) -> Optional[str]:
        """Return the scene_id that a zone belongs to."""
        with self._zone_lock:
            zone = self._zones.get(region_id)
        return zone.get("scene_id") if zone else None

    def set_zone(self, region_id: str, name: str, zone_type: str, **extra) -> None:
        """Add or update a single zone mapping at runtime."""
        with self._zone_lock:
            self._zones[region_id] = {"name": name, "type": zone_type, **extra}
        logger.info("Zone set", region_id=region_id, name=name, type=zone_type)

    def remove_zone(self, region_id: str) -> bool:
        """Remove a zone mapping. Returns True if it existed."""
        with self._zone_lock:
            removed = self._zones.pop(region_id, None)
        if removed:
            logger.info("Zone removed", region_id=region_id)
        return removed is not None

    def merge_zones(self, new_zones: Dict[str, dict]) -> int:
        """Merge discovered zones into the live map. Returns count added."""
        added = 0
        with self._zone_lock:
            for rid, zinfo in new_zones.items():
                if rid not in self._zones:
                    self._zones[rid] = zinfo
                    added += 1
        logger.info("Zones merged", added=added, total=len(self._zones))
        return added

    # ---- zone name map ----
    def get_zone_name_map(self) -> Dict[str, str]:
        """Return {region_name: zone_type} from all scenes (merged)."""
        return dict(self._zone_name_map)

    def get_zone_name_map_for_scene(self, scene_name: str) -> Dict[str, str]:
        """Return {region_name: zone_type} for a specific scene."""
        return dict(self._zone_name_map_per_scene.get(scene_name, {}))

    # ---- scenescape api ----
    def get_scenescape_api_config(self) -> dict:
        return self._zone_cfg.get("scenescape_api", {})
