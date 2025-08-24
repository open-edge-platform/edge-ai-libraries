import csv
from typing import Optional

from config import ROUTE_STATUS_DIR, WeatherStatus
from controllers.route_status import RouteStatusInterface
from schema import GeoCoordinates, WeatherData
from utils.logging_config import get_logger

logger = get_logger(__name__)


class WeatherReportController(RouteStatusInterface):
    """
    Controller for handling weather report data
    """

    WEATHER_REPORT_CSV: str = "weather_report.csv"

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
        # Match for large areas around ~500x500 Sq.Mtr.
        return 0.005

    def fetch_route_status(self) -> Optional[WeatherData]:
        """
        Fetch the weather report for the location from data/csv/weather_report.csv based on latitude and longitude.
        """
        # Get the data from CSV and return using proper schema
        with open(ROUTE_STATUS_DIR / self.WEATHER_REPORT_CSV, "r") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if (
                    abs(float(row["latitude"]) - self.latitude) <= self.proximity_factor
                    and abs(float(row["longitude"]) - self.longitude)
                    <= self.proximity_factor
                ):
                    # Attempt to read the weather condition as predefined enum
                    try:
                        weather_condition = WeatherStatus(row["condition"])
                    except ValueError:
                        # Graceful handling: Set a default positive value instead of raising error
                        weather_condition = WeatherStatus.CLEAR

                    return WeatherData(
                        location_coordinates=GeoCoordinates(
                            latitude=self.latitude, longitude=self.longitude
                        ),
                        weather_condition=weather_condition,
                        temperature=float(row["temperature"]),
                        visibility=float(row["visibility"]),
                    )

        # No Data available for given coordinates
        return None
