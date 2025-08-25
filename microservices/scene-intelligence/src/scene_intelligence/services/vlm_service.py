"""VLM service for traffic scene analysis."""

import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

import aiohttp
import structlog

from .image_service import CameraImage


logger = structlog.get_logger(__name__)


class TrafficState(Enum):
    """Traffic state enumeration."""
    NORMAL = "normal"
    HIGH = "high"


@dataclass
class TrafficAnalysisRequest:
    """Request for VLM traffic analysis."""
    intersection_id: str
    high_density_directions: List[str]
    camera_images: List[CameraImage]  # 4 images (one per direction)
    timestamp: datetime
    density_values: Dict[str, float]


@dataclass
class VLMAnalysisResult:
    """VLM analysis result with traffic context."""
    intersection_id: str
    analysis: str
    timestamp: datetime
    high_density_directions: List[str]
    confidence: Optional[float] = None
    # Traffic context from the analysis window
    analysis_period_start: Optional[datetime] = None
    analysis_period_end: Optional[datetime] = None
    avg_densities: Optional[Dict[str, float]] = None
    peak_densities: Optional[Dict[str, float]] = None
    # Camera images used for analysis (stored for same retention as analysis)
    camera_images: Optional[Dict[str, Any]] = None


@dataclass
class TrafficWindow:
    """Traffic data window for analysis."""
    timestamp: datetime
    directional_densities: Dict[str, float]
    high_density_directions: List[str]


@dataclass
class IntersectionTrafficState:
    """Track traffic state for an intersection."""
    intersection_id: str
    current_state: TrafficState = TrafficState.NORMAL
    state_change_time: Optional[datetime] = None
    last_vlm_analysis: Optional[datetime] = None
    last_high_density_directions: List[str] = None
    pending_analysis: bool = False
    last_image_request: Optional[datetime] = None  # Track when images were last requested
    # Sliding window for sustained traffic analysis
    traffic_window: List[TrafficWindow] = None
    
    def __post_init__(self):
        if self.traffic_window is None:
            self.traffic_window = []


class VLMService:
    """
    Service for VLM-based traffic scene analysis.

    VLM Analysis Triggers:
    - Threshold Exceeded: Any direction > configurable threshold (default: 5)
    - State Change: Only when transitioning from normal→high traffic
    - Persistence: High traffic must persist for configurable duration (default: 30s)
    - Cooldown: Configurable gap between VLM calls per intersection (default: 1 minute)
    - Multi-Frame: Sends up to 4 recent images (one per camera direction)
    
    Concurrent Processing:
    - VLM microservice supports multiple workers for concurrent API calls
    - Each intersection can trigger VLM analysis independently
    - Per-intersection pending_analysis flags prevent duplicate requests
    - Multiple intersections can be analyzed simultaneously by VLM service
    """
    
    def __init__(self, config):
        """Initialize VLM service."""
        self.config = config
        
        # Load VLM configuration
        self.vlm_config = self._load_vlm_config()
        
        # VLM service configuration
        self.vlm_base_url = os.getenv("VLM_BASE_URL", self.vlm_config.get("vlm_service", {}).get("base_url"))
        self.vlm_model = os.getenv("VLM_MODEL", self.vlm_config.get("vlm_service", {}).get("model"))
        
        # VLM concurrency configuration
        self.VLM_WORKERS = int(os.getenv("VLM_WORKERS", 
                                           self.vlm_config.get("vlm_service", {}).get("vlm_workers", 3)))
        
        # Create semaphore to limit concurrent VLM API calls
        self.vlm_semaphore = asyncio.Semaphore(self.VLM_WORKERS)
        
        # Traffic analysis configuration - use environment variables first, then config file
        traffic_config = self.vlm_config.get("traffic_analysis", {})
        self.high_density_threshold = float(os.getenv("HIGH_DENSITY_THRESHOLD", traffic_config.get("high_density_threshold", 5.0)))
        
        # Windowed analysis configuration (your requirements)
        self.traffic_window_duration_seconds = 15  # 15-second sliding window
        self.sustained_threshold_seconds = 5     # 12.5 seconds sustained high traffic
        self.analysis_display_duration_minutes = 20  # Show analysis for 20 minutes
        
        # Legacy config for backward compatibility
        self.minimum_duration_for_consistently_high_traffic_seconds = int(
            os.getenv("MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS", 
                     traffic_config.get("minimum_duration_for_consistently_high_traffic_seconds", 30))
        )
        self.vlm_cooldown_minutes = int(
            os.getenv("VLM_COOLDOWN_MINUTES", 
                     traffic_config.get("vlm_cooldown_minutes", 1))
        )
        self.vlm_timeout_seconds = int(
            os.getenv("VLM_TIMEOUT_SECONDS", 
                     self.vlm_config.get("vlm_service", {}).get("timeout_seconds", 10))
        )
        
        # VLM model parameters - from config file with env variable override
        model_params = self.vlm_config.get("vlm_model_parameters", {})
        self.max_completion_tokens = int(os.getenv("VLM_MAX_COMPLETION_TOKENS", model_params.get("max_completion_tokens", 500)))
        self.temperature = float(os.getenv("VLM_TEMPERATURE", model_params.get("temperature", 0.3)))
        self.top_p = float(os.getenv("VLM_TOP_P", model_params.get("top_p", 0.9)))
        
        # Prompts from config file with env variable override
        prompts = self.vlm_config.get("prompts", {})
        self.traffic_analysis_prompt = os.getenv("VLM_TRAFFIC_ANALYSIS_PROMPT", prompts.get("traffic_analysis_prompt", 
            "Analyze the provided intersection images and explain the high traffic density."))
        self.system_prompt = os.getenv("VLM_SYSTEM_PROMPT", prompts.get("system_prompt", 
            "You are an AI traffic analyst."))
        
        # Debug logging for prompt configuration
        logger.debug("VLM prompt configuration", 
                   system_prompt_length=len(self.system_prompt),
                   traffic_prompt_length=len(self.traffic_analysis_prompt),
                   system_prompt_preview=self.system_prompt[:100] + "..." if len(self.system_prompt) > 100 else self.system_prompt,
                   traffic_prompt_preview=self.traffic_analysis_prompt[:100] + "..." if len(self.traffic_analysis_prompt) > 100 else self.traffic_analysis_prompt)
        
        # Track traffic states per intersection
        self.intersection_states: Dict[str, IntersectionTrafficState] = {}
        
        # Store latest VLM results
        self.vlm_results: Dict[str, VLMAnalysisResult] = {}
        
        # Track recent image requests to coordinate with API
        self.recent_image_requests: Dict[str, datetime] = {}
        self.image_request_cooldown_seconds = 30  # Don't request images again within 30 seconds
        
        # MQTT publisher for coordinated image requests
        self.mqtt_publisher = None
        
        logger.info("VLM Service initialized", 
                   vlm_base_url=self.vlm_base_url,
                   VLM_WORKERS=self.VLM_WORKERS,
                   high_density_threshold=self.high_density_threshold,
                   cooldown_minutes=self.vlm_cooldown_minutes,
                   max_completion_tokens=self.max_completion_tokens)
    
    def _load_vlm_config(self) -> dict:
        """Load VLM configuration from file."""
        try:
            config_path = os.getenv("VLM_CONFIG_FILE", "config/vlm_config.json")
            
            # If path is relative, make it relative to the project root
            if not os.path.isabs(config_path):
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                config_path = os.path.join(project_root, config_path)
            
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config_content = f.read()
                    # Replace environment variables in config
                    import re
                    config_content = re.sub(r'\${(\w+)}', lambda m: os.getenv(m.group(1), m.group(0)), config_content)
                    return json.loads(config_content)
            else:
                logger.warning("VLM config file not found, using defaults", path=config_path)
                return {}
        except Exception as e:
            logger.error("Failed to load VLM config, using defaults", error=str(e))
            return {}
    
    def update_high_density_threshold(self, threshold: float) -> None:
        """Update the high density threshold."""
        self.high_density_threshold = threshold
        logger.info("High density threshold updated", threshold=threshold)
    
    def analyze_high_density_directions(self, directional_densities: Dict[str, float]) -> List[str]:
        """
        Analyze directional densities and return directions that exceed threshold.
        
        Args:
            directional_densities: Density values per direction
            
        Returns:
            List of directions with high density
        """
        high_directions = []
        for direction, density in directional_densities.items():
            if density >= self.high_density_threshold:
                high_directions.append(direction)
        return high_directions
    
    def get_high_traffic_threshold(self) -> float:
        """Get current high density threshold - alias for compatibility."""
        return self.high_density_threshold
    
    def set_mqtt_publisher(self, mqtt_publisher) -> None:
        """Set MQTT publisher for coordinated image requests."""
        self.mqtt_publisher = mqtt_publisher
        logger.info("MQTT publisher set in VLM service for image coordination")
    
    def mark_image_request(self, intersection_id: str) -> None:
        """Mark that images were recently requested for an intersection."""
        self.recent_image_requests[intersection_id] = datetime.utcnow()
        logger.debug("Marked image request for intersection", intersection_id=intersection_id)
    
    def should_request_images(self, intersection_id: str) -> bool:
        """Check if we should request images for an intersection (coordination with API)."""
        now = datetime.utcnow()
        
        # Check if images were recently requested
        if intersection_id in self.recent_image_requests:
            time_since_request = (now - self.recent_image_requests[intersection_id]).total_seconds()
            if time_since_request < self.image_request_cooldown_seconds:
                logger.debug("Images recently requested, skipping", 
                           intersection_id=intersection_id,
                           seconds_ago=round(time_since_request, 1))
                return False
        
        return True
    
    async def analyze_traffic_density(self, intersection_id: str, 
                                    directional_densities: Dict[str, float],
                                    image_service) -> Optional[str]:
        """
        Analyze traffic density and trigger VLM if needed.
        
        Args:
            intersection_id: ID of the intersection
            directional_densities: Density values per direction
            image_service: Image service instance
            
        Returns:
            VLM analysis text if available, None otherwise
        """
        now = datetime.utcnow()
        
        # Initialize intersection state if not exists
        if intersection_id not in self.intersection_states:
            self.intersection_states[intersection_id] = IntersectionTrafficState(
                intersection_id=intersection_id
            )
        
        state = self.intersection_states[intersection_id]
        
        # Update sliding window with current traffic data
        self._update_traffic_window(state, directional_densities, now)
        
        # Check for sustained high traffic in the window
        sustained_traffic = self._check_sustained_high_traffic(state, now)
        
        if sustained_traffic and not state.pending_analysis:
            # We have sustained high traffic and no analysis is pending
            logger.info("Sustained high traffic detected, triggering VLM analysis", 
                       intersection_id=intersection_id,
                       duration_seconds=sustained_traffic['duration_seconds'],
                       high_directions=sustained_traffic['high_directions'],
                       avg_densities=sustained_traffic['avg_densities'])
            
            # Check if we need to request images first (coordinate with API)
            need_fresh_images = self.should_request_images(intersection_id)
            
            if need_fresh_images:
                # Request images for this intersection only (not all cameras)
                try:
                    if self.mqtt_publisher and hasattr(self.mqtt_publisher, 'send_getimage_commands_for_intersections'):
                        logger.info("Requesting fresh images for VLM analysis", 
                                   intersection_id=intersection_id)
                        
                        # Mark that we're requesting images
                        self.mark_image_request(intersection_id)
                        
                        # Request images for this specific intersection
                        await self.mqtt_publisher.send_getimage_commands_for_intersections([intersection_id])
                        
                        # Wait briefly for images to arrive
                        await asyncio.sleep(2)
                        logger.debug("Waited for fresh images", intersection_id=intersection_id)
                    else:
                        logger.warning("MQTT publisher not available for image requests", 
                                     intersection_id=intersection_id)
                except Exception as e:
                    logger.warning("Failed to request fresh images", 
                                 intersection_id=intersection_id, error=str(e))
            
            # Get images for analysis
            camera_images = self._get_intersection_images(intersection_id, image_service)
            
            if camera_images and len(camera_images) >= 2:  # Need at least 2 cameras
                # Set pending analysis flag
                state.pending_analysis = True
                state.last_vlm_analysis = now
                
                # Trigger VLM analysis asynchronously with traffic context
                asyncio.create_task(self._perform_vlm_analysis_with_context(
                    intersection_id, sustained_traffic, camera_images, now
                ))
                
                logger.info("VLM analysis started for intersection", 
                           intersection_id=intersection_id,
                           camera_count=len(camera_images))
            else:
                logger.warning("Insufficient camera images for VLM analysis", 
                             intersection_id=intersection_id,
                             image_count=len(camera_images) if camera_images else 0)
        
        # Return existing VLM result if available and not expired (20 minutes)
        if intersection_id in self.vlm_results:
            result = self.vlm_results[intersection_id]
            age_minutes = (now - result.timestamp).total_seconds() / 60
            if age_minutes < self.analysis_display_duration_minutes:
                return result.analysis
            else:
                # Analysis has expired, remove it
                del self.vlm_results[intersection_id]
                logger.debug("Removed expired VLM analysis", 
                           intersection_id=intersection_id, 
                           age_minutes=round(age_minutes, 1))
        
        return None
    
    def _should_trigger_vlm_analysis(self, state: IntersectionTrafficState, now: datetime) -> bool:
        """Determine if VLM analysis should be triggered."""
        # Must be in high traffic state
        if state.current_state != TrafficState.HIGH:
            return False
        
        # Must have been in high state for minimum duration
        if not state.state_change_time:
            return False
        
        time_in_high_state = (now - state.state_change_time).total_seconds()
        if time_in_high_state < self.minimum_duration_for_consistently_high_traffic_seconds:
            return False
        
        # Check cooldown period
        if state.last_vlm_analysis:
            time_since_last_analysis = (now - state.last_vlm_analysis).total_seconds()
            if time_since_last_analysis < (self.vlm_cooldown_minutes * 60):
                return False
        
        # Don't trigger if analysis is already pending
        if state.pending_analysis:
            return False
        
        return True
    
    def _get_intersection_images(self, intersection_id: str, image_service) -> List[CameraImage]:
        """Get recent images for all cameras at an intersection."""
        try:
            logger.debug("Attempting to get intersection images", 
                       intersection_id=intersection_id,
                       image_service_type=type(image_service).__name__)
            
            # Debug: Show what camera images are currently available
            logger.debug("Current camera images available", 
                       intersection_id=intersection_id,
                       total_camera_images=len(image_service.camera_images),
                       camera_ids=list(image_service.camera_images.keys())[:10]  # First 10 for brevity
                       )
            
            # Debug: Show detailed camera status
            if hasattr(image_service, 'get_camera_status_debug'):
                camera_status = image_service.get_camera_status_debug()
                logger.debug("Detailed camera status", 
                           intersection_id=intersection_id,
                           camera_status=camera_status)
            
            # Debug: Show camera metadata for this intersection
            matching_metadata = {k: v for k, v in image_service.camera_metadata.items() 
                               if v.get("intersection_id") == intersection_id}
            logger.debug("Camera metadata for intersection", 
                       intersection_id=intersection_id,
                       matching_metadata_count=len(matching_metadata),
                       matching_metadata=matching_metadata)
            
            # Get images using scene UUID (since intersection_id is now a UUID)
            intersection_images = image_service.get_intersection_images_by_scene_uuid(intersection_id)
            
            logger.debug("Image service result", 
                       intersection_id=intersection_id,
                       intersection_images_type=type(intersection_images).__name__ if intersection_images else None,
                       intersection_images_bool=bool(intersection_images))
            
            if not intersection_images:
                logger.warning("No images found for intersection", 
                             intersection_id=intersection_id)
                return []
            
            logger.debug("Processing intersection images", 
                       intersection_id=intersection_id,
                       images_type=type(intersection_images).__name__,
                       images_count=len(intersection_images) if isinstance(intersection_images, dict) else "unknown")
            
            # Extract camera images - handle both dict format (from scene UUID lookup) and object format
            camera_images = []
            if isinstance(intersection_images, dict):
                # Handle dict format from get_intersection_images_by_scene_uuid
                for direction_key, camera_image in intersection_images.items():
                    logger.debug("Processing camera from dict", 
                               intersection_id=intersection_id,
                               direction_key=direction_key,
                               camera_image_type=type(camera_image).__name__)
                    
                    if isinstance(camera_image, dict) and 'image_base64' in camera_image:
                        # Convert dict to CameraImage object
                        camera_image_obj = CameraImage(
                            camera_id=camera_image.get('camera_id', f"{intersection_id}-unknown"),
                            intersection_id=intersection_id,
                            direction=camera_image.get('direction', direction_key.replace('_camera', '')),
                            timestamp=datetime.fromisoformat(camera_image.get('timestamp', datetime.utcnow().isoformat())),
                            image_base64=camera_image['image_base64']
                        )
                        camera_images.append(camera_image_obj)
            elif hasattr(intersection_images, 'cameras'):
                # Handle object format from get_intersection_images
                for direction_key, camera_image in intersection_images.cameras.items():
                    logger.debug("Processing camera from object", 
                               intersection_id=intersection_id,
                               direction_key=direction_key,
                               camera_image_type=type(camera_image).__name__)
                    
                    if isinstance(camera_image, CameraImage):
                        # Already a CameraImage object
                        camera_images.append(camera_image)
                    elif isinstance(camera_image, dict) and 'image_base64' in camera_image:
                        # Convert dict to CameraImage object (legacy format)
                        camera_image_obj = CameraImage(
                            camera_id=camera_image.get('camera_id', f"{intersection_id}-unknown"),
                            intersection_id=intersection_id,
                            direction=camera_image.get('direction', direction_key.replace('_camera', '')),
                            timestamp=datetime.fromisoformat(camera_image.get('timestamp', datetime.utcnow().isoformat())),
                            image_base64=camera_image['image_base64']
                        )
                        camera_images.append(camera_image_obj)
            
            logger.debug("Camera images extracted", 
                       intersection_id=intersection_id,
                       camera_images_count=len(camera_images))
            
            return camera_images
            
        except Exception as e:
            logger.error("Failed to get intersection images", 
                        intersection_id=intersection_id, error=str(e))
            return []
    
    async def _perform_vlm_analysis(self, intersection_id: str, 
                                  high_density_directions: List[str],
                                  camera_images: List[CameraImage],
                                  density_values: Dict[str, float],
                                  timestamp: datetime) -> None:
        """
        Perform VLM analysis asynchronously with semaphore-based concurrency control.
        
        This method uses a semaphore to limit concurrent VLM API calls to the number
        of available VLM workers, preventing overload while allowing multiple
        intersections to be analyzed concurrently.
        """
        try:
            logger.info("Requesting VLM analysis slot", 
                       intersection_id=intersection_id,
                       high_directions=high_density_directions,
                       image_count=len(camera_images))
            
            # Acquire semaphore to limit concurrent VLM calls
            async with self.vlm_semaphore:
                logger.info("Starting VLM analysis (semaphore acquired)", 
                           intersection_id=intersection_id,
                           high_directions=high_density_directions,
                           available_slots=self.vlm_semaphore._value)
                
                # Create prompt
                prompt = self._create_traffic_analysis_prompt(
                    intersection_id, high_density_directions, density_values
                )
                
                # Prepare VLM request
                vlm_request = self._build_vlm_request(prompt, camera_images)
                
                # Call VLM service - protected by semaphore
                analysis_result = await self._call_vlm_service(vlm_request)
                
                if analysis_result:
                    # Convert camera images to serializable format for storage
                    camera_images_dict = {}
                    for camera_image in camera_images:
                        if hasattr(camera_image, 'direction') and hasattr(camera_image, 'image_base64'):
                            camera_images_dict[f"{camera_image.direction}_camera"] = {
                                'camera_id': getattr(camera_image, 'camera_id', f"{intersection_id}_{camera_image.direction}"),
                                'direction': camera_image.direction,
                                'timestamp': camera_image.timestamp.isoformat() if hasattr(camera_image, 'timestamp') and camera_image.timestamp else timestamp.isoformat(),
                                'image_base64': camera_image.image_base64,
                                'image_size_bytes': getattr(camera_image, 'image_size_bytes', None)
                            }
                    
                    # Store result with camera images
                    self.vlm_results[intersection_id] = VLMAnalysisResult(
                        intersection_id=intersection_id,
                        analysis=analysis_result,
                        timestamp=timestamp,
                        high_density_directions=high_density_directions,
                        camera_images=camera_images_dict
                    )
                    
                    logger.info("VLM analysis completed successfully", 
                               intersection_id=intersection_id,
                               analysis_length=len(analysis_result))
                else:
                    logger.warning("VLM analysis returned no result", 
                                 intersection_id=intersection_id)
            
        except Exception as e:
            logger.error("VLM analysis failed", 
                        intersection_id=intersection_id, error=str(e))
        finally:
            # Clear pending flag for this specific intersection
            if intersection_id in self.intersection_states:
                self.intersection_states[intersection_id].pending_analysis = False
                logger.debug("Cleared pending analysis flag", 
                           intersection_id=intersection_id)
    
    async def _perform_vlm_analysis_with_context(self, intersection_id: str, 
                                               sustained_traffic: Dict[str, Any],
                                               camera_images: List[CameraImage],
                                               timestamp: datetime) -> None:
        """
        Perform VLM analysis with traffic context from sustained period.
        """
        try:
            logger.info("Requesting VLM analysis slot with context", 
                       intersection_id=intersection_id,
                       sustained_duration=sustained_traffic['duration_seconds'],
                       high_directions=sustained_traffic['high_directions'],
                       image_count=len(camera_images))
            
            # Acquire semaphore to limit concurrent VLM calls
            async with self.vlm_semaphore:
                logger.info("Starting VLM analysis with traffic context (semaphore acquired)", 
                           intersection_id=intersection_id,
                           available_slots=self.vlm_semaphore._value)
                
                # Create prompt with sustained traffic context
                prompt = self._create_windowed_traffic_analysis_prompt(
                    intersection_id, sustained_traffic
                )
                
                # Prepare VLM request
                vlm_request = self._build_vlm_request(prompt, camera_images)
                
                # Call VLM service
                analysis_result = await self._call_vlm_service(vlm_request)
                
                if analysis_result:
                    # Convert camera images to serializable format for storage
                    camera_images_dict = {}
                    for camera_image in camera_images:
                        if hasattr(camera_image, 'direction') and hasattr(camera_image, 'image_base64'):
                            camera_images_dict[f"{camera_image.direction}_camera"] = {
                                'camera_id': getattr(camera_image, 'camera_id', f"{intersection_id}_{camera_image.direction}"),
                                'direction': camera_image.direction,
                                'timestamp': camera_image.timestamp.isoformat() if hasattr(camera_image, 'timestamp') and camera_image.timestamp else timestamp.isoformat(),
                                'image_base64': camera_image.image_base64,
                                'image_size_bytes': getattr(camera_image, 'image_size_bytes', None)
                            }
                    
                    # Store result with enhanced context and camera images
                    self.vlm_results[intersection_id] = VLMAnalysisResult(
                        intersection_id=intersection_id,
                        analysis=analysis_result,
                        timestamp=timestamp,
                        high_density_directions=sustained_traffic['high_directions'],
                        analysis_period_start=sustained_traffic['period_start'],
                        analysis_period_end=sustained_traffic['period_end'],
                        avg_densities=sustained_traffic['avg_densities'],
                        peak_densities=sustained_traffic['peak_densities'],
                        camera_images=camera_images_dict
                    )
                    
                    logger.info("VLM analysis with context completed successfully", 
                               intersection_id=intersection_id,
                               analysis_length=len(analysis_result),
                               period_duration=sustained_traffic['duration_seconds'])
                else:
                    logger.warning("VLM analysis returned no result", 
                                 intersection_id=intersection_id)
            
        except Exception as e:
            logger.error("VLM analysis with context failed", 
                        intersection_id=intersection_id, error=str(e))
        finally:
            # Clear pending flag
            if intersection_id in self.intersection_states:
                self.intersection_states[intersection_id].pending_analysis = False
                logger.debug("Cleared pending analysis flag", 
                           intersection_id=intersection_id)
    
    def _create_traffic_analysis_prompt(self, intersection_id: str, 
                                      high_density_directions: List[str],
                                      density_values: Dict[str, float]) -> str:
        """Create structured prompt for VLM traffic analysis using configurable template."""
        
        # Convert UUID to readable intersection name for prompt
        intersection_name = self._uuid_to_intersection_name(intersection_id)
        
        directions_text = ", ".join(high_density_directions) if high_density_directions else "multiple directions"
        density_info = "; ".join([f"{direction}: {density:.1f}" for direction, density in density_values.items()])
        
        logger.debug("Creating VLM prompt", 
                   intersection_id=intersection_id,
                   intersection_name=intersection_name,
                   directions_text=directions_text,
                   density_info=density_info,
                   template_preview=self.traffic_analysis_prompt[:100] + "..." if len(self.traffic_analysis_prompt) > 100 else self.traffic_analysis_prompt)
        
        # Use the configurable prompt template from config file with readable intersection name
        prompt = self.traffic_analysis_prompt.format(
            intersection_id=intersection_name,  # Use readable name in prompt
            directions_text=directions_text,
            density_info=density_info,
            high_density_threshold=self.high_density_threshold
        )
        
        logger.debug("Generated VLM prompt", 
                   intersection_id=intersection_id,
                   prompt_length=len(prompt),
                   prompt_preview=prompt[:200] + "..." if len(prompt) > 200 else prompt)
        
        return prompt
    
    def _create_windowed_traffic_analysis_prompt(self, intersection_id: str, 
                                               sustained_traffic: Dict[str, Any]) -> str:
        """Create prompt with sustained traffic context."""
        # Convert UUID to readable intersection name for prompt
        intersection_name = self._uuid_to_intersection_name(intersection_id)
        
        period_start = sustained_traffic['period_start'].strftime('%H:%M:%S')
        period_end = sustained_traffic['period_end'].strftime('%H:%M:%S')
        duration = sustained_traffic['duration_seconds']
        high_directions = ", ".join(sustained_traffic['high_directions'])
        
        # Format average densities
        avg_densities_text = "; ".join([
            f"{direction}: {density:.1f}" 
            for direction, density in sustained_traffic['avg_densities'].items()
            if density > 0
        ])
        
        # Format peak densities  
        peak_densities_text = "; ".join([
            f"{direction}: {density:.1f}" 
            for direction, density in sustained_traffic['peak_densities'].items()
            if density > 0
        ])
        
        prompt = f"""Analyze the traffic situation at {intersection_name}.
        
Traffic Context:
- Analysis Period: {period_start} to {period_end} ({duration:.1f} seconds)
- High Density Directions: {high_directions}
- Average Densities: {avg_densities_text}
- Peak Densities: {peak_densities_text}
- Threshold: {self.high_density_threshold}

Please analyze the provided intersection images and explain:
1. The sustained high traffic density observed in {high_directions} direction(s)
2. Visible congestion patterns and vehicle behavior
3. Any contributing factors to the traffic buildup
4. Recommendations for traffic management

Focus on the {high_directions} direction(s) where sustained high density was detected."""
        
        logger.debug("Generated windowed VLM prompt", 
                   intersection_id=intersection_id,
                   prompt_length=len(prompt))
        
        return prompt
    
    def _build_vlm_request(self, prompt: str, camera_images: List[CameraImage]) -> Dict[str, Any]:
        """Build VLM API request with multiple images."""
        
        logger.debug("Building VLM request", 
                   prompt_length=len(prompt),
                   camera_images_count=len(camera_images),
                   system_prompt_length=len(self.system_prompt))
        
        # Prepare content with text prompt and images
        content = [
            {
                "type": "text",
                "text": prompt
            }
        ]
        
        # Add up to 4 camera images (one per direction)
        for i, camera_image in enumerate(camera_images[:4]):
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{camera_image.image_base64[:50]}..." # Just first 50 chars for logging
                }
            })
        
        # Use configurable parameters
        request = {
            "model": self.vlm_model,
            "messages": [
                {
                    "role": "system",
                    "content": self.system_prompt
                },
                {
                    "role": "user",
                    "content": content
                }
            ],
            "max_completion_tokens": self.max_completion_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p
        }
        
        logger.debug("VLM request built", 
                   model=self.vlm_model,
                   messages_count=len(request["messages"]),
                   user_content_count=len(content),
                   max_tokens=self.max_completion_tokens)
        
        # Fix the content for actual request (restore full base64)
        for i, camera_image in enumerate(camera_images[:4]):
            content[i+1]["image_url"]["url"] = f"data:image/jpeg;base64,{camera_image.image_base64}"
        
        return request
    
    async def _call_vlm_service(self, request_data: Dict[str, Any]) -> Optional[str]:
        """Call VLM service API."""
        try:
            url = f"{self.vlm_base_url}/v1/chat/completions"
            
            timeout = aiohttp.ClientTimeout(total=self.vlm_timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=request_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        if 'choices' in result and len(result['choices']) > 0:
                            content = result['choices'][0].get('message', {}).get('content', '')
                            return content.strip()
                        else:
                            logger.error("Invalid VLM response format", response=result)
                            return None
                    else:
                        error_text = await response.text()
                        logger.error("VLM service error", 
                                   status=response.status, error=error_text)
                        return None
                        
        except asyncio.TimeoutError:
            logger.error("VLM service timeout", timeout=self.vlm_timeout_seconds)
            return None
        except Exception as e:
            logger.error("VLM service call failed", error=str(e))
            return None
    
    def get_latest_analysis(self, intersection_id: str) -> Optional[VLMAnalysisResult]:
        """Get latest VLM analysis for an intersection."""
        return self.vlm_results.get(intersection_id)
    
    def clear_old_analyses(self, max_age_hours: int = 2) -> None:
        """Clear old VLM analysis results."""
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        to_remove = []
        for intersection_id, result in self.vlm_results.items():
            if result.timestamp < cutoff_time:
                to_remove.append(intersection_id)
        
        for intersection_id in to_remove:
            del self.vlm_results[intersection_id]
            
        if to_remove:
            logger.info("Cleared old VLM analyses", count=len(to_remove))
    
    def _update_traffic_window(self, state: IntersectionTrafficState, 
                              directional_densities: Dict[str, float], 
                              now: datetime) -> None:
        """Update the sliding traffic window for an intersection."""
        # Analyze current high density directions
        high_directions = self.analyze_high_density_directions(directional_densities)
        
        # Add current data point to window
        window_entry = TrafficWindow(
            timestamp=now,
            directional_densities=directional_densities.copy(),
            high_density_directions=high_directions
        )
        state.traffic_window.append(window_entry)
        
        # Remove old entries (keep only last 15 seconds)
        cutoff_time = now - timedelta(seconds=self.traffic_window_duration_seconds)
        state.traffic_window = [entry for entry in state.traffic_window 
                               if entry.timestamp >= cutoff_time]
        
        logger.debug("Updated traffic window", 
                   intersection_id=state.intersection_id,
                   window_size=len(state.traffic_window),
                   current_high_directions=high_directions)
    
    def _check_sustained_high_traffic(self, state: IntersectionTrafficState, 
                                     now: datetime) -> Optional[Dict[str, Any]]:
        """Check if there's sustained high traffic in the window."""
        if len(state.traffic_window) < 2:  # Need at least 2 data points
            return None
        
        # Find periods of sustained high traffic (3+ seconds)
        sustained_periods = []
        current_period = None
        
        for entry in state.traffic_window:
            if entry.high_density_directions:  # Has high traffic
                if current_period is None:
                    # Start new period
                    current_period = {
                        'start': entry.timestamp,
                        'end': entry.timestamp,
                        'directions': set(entry.high_density_directions),
                        'densities': [entry.directional_densities]
                    }
                else:
                    # Extend current period
                    current_period['end'] = entry.timestamp
                    current_period['directions'].update(entry.high_density_directions)
                    current_period['densities'].append(entry.directional_densities)
            else:
                # No high traffic, end current period if exists
                if current_period is not None:
                    duration = (current_period['end'] - current_period['start']).total_seconds()
                    if duration >= self.sustained_threshold_seconds:
                        sustained_periods.append(current_period)
                    current_period = None
        
        # Check if current period is still ongoing and sustained
        if current_period is not None:
            duration = (current_period['end'] - current_period['start']).total_seconds()
            if duration >= self.sustained_threshold_seconds:
                sustained_periods.append(current_period)
        
        if not sustained_periods:
            return None
        
        # Use the most recent sustained period
        latest_period = sustained_periods[-1]
        
        # Calculate average and peak densities during the sustained period
        avg_densities = {}
        peak_densities = {}
        
        for direction in ['northbound', 'southbound', 'eastbound', 'westbound']:
            values = [d[direction] for d in latest_period['densities']]
            avg_densities[direction] = sum(values) / len(values) if values else 0
            peak_densities[direction] = max(values) if values else 0
        
        return {
            'period_start': latest_period['start'],
            'period_end': latest_period['end'],
            'duration_seconds': (latest_period['end'] - latest_period['start']).total_seconds(),
            'high_directions': list(latest_period['directions']),
            'avg_densities': avg_densities,
            'peak_densities': peak_densities
        }
    
    def _uuid_to_intersection_name(self, uuid: str) -> str:
        """Convert UUID to readable intersection name for prompts."""
        # Hardcoded mapping from UUID to intersection name
        uuid_to_name = {
            "cb1cf1a0-b936-4d47-9221-3fd5cf24857d": "intersection-1",
            "8f2a4c5e-d9b1-4e3f-a2c8-1b5d7e9f3a6c": "intersection-2",
            "3d7b9e1f-c4a6-4f8e-b2d5-6a8c0e2f4b7d": "intersection-3",
            "9a4e6c2d-f1b8-4a3e-c7d9-5e8a1c4f6b9e": "intersection-4"
        }
        return uuid_to_name.get(uuid, f"intersection-{uuid[:8]}")  # Fallback to shortened UUID
