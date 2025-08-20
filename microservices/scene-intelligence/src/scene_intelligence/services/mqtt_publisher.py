"""MQTT publisher service for sending commands to cameras."""

import asyncio
import os
from typing import List
import structlog
import paho.mqtt.client as mqtt

logger = structlog.get_logger(__name__)


class MQTTPublisher:
    """Service for publishing MQTT commands to cameras."""
    
    def __init__(self, config_service):
        """Initialize MQTT publisher."""
        self.config = config_service
        self.host = "broker.scenescape.intel.com"
        self.port = 1883
        self.use_tls = True
        self.client = None
        self.connected = False
        
        logger.info("MQTT Publisher initialized", host=self.host, port=self.port)
    
    async def initialize(self):
        """Initialize MQTT client for publishing."""
        try:
            self.client = mqtt.Client()
            
            # Configure TLS
            if self.use_tls:
                root_ca_path = "/run/secrets/root-cert"
                if os.path.exists(root_ca_path):
                    self.client.tls_set(ca_certs=root_ca_path)
                    logger.info("MQTT Publisher TLS configured", ca_cert=root_ca_path)
                else:
                    logger.warning("Root CA not found, connecting without TLS", path=root_ca_path)
            
            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_publish = self._on_publish
            
            # Connect to broker
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()
            
            # Wait for connection
            await asyncio.sleep(2)
            
            logger.info("MQTT Publisher initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize MQTT Publisher", error=str(e))
            raise
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback."""
        if rc == 0:
            self.connected = True
            logger.info("MQTT Publisher connected successfully")
        else:
            logger.error("MQTT Publisher connection failed", return_code=rc)
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnect callback."""
        self.connected = False
        logger.warning("MQTT Publisher disconnected", return_code=rc)
    
    def _on_publish(self, client, userdata, mid):
        """MQTT publish callback."""
        logger.debug("MQTT message published", message_id=mid)
    
    def get_all_camera_ids(self) -> List[str]:
        """Get all camera IDs from configuration."""
        camera_ids = []
        try:
            intersections = self.config.get_intersections()
            for intersection_id, intersection_data in intersections.items():
                cameras = intersection_data.get("cameras", [])
                for camera in cameras:
                    camera_id = camera.get("id")
                    if camera_id:
                        camera_ids.append(camera_id)
            
            logger.debug("Retrieved camera IDs", count=len(camera_ids), cameras=camera_ids)
            return camera_ids
            
        except Exception as e:
            logger.error("Failed to get camera IDs", error=str(e))
            return []
    
    async def send_getimage_commands(self) -> bool:
        """Send 'getimage' command to all cameras."""
        if not self.connected:
            logger.warning("MQTT Publisher not connected, cannot send commands")
            return False
        
        try:
            camera_ids = self.get_all_camera_ids()
            
            if not camera_ids:
                logger.warning("No camera IDs found")
                return False
            
            success_count = 0
            for camera_id in camera_ids:
                try:
                    topic = f"scenescape/cmd/camera/{camera_id}"
                    message = "getimage"
                    
                    result = self.client.publish(topic, message)
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        success_count += 1
                        logger.debug("Sent getimage command", camera_id=camera_id, topic=topic)
                    else:
                        logger.warning("Failed to send getimage command", 
                                     camera_id=camera_id, 
                                     result_code=result.rc)
                    
                    # Small delay between commands to avoid overwhelming the broker
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error("Error sending getimage command", 
                               camera_id=camera_id, 
                               error=str(e))
            
            logger.info("Sent getimage commands", 
                       total_cameras=len(camera_ids), 
                       successful=success_count)
            
            return success_count > 0
            
        except Exception as e:
            logger.error("Failed to send getimage commands", error=str(e))
            return False
    
    async def send_getimage_commands_for_intersections(self, intersection_ids: List[str]) -> bool:
        """Send 'getimage' command to cameras for specific intersections only."""
        if not self.connected:
            logger.warning("MQTT Publisher not connected, cannot send commands")
            return False
        
        try:
            # Get all camera metadata
            camera_metadata = self.config.get_intersections()
            
            # Map UUIDs to intersection names for camera lookup
            mapped_intersection_ids = [self._uuid_to_intersection_name(iid) for iid in intersection_ids]
            
            # Find cameras for the specified intersections
            target_camera_ids = []
            for intersection_id in mapped_intersection_ids:
                intersection_data = camera_metadata.get(intersection_id)
                if intersection_data:
                    cameras = intersection_data.get("cameras", [])
                    for camera in cameras:
                        camera_id = camera.get("id")
                        if camera_id:
                            target_camera_ids.append(camera_id)
            
            if not target_camera_ids:
                logger.warning("No camera IDs found for intersections", intersection_ids=intersection_ids)
                return False
            
            success_count = 0
            for camera_id in target_camera_ids:
                try:
                    topic = f"scenescape/cmd/camera/{camera_id}"
                    message = "getimage"
                    
                    result = self.client.publish(topic, message)
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        success_count += 1
                        logger.debug("Sent getimage command to high-density intersection camera", 
                                   camera_id=camera_id, topic=topic)
                    else:
                        logger.warning("Failed to send getimage command", 
                                     camera_id=camera_id, 
                                     result_code=result.rc)
                    
                    # Small delay between commands to avoid overwhelming the broker
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error("Error sending getimage command", 
                               camera_id=camera_id, 
                               error=str(e))
            
            logger.info("Sent getimage commands for high-density intersections", 
                       intersection_count=len(intersection_ids),
                       camera_count=len(target_camera_ids),
                       success_count=success_count)
            
            return success_count > 0
            
        except Exception as e:
            logger.error("Failed to send getimage commands for intersections", 
                       intersection_ids=intersection_ids, error=str(e))
            return False
    
    def _uuid_to_intersection_name(self, uuid: str) -> str:
        """Convert UUID to intersection name for camera lookup."""
        uuid_to_name = {
            "cb1cf1a0-b936-4d47-9221-3fd5cf24857d": "intersection-1",
            "8f2a4c5e-d9b1-4e3f-a2c8-1b5d7e9f3a6c": "intersection-2",
            "3d7b9e1f-c4a6-4f8e-b2d5-6a8c0e2f4b7d": "intersection-3",
            "9a4e6c2d-f1b8-4a3e-c7d9-5e8a1c4f6b9e": "intersection-4"
        }
        return uuid_to_name.get(uuid, uuid)  # Return original if not found (fallback)
    
    async def stop(self):
        """Stop MQTT publisher."""
        try:
            if self.client:
                self.client.loop_stop()
                self.client.disconnect()
                logger.info("MQTT Publisher stopped")
        except Exception as e:
            logger.error("Error stopping MQTT Publisher", error=str(e))
