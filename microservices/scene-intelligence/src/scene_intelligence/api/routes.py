"""API routes for Scene Intelligence service."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..services.directional_traffic_service import DirectionalTrafficService


logger = structlog.get_logger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    timestamp: datetime
    service: str


class VLMThresholdUpdate(BaseModel):
    """VLM threshold update model."""
    threshold: float = Field(gt=0, description="High traffic density threshold for VLM analysis")


def get_directional_traffic_service(request: Request) -> DirectionalTrafficService:
    """Dependency to get directional traffic service."""
    return getattr(request.app.state, "directional_traffic", None)


def get_image_service(request: Request):
    """Dependency to get image service."""
    return getattr(request.app.state, "image_service", None)


def get_mqtt_publisher(request: Request):
    """Dependency to get MQTT publisher service."""
    return getattr(request.app.state, "mqtt_publisher", None)


def get_vlm_service(request: Request):
    """Dependency to get VLM service."""
    return getattr(request.app.state, "vlm_service", None)


# @router.get("/health", response_model=HealthResponse)
# async def health_check():
#     """Extended health check endpoint."""
#     return HealthResponse(
#         status="healthy", timestamp=datetime.utcnow(), service="scene-intelligence"
#     )


@router.get("/config")
async def get_service_config(request: Request):
    """Get service configuration."""
    try:
        config = request.app.state.config

        # Return a sanitized config without sensitive information
        public_config = {
            "service": config.get("service", {}),
            "intersections": list(config.get_intersections().keys()),
            "regions_configured": True,
            "mqtt_enabled": True,
        }

        return {
            "status": "success",
            "config": public_config,
            "timestamp": datetime.utcnow(),
        }

    except Exception as e:
        logger.error("Failed to get config", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get config: {str(e)}")


@router.get("/status")
async def get_service_status(request: Request):
    """Get comprehensive service status."""
    try:
        config = request.app.state.config

        # Base status
        status = {
            "service": "scene-intelligence",
            "version": "1.0.0",
            "status": "running",
            "timestamp": datetime.utcnow(),
            "components": {"mqtt": "unknown", "directional_traffic": "unknown", "image_service": "unknown"},
        }

        # Check MQTT connection
        if hasattr(request.app.state, "mqtt"):
            mqtt_service = request.app.state.mqtt
            try:
                if mqtt_service.is_connected():
                    status["components"]["mqtt"] = "connected"
                else:
                    status["components"]["mqtt"] = "disconnected"
            except Exception:
                status["components"]["mqtt"] = "error"

        # Check directional traffic service
        if hasattr(request.app.state, "directional_traffic"):
            directional_service = request.app.state.directional_traffic
            try:
                # Check if service is properly initialized
                if directional_service and hasattr(
                    directional_service, "get_all_intersections_directional_summary"
                ):
                    status["components"]["directional_traffic"] = "available"
                else:
                    status["components"]["directional_traffic"] = "unavailable"
            except Exception:
                status["components"]["directional_traffic"] = "error"

        # Check image service
        if hasattr(request.app.state, "image_service"):
            image_service = request.app.state.image_service
            try:
                # Check if service is properly initialized
                if image_service and hasattr(image_service, "get_camera_stats"):
                    status["components"]["image_service"] = "available"
                    # Add basic image stats
                    try:
                        stats = image_service.get_camera_stats()
                        status["image_stats"] = {
                            "total_images_processed": stats.get("total_images_processed", 0),
                            "cameras_active": stats.get("cameras_active", 0),
                            "recent_images_count": stats.get("recent_images_count", 0)
                        }
                    except Exception:
                        pass
                else:
                    status["components"]["image_service"] = "unavailable"
            except Exception:
                status["components"]["image_service"] = "error"

        return status

    except Exception as e:
        logger.error("Failed to get status", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.get("/traffic/directional/summary")
async def get_directional_traffic_summary(
    directional_service: DirectionalTrafficService = Depends(
        get_directional_traffic_service
    ),
    image_service = Depends(get_image_service),
    mqtt_publisher = Depends(get_mqtt_publisher),
    vlm_service = Depends(get_vlm_service),
):
    """Get directional traffic summary for all intersections with camera images."""
    try:
        if not directional_service:
            raise HTTPException(
                status_code=503, detail="Directional traffic service not available"
            )

        logger.info("Getting directional traffic summary")

        # First, quickly identify intersections with high traffic density
        high_density_intersections = []
        if vlm_service and directional_service:
            try:
                # Get current traffic data to identify high-density intersections
                current_summary = directional_service.get_all_intersections_directional_summary()
                if current_summary and current_summary.intersections:
                    for intersection_data in current_summary.intersections:
                        intersection_id = intersection_data.intersection_id
                        directional_densities = {
                            "northbound": intersection_data.northbound_density,
                            "southbound": intersection_data.southbound_density,
                            "eastbound": intersection_data.eastbound_density,
                            "westbound": intersection_data.westbound_density
                        }
                        
                        # Check if this intersection has high traffic density
                        high_directions = vlm_service.analyze_high_density_directions(directional_densities)
                        if high_directions:
                            high_density_intersections.append(intersection_id)
                
                logger.info("Identified high-density intersections", 
                           high_density_intersections=high_density_intersections,
                           threshold=vlm_service.get_high_traffic_threshold())
            except Exception as e:
                logger.warning("Failed to identify high-density intersections", error=str(e))

        # Send getimage commands only to cameras for high-density intersections
        if mqtt_publisher:
            if high_density_intersections:
                logger.info("Sending getimage commands to high-density intersections only", 
                           intersections=high_density_intersections)
                
                # Mark image requests in VLM service to coordinate
                if vlm_service:
                    for intersection_id in high_density_intersections:
                        vlm_service.mark_image_request(intersection_id)
                
                send_success = await mqtt_publisher.send_getimage_commands_for_intersections(high_density_intersections)
                if send_success:
                    logger.info("Successfully sent getimage commands to high-density intersections, waiting for images...")
                    # Wait a bit for cameras to publish fresh images
                    await asyncio.sleep(3)  # 3 seconds should be enough for cameras to respond
                else:
                    logger.warning("Failed to send getimage commands to high-density intersections")
            else:
                logger.info("No high-density intersections found, not requesting images")
        else:
            logger.warning("MQTT publisher not available, using existing images")

        # Get summary data from directional traffic service
        summary = directional_service.get_all_intersections_directional_summary()

        if not summary or summary.total_intersections == 0:
            logger.warning("No directional traffic data available")
            return {
                "timestamp": datetime.utcnow(),
                "intersections": {},
                "total_density": {
                    "northbound": 0,
                    "southbound": 0,
                    "eastbound": 0,
                    "westbound": 0,
                },
                "message": "No traffic data available",
            }

        # Convert dataclass to dictionary for JSON serialization
        from dataclasses import asdict

        summary_dict = asdict(summary)
        
        # VLM Analysis - Check if any intersection has high traffic density and get VLM analysis
        high_density_intersections = []
        if vlm_service:
            try:
                for intersection in summary_dict["intersections"]:
                    intersection_id = intersection["intersection_id"]
                    
                    # Extract directional densities from the intersection data
                    directional_densities = {
                        "northbound": intersection.get("northbound_density", 0),
                        "southbound": intersection.get("southbound_density", 0),
                        "eastbound": intersection.get("eastbound_density", 0),
                        "westbound": intersection.get("westbound_density", 0)
                    }
                    
                    # Use VLM service's shared method to analyze high density directions
                    high_directions = vlm_service.analyze_high_density_directions(directional_densities)
                    
                    # Always try to get VLM analysis for this intersection (not just when high traffic)
                    vlm_analysis = vlm_service.get_latest_analysis(intersection_id)
                    
                    if high_directions:
                        high_density_intersections.append(intersection_id)
                    
                    if vlm_analysis:
                        # Enhanced VLM analysis with traffic context
                        analysis_data = {
                            "analysis": vlm_analysis.analysis,
                            "high_density_directions": vlm_analysis.high_density_directions,
                            "analysis_timestamp": vlm_analysis.timestamp.isoformat(),
                            "confidence": vlm_analysis.confidence,
                            "current_high_directions": high_directions,  # Current state
                            "analysis_age_minutes": round((datetime.utcnow() - vlm_analysis.timestamp).total_seconds() / 60, 1)
                        }
                        
                        # Add traffic context if available (from windowed analysis)
                        if hasattr(vlm_analysis, 'analysis_period_start') and vlm_analysis.analysis_period_start:
                            analysis_data["traffic_context"] = {
                                "analysis_period": {
                                    "start": vlm_analysis.analysis_period_start.isoformat(),
                                    "end": vlm_analysis.analysis_period_end.isoformat(),
                                    "duration_seconds": (vlm_analysis.analysis_period_end - vlm_analysis.analysis_period_start).total_seconds()
                                },
                                "avg_densities": vlm_analysis.avg_densities,
                                "peak_densities": vlm_analysis.peak_densities
                            }
                        
                        # Add camera images if stored with VLM analysis
                        if hasattr(vlm_analysis, 'camera_images') and vlm_analysis.camera_images:
                            analysis_data["camera_images"] = vlm_analysis.camera_images
                        
                        intersection["vlm_analysis"] = analysis_data
                        logger.info("Added enhanced VLM analysis to intersection", 
                                  intersection_id=intersection_id,
                                  current_high_directions=high_directions,
                                  analysis_age_minutes=round((datetime.utcnow() - vlm_analysis.timestamp).total_seconds() / 60, 1))
                    elif high_directions:
                        # High traffic but no VLM analysis available
                        intersection["vlm_analysis"] = {
                            "analysis": "High traffic density detected but no VLM analysis available yet",
                            "high_density_directions": high_directions,
                            "analysis_timestamp": None,
                            "confidence": None,
                            "current_high_directions": high_directions,
                            "analysis_age_minutes": None
                        }
                        logger.info("High traffic detected but no VLM analysis available", 
                                  intersection_id=intersection_id,
                                  high_directions=high_directions)

                summary_dict["high_density_intersections"] = high_density_intersections
                summary_dict["vlm_threshold"] = vlm_service.get_high_traffic_threshold()

                logger.info("VLM analysis complete", 
                          high_density_intersections=high_density_intersections,
                          threshold=vlm_service.get_high_traffic_threshold())

            except Exception as e:
                logger.warning("Failed to perform VLM analysis", error=str(e))
        else:
            logger.warning("VLM service not available")
            
        # Add camera images - prioritize VLM analysis stored images, fallback to fresh images for high density
        if image_service:
            for intersection_data in summary_dict["intersections"]:
                intersection_id = intersection_data["intersection_id"]
                
                # Check if VLM analysis has stored camera images
                vlm_analysis_in_intersection = intersection_data.get("vlm_analysis")
                if vlm_analysis_in_intersection and "camera_images" in vlm_analysis_in_intersection:
                    # Use camera images stored with VLM analysis for consistency and retention
                    intersection_data["camera_images"] = vlm_analysis_in_intersection["camera_images"]
                    logger.debug("Using VLM analysis stored camera images", 
                               intersection_id=intersection_id, 
                               image_count=len(vlm_analysis_in_intersection["camera_images"]))
                elif intersection_id in high_density_intersections:
                    # Only add fresh images if this intersection currently has high density and no VLM stored images
                    camera_images = image_service.get_intersection_images_by_scene_uuid(intersection_id, max_age_minutes=3)
                    intersection_data["camera_images"] = camera_images
                    logger.debug("Added fresh camera images to high-density intersection", 
                               intersection_id=intersection_id, 
                               image_count=len(camera_images))
                else:
                    # No images for normal/low density intersections without VLM analysis
                    intersection_data["camera_images"] = {}
                    logger.debug("No images added for normal-density intersection", 
                               intersection_id=intersection_id)
        else:
            logger.warning("Image service not available")
            # Set empty camera_images for all intersections
            for intersection_data in summary_dict["intersections"]:
                intersection_data["camera_images"] = {}

        return {
            "timestamp": datetime.utcnow(),
            "data": summary_dict,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get directional traffic summary", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get directional traffic summary: {str(e)}",
        )


@router.get("/traffic/directional/intersection/{intersection_id}")
async def get_intersection_directional_traffic(
    intersection_id: str,
    directional_service: DirectionalTrafficService = Depends(
        get_directional_traffic_service
    ),
    image_service = Depends(get_image_service),
    mqtt_publisher = Depends(get_mqtt_publisher),
    vlm_service = Depends(get_vlm_service),
):
    """Get directional traffic data for a specific intersection with camera images."""
    try:
        if not directional_service:
            raise HTTPException(
                status_code=503, detail="Directional traffic service not available"
            )

        logger.info(
            "Getting directional traffic for intersection",
            intersection_id=intersection_id,
        )

        # First, check if this specific intersection has high traffic density
        should_request_images = False
        if vlm_service and directional_service:
            try:
                # Get current data for this specific intersection
                current_data = directional_service.get_intersection_directional_data(intersection_id)
                if current_data:
                    directional_densities = {
                        "northbound": current_data.northbound_density,
                        "southbound": current_data.southbound_density,
                        "eastbound": current_data.eastbound_density,
                        "westbound": current_data.westbound_density
                    }
                    
                    # Check if this intersection has high traffic density
                    high_directions = vlm_service.analyze_high_density_directions(directional_densities)
                    should_request_images = bool(high_directions)
                    
                    logger.info("Checked intersection traffic density", 
                               intersection_id=intersection_id,
                               high_directions=high_directions,
                               should_request_images=should_request_images,
                               threshold=vlm_service.get_high_traffic_threshold())
            except Exception as e:
                logger.warning("Failed to check intersection traffic density", 
                             intersection_id=intersection_id, error=str(e))

        # Send getimage commands only if this intersection has high traffic density
        if mqtt_publisher:
            if should_request_images:
                logger.info("Sending getimage commands for high-density intersection", 
                           intersection_id=intersection_id)
                
                # Mark image request in VLM service to coordinate
                if vlm_service:
                    vlm_service.mark_image_request(intersection_id)
                
                send_success = await mqtt_publisher.send_getimage_commands_for_intersections([intersection_id])
                if send_success:
                    logger.info("Successfully sent getimage commands for intersection, waiting for images...",
                               intersection_id=intersection_id)
                    # Wait a bit for cameras to publish fresh images
                    await asyncio.sleep(3)  # 3 seconds should be enough for cameras to respond
                else:
                    logger.warning("Failed to send getimage commands for intersection",
                                 intersection_id=intersection_id)
            else:
                logger.info("Intersection traffic density below threshold, not requesting images",
                           intersection_id=intersection_id)
        else:
            logger.warning("MQTT publisher not available, using existing images")

        # Get data for specific intersection
        data = directional_service.get_intersection_directional_data(intersection_id)

        if not data:
            logger.warning(
                "No directional traffic data for intersection",
                intersection_id=intersection_id,
            )
            return {
                "timestamp": datetime.utcnow(),
                "intersection_id": intersection_id,
                "directional_density": {
                    "northbound": 0,
                    "southbound": 0,
                    "eastbound": 0,
                    "westbound": 0,
                },
                "camera_images": {},
                "message": f"No traffic data available for intersection {intersection_id}",
            }

        # Convert dataclass to dictionary for JSON serialization
        from dataclasses import asdict

        data_dict = asdict(data)
        
        # VLM Analysis - Check if this intersection has high traffic density for proper image inclusion
        is_high_density = False
        vlm_analysis_result = None
        if vlm_service:
            try:
                # Get density values from the DirectionalTrafficData object
                northbound_density = data.northbound_density
                southbound_density = data.southbound_density
                eastbound_density = data.eastbound_density
                westbound_density = data.westbound_density
                
                # Create directional densities dict for VLM service
                directional_densities = {
                    "northbound": northbound_density,
                    "southbound": southbound_density,
                    "eastbound": eastbound_density,
                    "westbound": westbound_density
                }
                
                # Check if this intersection currently has high density
                high_directions = vlm_service.analyze_high_density_directions(directional_densities)
                is_high_density = bool(high_directions)
                
                logger.debug("Checked intersection density for image inclusion", 
                           intersection_id=intersection_id,
                           directional_densities=directional_densities,
                           high_directions=high_directions,
                           is_high_density=is_high_density,
                           threshold=vlm_service.get_high_traffic_threshold())

                # Try to get existing VLM analysis
                vlm_analysis = vlm_service.get_latest_analysis(intersection_id)
                
                if vlm_analysis:
                    vlm_analysis_result = {
                        "analysis": vlm_analysis.analysis,
                        "high_density_directions": vlm_analysis.high_density_directions,
                        "analysis_timestamp": vlm_analysis.timestamp.isoformat(),
                        "confidence": vlm_analysis.confidence,
                        "current_high_directions": high_directions,  # Current state
                        "analysis_age_minutes": round((datetime.utcnow() - vlm_analysis.timestamp).total_seconds() / 60, 1)
                    }
                    
                    # Add traffic context if available (from windowed analysis)
                    if hasattr(vlm_analysis, 'analysis_period_start') and vlm_analysis.analysis_period_start:
                        vlm_analysis_result["traffic_context"] = {
                            "analysis_period": {
                                "start": vlm_analysis.analysis_period_start.isoformat(),
                                "end": vlm_analysis.analysis_period_end.isoformat(),
                                "duration_seconds": (vlm_analysis.analysis_period_end - vlm_analysis.analysis_period_start).total_seconds()
                            },
                            "avg_densities": vlm_analysis.avg_densities,
                            "peak_densities": vlm_analysis.peak_densities
                        }
                    
                    # Add camera images if stored with VLM analysis
                    if hasattr(vlm_analysis, 'camera_images') and vlm_analysis.camera_images:
                        vlm_analysis_result["camera_images"] = vlm_analysis.camera_images
                    
                    logger.info("Added enhanced VLM analysis to intersection response", 
                              intersection_id=intersection_id,
                              current_high_directions=high_directions)
                elif high_directions:
                    # High traffic but no VLM analysis available yet
                    vlm_analysis_result = {
                        "analysis": "High traffic density detected but no VLM analysis available yet",
                        "high_density_directions": high_directions,
                        "analysis_timestamp": None,
                        "confidence": None,
                        "current_high_directions": high_directions,
                        "analysis_age_minutes": None
                    }
                    logger.info("High traffic detected but no VLM analysis available", 
                              intersection_id=intersection_id,
                              high_directions=high_directions)

            except Exception as e:
                logger.warning("Failed to perform VLM analysis for intersection", 
                             intersection_id=intersection_id, error=str(e))
        else:
            logger.warning("VLM service not available")
        
        # Add camera images - prioritize VLM analysis stored images, fallback to fresh images for high density
        camera_images = {}
        vlm_has_stored_images = False
        
        if vlm_analysis_result and "camera_images" in vlm_analysis_result:
            # Use camera images stored with VLM analysis for consistency and retention
            camera_images = vlm_analysis_result["camera_images"]
            vlm_has_stored_images = True
            logger.debug("Using VLM analysis stored camera images", 
                       intersection_id=intersection_id, 
                       image_count=len(camera_images))
        
        if image_service and not vlm_has_stored_images:
            try:
                if is_high_density:
                    # Use intersection_id as scene UUID for the new mapping method
                    scene_uuid = intersection_id
                    # Use fresh images only (3 minutes max age) to avoid stale images
                    intersection_images = image_service.get_intersection_images_by_scene_uuid(scene_uuid, max_age_minutes=3)
                    
                    if intersection_images:
                        camera_images = intersection_images
                        logger.debug("Added fresh camera images to high-density intersection", 
                                   intersection_id=intersection_id, 
                                   image_count=len(camera_images))
                    else:
                        logger.debug("No fresh camera images for high-density intersection", 
                                   intersection_id=intersection_id)
                else:
                    logger.debug("Intersection traffic density below threshold, not including images", 
                               intersection_id=intersection_id)
                    
            except Exception as e:
                logger.warning("Failed to get camera images for intersection", 
                             intersection_id=intersection_id, 
                             error=str(e))
        else:
            if not image_service:
                logger.warning("Image service not available")
            elif vlm_has_stored_images:
                logger.debug("Using VLM stored images, skipping fresh image fetch", 
                           intersection_id=intersection_id)

        # Construct response with camera images only if high density
        response_data = {
            "timestamp": datetime.utcnow(),
            "intersection_id": intersection_id,
            "data": data_dict,
            "camera_images": camera_images,  # Empty dict if not high density
        }
        
        # Add VLM analysis if available
        if vlm_analysis_result:
            response_data["vlm_analysis"] = vlm_analysis_result

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get intersection directional traffic",
            error=str(e),
            intersection_id=intersection_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get directional traffic for intersection {intersection_id}: {str(e)}",
        )


@router.get("/traffic/directional/regions/mapping")
async def get_region_mapping(
    directional_service: DirectionalTrafficService = Depends(
        get_directional_traffic_service
    ),
):
    """Get region to direction mapping for all intersections."""
    try:
        if not directional_service:
            raise HTTPException(
                status_code=503, detail="Directional traffic service not available"
            )

        logger.info("Getting region mapping")

        # Get region mapping from directional traffic service
        mapping = directional_service.get_region_mapping_info()

        return {"timestamp": datetime.utcnow(), "region_mapping": mapping}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get region mapping", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get region mapping: {str(e)}"
        )


@router.get("/cameras/images")
async def get_camera_images(
    intersection_id: Optional[str] = Query(None, description="Filter by intersection ID"),
    image_service = Depends(get_image_service),
):
    """Get camera images for all intersections or specific intersection."""
    try:
        if not image_service:
            raise HTTPException(
                status_code=503, detail="Image service not available"
            )

        logger.info("Getting camera images", intersection_id=intersection_id)

        if intersection_id:
            # Get images for specific intersection
            intersection_images = image_service.get_intersection_images(intersection_id, max_age_minutes=5)
            
            camera_images = {}
            if intersection_images:
                for direction, image in intersection_images.cameras.items():
                    camera_images[f"{direction}_camera"] = {
                        "camera_id": image.camera_id,
                        "direction": image.direction,
                        "timestamp": image.timestamp.isoformat(),
                        "image_base64": image.image_base64,
                        "image_size_bytes": image.image_size_bytes
                    }
            
            return {
                "timestamp": datetime.utcnow(),
                "intersection_id": intersection_id,
                "camera_images": camera_images,
            }
        else:
            # Get all images
            all_images = image_service.get_all_intersections_images(max_age_minutes=5)
            formatted_images = {}
            
            for intersection_id, intersection_images in all_images.items():
                camera_images = {}
                for direction, image in intersection_images.cameras.items():
                    camera_images[f"{direction}_camera"] = {
                        "camera_id": image.camera_id,
                        "direction": image.direction,
                        "timestamp": image.timestamp.isoformat(),
                        "image_base64": image.image_base64,
                        "image_size_bytes": image.image_size_bytes
                    }
                formatted_images[intersection_id] = camera_images
            
            return {
                "timestamp": datetime.utcnow(),
                "camera_images": formatted_images,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get camera images", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get camera images: {str(e)}"
        )


@router.get("/cameras/stats")
async def get_camera_stats(
    image_service = Depends(get_image_service),
):
    """Get statistics about camera images."""
    try:
        if not image_service:
            raise HTTPException(
                status_code=503, detail="Image service not available"
            )

        logger.info("Getting camera image statistics")

        stats = image_service.get_camera_stats()

        return {
            "timestamp": datetime.utcnow(),
            "camera_stats": stats,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get camera stats", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get camera stats: {str(e)}"
        )


@router.get("/debug/image-requests")
async def get_image_request_status(
    vlm_service = Depends(get_vlm_service),
):
    """Get debug information about image request coordination."""
    try:
        if not vlm_service:
            raise HTTPException(status_code=503, detail="VLM service not available")
        
        now = datetime.utcnow()
        request_status = {}
        
        for intersection_id, request_time in vlm_service.recent_image_requests.items():
            seconds_ago = (now - request_time).total_seconds()
            request_status[intersection_id] = {
                "last_request_time": request_time.isoformat(),
                "seconds_ago": round(seconds_ago, 1),
                "within_cooldown": seconds_ago < vlm_service.image_request_cooldown_seconds
            }
        
        return {
            "timestamp": now.isoformat(),
            "image_request_cooldown_seconds": vlm_service.image_request_cooldown_seconds,
            "recent_requests": request_status,
            "mqtt_publisher_available": vlm_service.mqtt_publisher is not None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get image request status", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get image request status: {str(e)}"
        )


@router.get("/config/vlm/threshold")
async def get_vlm_threshold(
    vlm_service = Depends(get_vlm_service),
):
    """Get current VLM high traffic threshold."""
    try:
        if not vlm_service:
            raise HTTPException(
                status_code=503, detail="VLM service not available"
            )

        threshold = vlm_service.get_high_traffic_threshold()
        
        return {
            "timestamp": datetime.utcnow(),
            "high_traffic_threshold": threshold,
            "description": "Traffic density threshold above which VLM analysis is triggered"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get VLM threshold", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get VLM threshold: {str(e)}"
        )


@router.put("/config/vlm/threshold")
async def update_vlm_threshold(
    threshold_update: VLMThresholdUpdate,
    vlm_service = Depends(get_vlm_service),
):
    """Update VLM high traffic threshold."""
    try:
        if not vlm_service:
            raise HTTPException(
                status_code=503, detail="VLM service not available"
            )

        vlm_service.update_high_density_threshold(threshold_update.threshold)
        
        return {
            "timestamp": datetime.utcnow(),
            "status": "success",
            "message": f"VLM threshold updated to {threshold_update.threshold}",
            "new_threshold": threshold_update.threshold
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update VLM threshold", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to update VLM threshold: {str(e)}"
        )


@router.get("/intersections")
async def get_intersections(
    request: Request,
    directional_service: DirectionalTrafficService = Depends(get_directional_traffic_service),
):
    """Get list of all available intersections with their IDs and names."""
    try:
        if not directional_service:
            raise HTTPException(
                status_code=503, detail="Directional traffic service not available"
            )

        logger.info("Getting list of intersections")

        # Get intersection configuration from app config
        config = request.app.state.config
        intersections_config = config.get_intersections()
        
        # Get region mapping to ensure intersection is actually configured
        region_mapping = directional_service.get_region_mapping_info()
        configured_scenes = region_mapping.get('mapping', {}).keys()
        
        # Build intersection list with both configured intersections and active scenes
        intersections = []
        
        # Add intersections from configuration that are also in region mapping
        for intersection_id, intersection_info in intersections_config.items():
            if intersection_id in configured_scenes:
                intersections.append({
                    "intersection_id": intersection_id,
                    "name": intersection_info.get("name", f"Intersection-{intersection_id[:8]}"),
                    "latitude": intersection_info.get("latitude"),
                    "longitude": intersection_info.get("longitude"),
                    "status": "configured"
                })
        
        # Add any active scenes that might not be in the intersection config
        for scene_id in configured_scenes:
            if scene_id not in intersections_config:
                # Generate a name for scenes not in config
                intersection_name = f"Intersection-{scene_id[:8]}"
                intersections.append({
                    "intersection_id": scene_id,
                    "name": intersection_name,
                    "latitude": None,
                    "longitude": None,
                    "status": "active_scene"
                })

        return {
            "timestamp": datetime.utcnow(),
            "total_intersections": len(intersections),
            "intersections": intersections,
            "usage_example": {
                "get_intersection_traffic": f"/api/v1/traffic/directional/intersection/{{intersection_id}}",
                "example_with_first_intersection": f"/api/v1/traffic/directional/intersection/{intersections[0]['intersection_id']}" if intersections else "No intersections available"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get intersections list", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get intersections list: {str(e)}"
        )



