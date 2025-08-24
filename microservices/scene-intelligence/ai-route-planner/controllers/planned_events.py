import csv
from typing import Optional

from config import ROUTE_STATUS_DIR, CongestionLevel
from controllers.route_status import RouteStatusInterface
from schema import GeoCoordinates, PlannedEventsData
from utils.logging_config import get_logger

logger = get_logger(__name__)


class PlannedEventsController(RouteStatusInterface):
    """
    Controller for handling planned events data
    """

    PLANNED_EVENTS_CSV: str = "planned_events.csv"

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
        # Match for very large areas around ~1x1 Sq.Kms.
        return 0.01

    def fetch_route_status(self) -> Optional[PlannedEventsData]:
        """
        Fetch the planned events information for the location from data/csv/planned_events.csv
        based on latitude and longitude.
        """
        # Get the data from CSV and return using proper schema
        with open(ROUTE_STATUS_DIR / self.PLANNED_EVENTS_CSV, "r") as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Check if coordinates are close enough (within a small radius)
                if (
                    abs(float(row["latitude"]) - self.latitude) <= self.proximity_factor
                    and abs(float(row["longitude"]) - self.longitude)
                    <= self.proximity_factor
                ):
                    # Try to read traffic_impact from CSV as CongestionLevel enum
                    try:
                        congestion_level = CongestionLevel(row["traffic_impact"])
                    except ValueError:
                        # Graceful handling: Set a default low value instead of raising error
                        congestion_level = CongestionLevel.LOW

                    return PlannedEventsData(
                        location_coordinates=GeoCoordinates(
                            latitude=self.latitude, longitude=self.longitude
                        ),
                        congestion_level=congestion_level,
                        event_name=row["event_name"],
                    )

        # No Data available for given coordinates
        return None
