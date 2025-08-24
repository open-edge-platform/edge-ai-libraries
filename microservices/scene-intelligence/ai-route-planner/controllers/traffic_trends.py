import csv
from typing import Optional

from config import ROUTE_STATUS_DIR, CongestionLevel
from controllers.route_status import RouteStatusInterface
from schema import GeoCoordinates, TrafficTrendsData
from utils.logging_config import get_logger

logger = get_logger(__name__)


class TrafficTrendsController(RouteStatusInterface):
    """
    Controller for handling traffic trends data
    """

    TRAFFIC_TRENDS_CSV: str = "traffic_trends.csv"

    def __init__(self, latitude: float, longitude: float):
        self._latitude = latitude
        self._longitude = longitude

    @property
    def latitude(self) -> float:
        return self._latitude

    @property
    def longitude(self) -> float:
        return self._longitude

    @property
    def proximity_factor(self) -> float:
        """
        A float integer to help consider nearby latitude and longitudes as matching location coordinates.
        """
        # Match for smaller areas around ~55x55 Sq.Mtr.
        return 0.0005

    def fetch_route_status(self) -> Optional[TrafficTrendsData]:
        """
        Fetch the historical traffic trends for the route based on provided latitude and longitude.
        """
        # Fetch data from CSV simulating a real data source
        with open(ROUTE_STATUS_DIR / self.TRAFFIC_TRENDS_CSV, "r") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if (
                    abs(float(row["latitude"]) - self.latitude) <= self.proximity_factor
                    and abs(float(row["longitude"]) - self.longitude)
                    <= self.proximity_factor
                ):
                    # Try to read congestion_level from CSV as enum
                    try:
                        congestion_level = CongestionLevel(row["congestion_level"])
                    except ValueError:
                        # Graceful handling: Set a default low value instead of raising error
                        congestion_level = CongestionLevel.LOW

                    return TrafficTrendsData(
                        location_coordinates=GeoCoordinates(
                            latitude=self.latitude, longitude=self.longitude
                        ),
                        congestion_level=congestion_level,
                        vehicle_count=row["vehicle_count"],
                        avg_speed=row["average_speed"],
                    )

        # No Data available for given coordinates
        return None
