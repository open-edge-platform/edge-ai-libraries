"""Image service for handling camera images from MQTT."""

import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CameraImage:
    """Camera image data."""
    camera_id: str
    intersection_id: str
    direction: str
    timestamp: datetime
    image_base64: str
    image_size_bytes: Optional[int] = None


@dataclass
class IntersectionImages:
    """Images for all cameras at an intersection."""
    intersection_id: str
    timestamp: datetime
    cameras: Dict[str, CameraImage]  # direction -> CameraImage


class ImageService:
    """Service for managing camera images from MQTT."""
    
    def __init__(self, config, max_images_per_camera: int = 10):
        """Initialize image service.
        
        Args:
            config: Service configuration object
        """
        self.config = config
        self.max_images_per_camera = max_images_per_camera
        
        # Store latest image per camera: camera_id -> CameraImage
        self.camera_images: Dict[str, CameraImage] = {}
        
        # Camera metadata: camera_id -> {intersection_id, direction}
        self.camera_metadata: Dict[str, Dict[str, str]] = {}
        
        # Mapping from scene UUID to intersection ID
        self.scene_uuid_to_intersection_id = {}
        
        # Statistics
        self.stats = {
            "total_images_processed": 0,
            "last_image_timestamp": None,
            "cameras_active": set(),
            "intersections_active": set()
        }
        
        # Initialize camera metadata from config
        self._initialize_camera_metadata()
        self._initialize_scene_mapping()
        
        logger.info("Image service initialized", 
                   total_cameras=len(self.camera_metadata))
    
    def _initialize_camera_metadata(self):
        """Initialize camera metadata from configuration."""
        try:
            intersections = self.config.get_intersections()
            
            logger.debug("Raw intersections config", 
                       intersections_keys=list(intersections.keys()) if intersections else [],
                       intersections_count=len(intersections) if intersections else 0)
            
            for intersection_id, intersection_data in intersections.items():
                cameras = intersection_data.get("cameras", [])
                
                logger.debug("Processing intersection cameras", 
                           intersection_id=intersection_id,
                           cameras_count=len(cameras))
                
                for camera in cameras:
                    camera_id = camera.get("id")
                    direction = camera.get("direction")
                    
                    if camera_id and direction:
                        self.camera_metadata[camera_id] = {
                            "intersection_id": intersection_id,
                            "direction": direction,
                            "name": camera.get("name", f"{intersection_id}-{direction}")
                        }
                        
                        logger.debug("Registered camera", 
                                   camera_id=camera_id,
                                   intersection_id=intersection_id,
                                   direction=direction)
            
            logger.info("Camera metadata initialized", 
                       total_cameras=len(self.camera_metadata),
                       intersections=list(intersections.keys()),
                       camera_metadata_sample=dict(list(self.camera_metadata.items())[:3]))
                       
        except Exception as e:
            logger.error("Failed to initialize camera metadata", error=str(e))
    
    def _initialize_scene_mapping(self):
        """Initialize mapping from scene UUID to intersection ID."""
        try:
            # Try to load scene mapping from data.json
            import os, json
            data_path = os.path.join(os.path.dirname(__file__), '../../webserver/data.json')
            if os.path.exists(data_path):
                with open(data_path, 'r') as f:
                    data = json.load(f)
                for item in data:
                    if item.get('model') == 'manager.scene':
                        pk = item.get('pk')
                        name = item.get('fields', {}).get('name')
                        if pk and name and 'Intersection' in name:
                            # Convert from "Intersection-3" to "intersection-3"
                            intersection_id = name.lower()
                            self.scene_uuid_to_intersection_id[pk] = intersection_id
                logger.info("Scene UUID to intersection mapping initialized", mapping=self.scene_uuid_to_intersection_id)
            else:
                logger.warning("data.json not found for scene mapping", path=data_path)
                
            # Add fallback hardcoded mapping if data.json failed or is incomplete
            fallback_mapping = {
                "cb1cf1a0-b936-4d47-9221-3fd5cf24857d": "intersection-1",
                "8f2a4c5e-d9b1-4e3f-a2c8-1b5d7e9f3a6c": "intersection-2",
                "3d7b9e1f-c4a6-4f8e-b2d5-6a8c0e2f4b7d": "intersection-3",
                "9a4e6c2d-f1b8-4a3e-c7d9-5e8a1c4f6b9e": "intersection-4"
            }
            
            # Add any missing mappings from fallback
            missing_mappings = []
            for uuid, intersection_name in fallback_mapping.items():
                if uuid not in self.scene_uuid_to_intersection_id:
                    self.scene_uuid_to_intersection_id[uuid] = intersection_name
                    missing_mappings.append(f"{uuid} -> {intersection_name}")
            
            if missing_mappings:
                logger.info("Added fallback scene mappings", 
                           added_mappings=missing_mappings)
            
            logger.info("Final scene UUID to intersection mapping", 
                       mapping=self.scene_uuid_to_intersection_id)
        except Exception as e:
            logger.error("Failed to initialize scene mapping", error=str(e))

    def process_image_message(self, topic: str, payload: Dict[str, Any]):
        """Process incoming image message from MQTT.
        
        Args:
            topic: MQTT topic (e.g., "scenescape/image/camera/intersection-1-cam2")
            payload: Message payload with timestamp, id, and base64 image
        """
        try:
            # Extract camera ID from topic
            topic_parts = topic.split("/")
            if len(topic_parts) >= 4:
                camera_id = topic_parts[-1]  # Last part should be camera ID
            else:
                camera_id = payload.get("id")
            
            if not camera_id:
                logger.warning("No camera ID found", topic=topic, payload_keys=list(payload.keys()))
                return
            
            # Validate payload
            required_fields = ["timestamp", "id", "image"]
            missing_fields = [field for field in required_fields if field not in payload]
            if missing_fields:
                logger.warning("Missing required fields in image message",
                             camera_id=camera_id,
                             missing_fields=missing_fields)
                return
            
            # Get camera metadata
            metadata = self.camera_metadata.get(camera_id)
            if not metadata:
                logger.warning("Unknown camera ID", camera_id=camera_id)
                return
            
            # Parse timestamp
            try:
                timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
            except Exception as e:
                logger.warning("Invalid timestamp format", 
                             camera_id=camera_id,
                             timestamp=payload["timestamp"],
                             error=str(e))
                timestamp = datetime.now(timezone.utc)
            
            # Calculate image size
            image_base64 = payload["image"]
            image_size_bytes = len(image_base64.encode('utf-8')) if image_base64 else 0
            
            # Create camera image object
            camera_image = CameraImage(
                camera_id=camera_id,
                intersection_id=metadata["intersection_id"],
                direction=metadata["direction"],
                timestamp=timestamp,
                image_base64=image_base64,
                image_size_bytes=image_size_bytes
            )
            
            # Store image (replace any existing image for this camera)
            self.camera_images[camera_id] = camera_image
            
            # Update statistics
            self.stats["total_images_processed"] += 1
            self.stats["last_image_timestamp"] = timestamp
            self.stats["cameras_active"].add(camera_id)
            self.stats["intersections_active"].add(metadata["intersection_id"])
            
            logger.info("Stored camera image",
                        camera_id=camera_id,
                        intersection_id=metadata["intersection_id"],
                        direction=metadata["direction"],
                        image_size_kb=round(image_size_bytes / 1024, 2),
                        total_cameras_active=len(self.stats["cameras_active"]),
                        total_intersections_active=len(self.stats["intersections_active"]),
                        timestamp=timestamp)
            
        except Exception as e:
            logger.error("Failed to process image message",
                        topic=topic,
                        error=str(e))
    
    def get_latest_camera_image(self, camera_id: str) -> Optional[CameraImage]:
        """Get the latest image for a specific camera.
        
        Args:
            camera_id: Camera identifier
            
        Returns:
            Latest CameraImage or None if not available
        """
        return self.camera_images.get(camera_id)
    
    def get_intersection_images(self, intersection_id: str, max_age_minutes: int = 5) -> Optional[IntersectionImages]:
        """Get latest images for all cameras at an intersection.
        
        Args:
            intersection_id: Intersection identifier
            max_age_minutes: Maximum age of images to include (in minutes)
            
        Returns:
            IntersectionImages with cameras by direction, or None if no recent images
        """
        logger.debug("Looking for intersection images", 
                   intersection_id=intersection_id,
                   total_camera_metadata=len(self.camera_metadata),
                   max_age_minutes=max_age_minutes)
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        cameras_data = {}
        latest_timestamp = None
        
        # Find cameras for this intersection
        matching_cameras = []
        for camera_id, metadata in self.camera_metadata.items():
            if metadata["intersection_id"] == intersection_id:
                matching_cameras.append((camera_id, metadata))
        
        logger.debug("Found matching cameras", 
                   intersection_id=intersection_id,
                   matching_cameras_count=len(matching_cameras),
                   matching_cameras=[(c_id, meta["direction"]) for c_id, meta in matching_cameras])
        
        for camera_id, metadata in matching_cameras:
            latest_image = self.get_latest_camera_image(camera_id)
            
            logger.debug("Checking camera image", 
                       intersection_id=intersection_id,
                       camera_id=camera_id,
                       direction=metadata["direction"],
                       has_image=bool(latest_image),
                       image_timestamp=latest_image.timestamp if latest_image else None,
                       cutoff_time=cutoff_time)
            
            if latest_image and latest_image.timestamp >= cutoff_time:
                direction = metadata["direction"]
                cameras_data[direction] = latest_image
                
                # Track latest timestamp
                if not latest_timestamp or latest_image.timestamp > latest_timestamp:
                    latest_timestamp = latest_image.timestamp
        
        logger.debug("Intersection images result", 
                   intersection_id=intersection_id,
                   cameras_data_count=len(cameras_data),
                   cameras_data_directions=list(cameras_data.keys()))
        
        if not cameras_data:
            return None
        
        return IntersectionImages(
            intersection_id=intersection_id,
            timestamp=latest_timestamp or datetime.now(timezone.utc),
            cameras=cameras_data
        )
    
    def get_all_intersections_images(self, max_age_minutes: int = 5) -> Dict[str, IntersectionImages]:
        """Get latest images for all intersections.
        
        Args:
            max_age_minutes: Maximum age of images to include (in minutes)
            
        Returns:
            Dictionary mapping intersection_id to IntersectionImages
        """
        all_images = {}
        
        # Get unique intersection IDs
        intersection_ids = set(
            metadata["intersection_id"] 
            for metadata in self.camera_metadata.values()
        )
        
        for intersection_id in intersection_ids:
            images = self.get_intersection_images(intersection_id, max_age_minutes)
            if images:
                all_images[intersection_id] = images
        
        return all_images
    
    def get_camera_stats(self) -> Dict[str, Any]:
        """Get camera and image statistics.
        
        Returns:
            Dictionary with various statistics
        """
        current_time = datetime.now(timezone.utc)
        
        # Count images per camera (now just 0 or 1)
        images_per_camera = {
            camera_id: 1 if camera_id in self.camera_images else 0
            for camera_id in self.camera_metadata.keys()
        }
        
        # Count recent images (last 5 minutes)
        recent_cutoff = current_time - timedelta(minutes=5)
        recent_images = 0
        
        for image in self.camera_images.values():
            if image.timestamp >= recent_cutoff:
                recent_images += 1
        
        return {
            "total_images_processed": self.stats["total_images_processed"],
            "last_image_timestamp": self.stats["last_image_timestamp"],
            "cameras_configured": len(self.camera_metadata),
            "cameras_active": len(self.stats["cameras_active"]),
            "intersections_active": len(self.stats["intersections_active"]),
            "images_per_camera": images_per_camera,
            "recent_images_count": recent_images,
            "current_images_stored": len(self.camera_images),
            "timestamp": current_time
        }
    
    def get_image_summary(self, intersection_id: str) -> Dict[str, dict]:
        """Get image summary for API response (backward compatibility).
        
        Args:
            intersection_id: ID of the intersection
            
        Returns:
            Dict with camera directions and their image metadata
        """
        intersection_images = self.get_intersection_images(intersection_id)
        summary = {}
        
        if intersection_images:
            for direction, image in intersection_images.cameras.items():
                summary[f"{direction}_camera"] = {
                    "camera_id": image.camera_id,
                    "direction": image.direction,
                    "timestamp": image.timestamp.isoformat(),
                    "image_base64": image.image_base64,
                    "image_size_bytes": image.image_size_bytes
                }
        
        return summary
    
    def get_all_images(self) -> Dict[str, Dict[str, CameraImage]]:
        """Get all camera images organized by intersection (backward compatibility).
        
        Returns:
            Dict mapping intersection_id to dict of direction->CameraImage
        """
        all_images = {}
        
        # Get all intersection IDs
        intersection_ids = set(
            metadata["intersection_id"] 
            for metadata in self.camera_metadata.values()
        )
        
        # Organize by intersection
        for intersection_id in intersection_ids:
            intersection_images = self.get_intersection_images(intersection_id)
            if intersection_images:
                all_images[intersection_id] = intersection_images.cameras
            else:
                all_images[intersection_id] = {}
                
        return all_images
    
    def get_intersection_images_by_scene_uuid(self, scene_uuid: str, max_age_minutes: int = 5):
        """Get images for intersection using scene UUID."""
        intersection_id = self.scene_uuid_to_intersection_id.get(scene_uuid)
        if not intersection_id:
            logger.debug("No intersection mapping for scene UUID", scene_uuid=scene_uuid)
            return {}
        images_obj = self.get_intersection_images(intersection_id, max_age_minutes)
        if not images_obj:
            return {}
        # Return dict of direction -> image metadata
        result = {}
        for direction, image in images_obj.cameras.items():
            result[f"{direction}_camera"] = {
                "camera_id": image.camera_id,
                "direction": image.direction,
                "timestamp": image.timestamp.isoformat(),
                "image_base64": image.image_base64,
                "image_size_bytes": image.image_size_bytes
            }
        return result
    
    def get_camera_status_debug(self) -> Dict[str, Any]:
        """Get current camera status for debugging."""
        now = datetime.now(timezone.utc)
        camera_status = {}
        
        for intersection_id in ["intersection-1", "intersection-2", "intersection-3", "intersection-4"]:
            intersection_cameras = {}
            for camera_id, metadata in self.camera_metadata.items():
                if metadata["intersection_id"] == intersection_id:
                    latest_image = self.get_latest_camera_image(camera_id)
                    age_minutes = None
                    if latest_image:
                        age_minutes = (now - latest_image.timestamp).total_seconds() / 60
                    
                    intersection_cameras[camera_id] = {
                        "direction": metadata["direction"],
                        "has_image": bool(latest_image),
                        "age_minutes": round(age_minutes, 1) if age_minutes else None,
                        "timestamp": latest_image.timestamp.isoformat() if latest_image else None
                    }
            camera_status[intersection_id] = intersection_cameras
        
        return {
            "total_cameras": len(self.camera_metadata),
            "total_images": len(self.camera_images),
            "cameras_active": list(self.stats["cameras_active"]),
            "intersections_active": list(self.stats["intersections_active"]),
            "camera_details": camera_status
        }
    
    def cleanup_stale_images(self, max_age_minutes: int = 10) -> int:
        """Clean up images older than specified age.
        
        Args:
            max_age_minutes: Maximum age for images in minutes
            
        Returns:
            Number of images removed
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        
        stale_cameras = []
        for camera_id, image in self.camera_images.items():
            if image.timestamp < cutoff_time:
                stale_cameras.append(camera_id)
        
        # Remove stale images
        for camera_id in stale_cameras:
            del self.camera_images[camera_id]
            
        if stale_cameras:
            logger.info("Cleaned up stale images", 
                       removed_count=len(stale_cameras),
                       max_age_minutes=max_age_minutes,
                       cameras_removed=stale_cameras)
        
        return len(stale_cameras)
    
    def get_fresh_images_only(self, intersection_id: str, max_age_minutes: int = 3) -> Optional[IntersectionImages]:
        """Get only fresh images for an intersection.
        
        This method is more strict about image freshness to prevent stale images
        from being included in responses when traffic density has changed.
        
        Args:
            intersection_id: ID of the intersection
            max_age_minutes: Maximum age for images (default 3 minutes)
            
        Returns:
            IntersectionImages object if fresh images available, None otherwise
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        
        cameras_with_fresh_images = {}
        latest_timestamp = None
        
        for camera_id, metadata in self.camera_metadata.items():
            if metadata["intersection_id"] == intersection_id:
                direction = metadata["direction"]
                
                if camera_id in self.camera_images:
                    image = self.camera_images[camera_id]
                    # Only include if image is fresh
                    if image.timestamp >= cutoff_time:
                        cameras_with_fresh_images[direction] = image
                        
                        if latest_timestamp is None or image.timestamp > latest_timestamp:
                            latest_timestamp = image.timestamp
        
        if not cameras_with_fresh_images:
            return None
        
        return IntersectionImages(
            intersection_id=intersection_id,
            timestamp=latest_timestamp,
            cameras=cameras_with_fresh_images
        )
