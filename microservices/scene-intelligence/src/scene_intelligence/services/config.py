"""Configuration service."""

import json
import os
from typing import Any, Dict

import structlog


logger = structlog.get_logger(__name__)


class ConfigService:
    """Service for managing configuration."""
    
    def __init__(self):
        """Initialize configuration service."""
        self.config_path = os.getenv(
            "SCENE_INTELLIGENCE_CONFIG", 
            "/app/config/scene_intelligence_config.json"
        )
        self.config = self._load_config()
        logger.info("Configuration loaded", config_path=self.config_path)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            logger.info("Configuration loaded successfully")
            return config
        except FileNotFoundError:
            logger.error("Configuration file not found", path=self.config_path)
            # Return default configuration
            return self._get_default_config()
        except json.JSONDecodeError as e:
            logger.error("Failed to parse configuration file", error=str(e))
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "service": {
                "name": "Scene Intelligence",
                "version": "1.0.0",
                "port": 8080
            },
            "intersections": {},
            "routes": {},
            "mqtt": {
                "qos": 1,
                "subscriptions": [
                    {
                        "topic_pattern": "scenescape/event/region/+/+/count",
                        "description": "Region count events for traffic density calculation"
                    }
                ]
            },
            "analysis": {
                "buffer_duration_seconds": 60,
                "aggregation_interval_seconds": 10
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_intersections(self) -> Dict[str, Any]:
        """Get intersections configuration."""
        intersections_data = self.config.get("intersections", {})
        
        # Handle both list and dict formats
        if isinstance(intersections_data, list):
            # Convert list format to dict format using id as key
            return {item.get("id"): item for item in intersections_data if item.get("id")}
        
        return intersections_data
    
    def get_routes(self) -> Dict[str, Any]:
        """Get routes configuration."""
        routes_data = self.config.get("routes", {})
        
        # Handle both list and dict formats
        if isinstance(routes_data, list):
            # Convert list format to dict format using id as key
            return {item.get("id"): item for item in routes_data if item.get("id")}
        
        return routes_data
    
    def get_mqtt_config(self) -> Dict[str, Any]:
        """Get MQTT configuration."""
        return self.config.get("mqtt", {})
    
    def get_analysis_config(self) -> Dict[str, Any]:
        """Get analysis configuration."""
        return self.config.get("analysis", {})
