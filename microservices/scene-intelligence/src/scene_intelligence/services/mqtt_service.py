"""MQTT service for receiving SceneScape region count data and camera images."""

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Optional
from queue import Queue
import threading

import paho.mqtt.client as mqtt
import structlog

from .config import ConfigService
from .directional_traffic_service import DirectionalTrafficService
from .image_service import ImageService


logger = structlog.get_logger(__name__)


class MQTTService:
    """Service for MQTT operations."""
    
    def __init__(self, config_service: ConfigService, directional_traffic_service: DirectionalTrafficService, image_service: ImageService, vlm_service=None):
        """Initialize MQTT service."""
        self.config = config_service
        self.directional_traffic = directional_traffic_service
        self.image_service = image_service
        self.vlm_service = vlm_service
        
        # MQTT connection settings
        self.host = "broker.scenescape.intel.com"
        self.port = 1883
        self.use_tls = True
        
        # MQTT client and connection state
        self.client = None
        self.connected = False
        self.loop = None
        
        # Message processing
        self.message_queue = Queue(maxsize=5000)
        self.processing_task = None
        self.shutdown_event = asyncio.Event()
        self.dropped_message_count = 0
        
        # Topic patterns
        # Pattern: scenescape/event/region/{scene_id}/{region_id}/count
        self.region_count_pattern = re.compile(r'scenescape/event/region/([^/]+)/([^/]+)/count')
        # Pattern: scenescape/image/camera/{camera_id}
        self.camera_image_pattern = re.compile(r'scenescape/image/camera/([^/]+)')
        
        logger.info("MQTT service initialized", host=self.host, port=self.port, use_tls=self.use_tls)
    
    async def initialize(self) -> None:
        """Initialize MQTT client."""
        try:
            self.client = mqtt.Client()
            
            # Configure TLS
            if self.use_tls:
                logger.info("Configuring MQTT TLS", ca_cert="/run/secrets/root-cert")
                self.client.tls_set(ca_certs="/run/secrets/root-cert", 
                                  certfile=None, 
                                  keyfile=None)
                logger.info("Using CA certificate for TLS verification")
            
            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            logger.info("MQTT client initialized")
            
        except Exception as e:
            logger.error("Failed to initialize MQTT client", error=str(e))
            raise
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback."""
        if rc == 0:
            self.connected = True
            logger.info("MQTT connected successfully")
            
            # Subscribe to region count events
            region_count_topic = "scenescape/event/region/+/+/count"
            client.subscribe(region_count_topic, qos=1)
            logger.info("Subscribed to MQTT topic", topic=region_count_topic)
            
            # Subscribe to camera image events
            camera_image_topic = "scenescape/image/camera/+"
            client.subscribe(camera_image_topic, qos=1)
            logger.info("Subscribed to MQTT topic", topic=camera_image_topic)
            
            # Subscribe to camera image events
            camera_image_topic = "scenescape/image/camera/+"
            client.subscribe(camera_image_topic, qos=1)
            logger.info("Subscribed to MQTT topic", topic=camera_image_topic)
        else:
            logger.error("MQTT connection failed", return_code=rc)
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback."""
        self.connected = False
        logger.warning("MQTT disconnected", return_code=rc)
    
    def _on_message(self, client, userdata, msg):
        """MQTT message callback - queue messages for async processing."""
        try:
            # Parse message payload first
            try:
                payload = json.loads(msg.payload.decode())
            except json.JSONDecodeError:
                logger.error("Failed to parse MQTT message payload", topic=msg.topic)
                return
            
            # Create message data structure
            message_data = {
                'topic': msg.topic,
                'payload': payload,
                'timestamp': datetime.now(timezone.utc)
            }
            
            # Queue the message for async processing (non-blocking)
            try:
                self.message_queue.put_nowait(message_data)
            except:
                # Queue is full, drop the message with reduced logging frequency
                self.dropped_message_count += 1
                if self.dropped_message_count % 100 == 1:  # Log every 100th dropped message
                    logger.warning("Message queue full, dropping message", 
                                 topic=msg.topic, 
                                 queue_size=self.message_queue.qsize())
        
        except Exception as e:
            logger.error("Error queuing MQTT message", error=str(e), topic=msg.topic)
    
    async def _process_region_count_message(self, 
                                          scene_id: str,
                                          region_id: str,
                                          payload: dict,
                                          timestamp: datetime) -> None:
        """Process region count MQTT message."""
        try:
            # Extract counts from payload
            counts = payload.get('counts', {})
            vehicle_count = counts.get('vehicle', 0)
            pedestrian_count = counts.get('pedestrian', 0)
            
            # Get region name for logging
            region_name = payload.get('region_name', region_id)
            
            logger.debug("Processing region count", 
                        scene_id=scene_id,
                        region_id=region_id,
                        region_name=region_name,
                        vehicle_count=vehicle_count,
                        pedestrian_count=pedestrian_count)
            
            # Update directional traffic service
            self.directional_traffic.update_region_count(
                scene_id=scene_id,
                region_uuid=region_id,
                counts={
                    "vehicle": vehicle_count,
                    "pedestrian": pedestrian_count
                }
            )
            
            # Trigger VLM analysis if high traffic density is detected
            if self.vlm_service:
                try:
                    # Get current directional densities for the scene
                    directional_data = self.directional_traffic.get_intersection_directional_data(scene_id)
                    if directional_data:
                        # Extract intersection ID from scene ID mapping
                        intersection_id = self._scene_to_intersection_id(scene_id)
                        if intersection_id:
                            # Convert DirectionalTrafficData to directional densities dict
                            directional_densities = {
                                "northbound": directional_data.northbound_density,
                                "southbound": directional_data.southbound_density,
                                "eastbound": directional_data.eastbound_density,
                                "westbound": directional_data.westbound_density
                            }
                            
                            # Trigger VLM analysis (async, non-blocking) 
                            # Use scene_id (UUID) instead of intersection_id (name) for consistent lookup
                            asyncio.create_task(
                                self.vlm_service.analyze_traffic_density(
                                    intersection_id=scene_id,  # Use original UUID, not mapped name
                                    directional_densities=directional_densities,
                                    image_service=self.image_service
                                )
                            )
                except Exception as e:
                    logger.error("Failed to trigger VLM analysis", 
                               error=str(e), scene_id=scene_id)
                    
        except Exception as e:
            logger.error("Failed to process region count message", 
                        error=str(e), 
                        scene_id=scene_id, 
                        region_id=region_id)
    
    async def _process_camera_image_message(self, 
                                          camera_id: str,
                                          payload: dict,
                                          topic: str,
                                          timestamp: datetime) -> None:
        """Process camera image MQTT message."""
        try:
            # Process camera image using image service
            self.image_service.process_image_message(topic, payload)
            
            logger.debug("Camera image processed successfully", 
                       camera_id=camera_id, 
                       payload_timestamp=payload.get('timestamp'))
                    
        except Exception as e:
            logger.error("Failed to process camera image message", 
                        error=str(e), 
                        camera_id=camera_id, 
                        topic=topic)
                    
        except Exception as e:
            logger.error("Failed to process camera image message", 
                        error=str(e), 
                        camera_id=camera_id, 
                        topic=topic)
    
    async def start(self) -> None:
        """Start MQTT service."""
        try:
            if not self.client:
                await self.initialize()
            
            logger.info("Starting MQTT connection", host=self.host, port=self.port)
            self.client.connect(self.host, self.port, 60)
            
            # Start the network loop in a separate thread
            self.client.loop_start()
            
            # Start the message processing task
            self.processing_task = asyncio.create_task(self._message_processor_task())
            
            # Keep the service running
            while True:
                await asyncio.sleep(1)
        
        except Exception as e:
            logger.error("Failed to start MQTT service", error=str(e))
            raise
    
    async def stop(self) -> None:
        """Stop MQTT service."""
        try:
            # Signal the shutdown event
            self.shutdown_event.set()
            
            if self.processing_task:
                await self.processing_task  # Wait for the processing task to finish
            
            if self.client:
                self.client.loop_stop()
                self.client.disconnect()
                logger.info("MQTT service stopped")
        
        except Exception as e:
            logger.error("Error stopping MQTT service", error=str(e))
    
    def is_connected(self) -> bool:
        """Check if MQTT client is connected."""
        return self.connected
    
    def set_event_loop(self, loop):
        """Set the event loop reference for async task scheduling."""
        self.loop = loop
        logger.info("Event loop reference set for MQTT service")
    
    async def _message_processor_task(self):
        """Background task to process queued MQTT messages."""
        logger.info("Starting MQTT message processor task")
        
        while not self.shutdown_event.is_set():
            try:
                # Process messages in larger batches to improve efficiency
                messages_to_process = []
                
                # Get up to 50 messages from queue (non-blocking)
                for _ in range(50):
                    try:
                        if not self.message_queue.empty():
                            message = self.message_queue.get_nowait()
                            messages_to_process.append(message)
                        else:
                            break
                    except:
                        break
                
                # Process all messages in the batch
                if messages_to_process:
                    await self._process_message_batch(messages_to_process)
                    # Log processing stats periodically
                    if len(messages_to_process) >= 25:
                        logger.info("Processed message batch", 
                                  batch_size=len(messages_to_process),
                                  queue_size=self.message_queue.qsize())
                else:
                    # No messages, sleep briefly to avoid busy waiting
                    await asyncio.sleep(0.05)  # Reduced sleep time for faster processing
                    
            except Exception as e:
                logger.error("Error in message processor task", error=str(e))
                await asyncio.sleep(1)  # Wait before retrying
        
        logger.info("MQTT message processor task stopped")
    
    async def _process_message_batch(self, messages: list):
        """Process a batch of MQTT messages."""
        try:
            # Separate messages by type
            region_count_messages = []
            camera_image_messages = []
            
            for message_data in messages:
                topic = message_data['topic']
                payload = message_data['payload']
                timestamp = message_data['timestamp']
                
                # Parse topic to extract message type
                region_match = self.region_count_pattern.match(topic)
                camera_match = self.camera_image_pattern.match(topic)
                
                if region_match:
                    scene_id, region_id = region_match.groups()
                    region_count_messages.append({
                        'scene_id': scene_id,
                        'region_id': region_id,
                        'payload': payload,
                        'timestamp': timestamp,
                        'topic': topic
                    })
                elif camera_match:
                    camera_id = camera_match.group(1)
                    camera_image_messages.append({
                        'camera_id': camera_id,
                        'payload': payload,
                        'timestamp': timestamp,
                        'topic': topic
                    })
                else:
                    # Log unexpected topic patterns for debugging
                    logger.debug("Ignoring unrecognized topic", topic=topic)
            
            # Process region count messages
            for msg in region_count_messages:
                try:
                    await self._process_region_count_message(
                        scene_id=msg['scene_id'],
                        region_id=msg['region_id'],
                        payload=msg['payload'],
                        timestamp=msg['timestamp']
                    )
                except Exception as e:
                    logger.error("Failed to process region count message", error=str(e), topic=msg['topic'])
            
            # Process camera image messages
            for msg in camera_image_messages:
                try:
                    await self._process_camera_image_message(
                        camera_id=msg['camera_id'],
                        payload=msg['payload'],
                        topic=msg['topic'],
                        timestamp=msg['timestamp']
                    )
                except Exception as e:
                    logger.error("Failed to process camera image message", error=str(e), topic=msg['topic'])
                    
        except Exception as e:
            logger.error("Error processing message batch", error=str(e))
    
    def _scene_to_intersection_id(self, scene_id: str) -> Optional[str]:
        """Map scene UUID to intersection ID using data.json."""
        try:
            import json
            import os
            
            # Get data.json path from config
            data_json_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "webserver", "data.json"
            )
            
            if not os.path.exists(data_json_path):
                logger.warning("data.json not found, falling back to hardcoded mapping", path=data_json_path)
                # Fallback to hardcoded mapping
                scene_mappings = {
                    "cb1cf1a0-b936-4d47-9221-3fd5cf24857d": "intersection-1",
                    "8f2a4c5e-d9b1-4e3f-a2c8-1b5d7e9f3a6c": "intersection-2",  
                    "3d7b9e1f-c4a6-4f8e-b2d5-6a8c0e2f4b7d": "intersection-3",
                    "9a4e6c2d-f1b8-4a3e-c7d9-5e8a1c4f6b9e": "intersection-4"
                }
                return scene_mappings.get(scene_id)
            
            # Load and parse data.json
            with open(data_json_path, 'r') as f:
                data = json.load(f)
            
            # Find scene with matching pk (scene_id) and return its name
            for item in data:
                if item.get("model") == "manager.scene" and item.get("pk") == scene_id:
                    scene_name = item.get("fields", {}).get("name", "")
                    # Convert scene name to intersection ID (e.g., "Intersection-1" -> "intersection-1")
                    if scene_name.startswith("Intersection-"):
                        return scene_name.lower()
                    return scene_name.lower()
            
            logger.warning("Scene not found in data.json", scene_id=scene_id)
            return None
            
        except Exception as e:
            logger.error("Failed to load scene mapping from data.json", error=str(e))
            # Fallback to hardcoded mapping
            scene_mappings = {
                "cb1cf1a0-b936-4d47-9221-3fd5cf24857d": "intersection-1",
                "8f2a4c5e-d9b1-4e3f-a2c8-1b5d7e9f3a6c": "intersection-2",  
                "3d7b9e1f-c4a6-4f8e-b2d5-6a8c0e2f4b7d": "intersection-3",
                "9a4e6c2d-f1b8-4a3e-c7d9-5e8a1c4f6b9e": "intersection-4"
            }
            return scene_mappings.get(scene_id)
