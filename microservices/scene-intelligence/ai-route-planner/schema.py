from typing import List, Optional

from pydantic import BaseModel, Field
from typing_extensions import Annotated

from config import CongestionLevel, WeatherStatus


class GeoCoordinates(BaseModel):
    """Pydantic model for location information"""

    latitude: Annotated[float, Field(description="Latitude of the location")]
    longitude: Annotated[float, Field(description="Longitude of the location")]


class RouteCondition(BaseModel):
    """Pydantic model for route condition information"""

    location_coordinates: GeoCoordinates


class TrafficTrendsData(RouteCondition):
    """Pydantic model for historical traffic trends information"""

    vehicle_count: Annotated[
        int, Field(description="Number of vehicles observed historically in the area")
    ]
    avg_speed: Annotated[
        int, Field(description="Average movement speed of vehicles in the area")
    ]
    congestion_level: Annotated[
        CongestionLevel, Field(description="Current congestion level at the location")
    ]


class WeatherData(RouteCondition):
    """Pydantic model for weather information along a route"""

    weather_condition: Annotated[
        WeatherStatus, Field(description="Current weather condition at the location")
    ]
    temperature: Annotated[
        float, Field(description="Current temperature at the location in Fahrenheit")
    ]
    visibility: Annotated[
        float, Field(description="Current visibility at the location in miles")
    ]


class PlannedEventsData(RouteCondition):
    """Pydantic model for planned events information along a route"""

    event_name: Annotated[
        str, Field(description="Name of the planned event affecting the route")
    ]
    congestion_level: Annotated[
        CongestionLevel, Field(description="Current congestion level at the location")
    ]


class LiveTrafficData(RouteCondition):
    """Pydantic model for live traffic data from an external API"""

    intersection_name: Annotated[
        str, Field(description="Name of the intersection where traffic is being monitored")
    ]
    timestamp: Annotated[
        str, Field(description="Time when the traffic data was recorded")
    ]
    traffic_density: Annotated[
        int, Field(description="Number of vehicles at the intersection")
    ]
    traffic_description: Annotated[
        Optional[str], Field(description="Description of the traffic situation")
    ] = None
    intersection_images: Annotated[
        Optional[dict[str, str]], Field(description="Dictionary of base64 encoded images from different views of the intersection")
    ] = None


class RoutePoints(BaseModel):
    """Pydantic model for route coordinates"""

    main_route: List[List[float]]
    alternative_route: Optional[List[List[float]]] = None

    def get_all_points(self) -> List[List[float]]:
        """Get all route points for bounds calculation"""
        all_points = self.main_route.copy()
        if self.alternative_route:
            all_points.extend(self.alternative_route)
        return all_points
