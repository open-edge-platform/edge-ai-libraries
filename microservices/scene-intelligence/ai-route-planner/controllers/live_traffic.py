import requests
from typing import Optional, List

from config import (
    SCENE_INTELLIGENCE_API_BASE,
    SCENE_INTELLIGENCE_ENDPOINTS,
)
from controllers.route_status import RouteStatusInterface
from schema import GeoCoordinates, LiveTrafficData
from utils.logging_config import get_logger

logger = get_logger(__name__)


class LiveTrafficController(RouteStatusInterface):
    """
    Controller for handling live traffic data from an external API.
    """

    def __init__(self, latitude: Optional[float] = None, longitude: Optional[float] = None):
        self._latitude = latitude
        self._longitude = longitude

    @property
    def latitude(self) -> Optional[float]:
        return self._latitude

    @property
    def longitude(self) -> Optional[float]:
        return self._longitude

    @property
    def proximity_factor(self) -> float:
        """
        A float integer to help consider nearby latitude and longitudes as matching location coordinates.
        Uses the configured COORDINATE_MATCHING_PRECISION value.
        """
        return 0.0005    # Approx 50 meters

    def fetch_route_status(self) -> List[LiveTrafficData]:
        """
        Fetch the live traffic data from the Scene Intelligence API.

        Returns:
            list[LiveTrafficData]: List of traffic data for all intersections.
        """
        try:
            logger.info("Fetching live traffic data ...")
            # Construct the API URL
            api_url = f"{SCENE_INTELLIGENCE_API_BASE}{SCENE_INTELLIGENCE_ENDPOINTS['traffic_summary']}"
            
            # Make the API request
            response = requests.get(api_url)
            response.raise_for_status()  # Raise an exception for HTTP errors
            
            # Parse the response
            data = response.json()

            # List to store the final response as list of LiveTrafficData
            intersection_traffic_data = []
            
            # Look for intersections that match our current coordinates
            for intersection in data.get("data", {}).get("intersections", []):
                # Get the intersection's coordinates
                intersection_lat = intersection.get("latitude")
                intersection_lon = intersection.get("longitude")
                
                traffic_density = intersection.get("total_density", 0)
                
                # Get traffic description if available
                traffic_description = None
                vlm_analysis = intersection.get("vlm_analysis", {})
                if vlm_analysis and "analysis" in vlm_analysis:
                    traffic_description = vlm_analysis.get("analysis")
                
                # Get intersection images if available (base64 encoded)
                intersection_images = {}
                camera_images = intersection.get("camera_images", {})
                for camera_id, image_data in camera_images.items():
                    intersection_images[camera_id] = image_data.get("image_base64")

                # Create and return the LiveTrafficData
                intersection_traffic_data.append(
                    LiveTrafficData(
                        location_coordinates=GeoCoordinates(
                            latitude=intersection_lat,
                            longitude=intersection_lon,
                        ),
                        intersection_name=intersection.get("intersection_name", "Unknown Intersection"),
                        timestamp=intersection.get("timestamp", ""),
                        traffic_density=traffic_density,
                        traffic_description=traffic_description,
                        intersection_images=intersection_images,
                    )
                )
                    
            return intersection_traffic_data

        except Exception as e:
            logger.error(f"Error fetching live traffic data: {e}")
            return []
