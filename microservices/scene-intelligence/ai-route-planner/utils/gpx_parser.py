from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import gpxpy

from config import DEFAULT_LOCATION_COORDINATES
from utils.logging_config import get_logger

logger = get_logger(__name__)


class MapDataParser:
    """
    A class for parsing GPX files using the gpxpy library.
    Provides methods to extract route data, bounds, and location information.
    """

    def __init__(self, gpx_file_path: str | Path | None = None):
        """
        Initialize the MapDataParser with an optional GPX file path.

        Args:
            gpx_file_path: Path to the GPX file (optional)
        """
        self.gpx_file_path = gpx_file_path
        self.gpx = None

        if self.gpx_file_path:
            self._load_gpx_file()

    def _load_gpx_file(self) -> bool:
        """
        Load and parse a GPX file.

        Args:
            gpx_file_path: Path to the GPX file

        Returns:
            bool: True if successful, False otherwise
        """
        gpx_file_path = self.gpx_file_path

        if not Path.exists(gpx_file_path):
            raise FileNotFoundError(f"GPX file not found: {gpx_file_path}")

        try:
            with open(gpx_file_path, "r") as gpx_file:
                self.gpx = gpxpy.parse(gpx_file)
            return True
        except Exception as e:
            print(f"Error parsing GPX file: {e}")
            return False

    def get_route_data(self) -> Dict[str, Any]:
        """
        Extract route information including waypoints and track points.

        Returns:
            dict: Contains metadata, waypoints, and track points
        """
        if not self.gpx:
            return {"metadata": {}, "waypoints": [], "track_points": []}

        # Extract metadata
        metadata = {
            "time": self.gpx.time.isoformat() if self.gpx.time else None,
            "name": self.gpx.name,
            "description": self.gpx.description,
        }

        # Extract waypoints
        waypoints = []
        for waypoint in self.gpx.waypoints:
            waypoints.append(
                {
                    "lat": waypoint.latitude,
                    "lon": waypoint.longitude,
                    "name": waypoint.name,
                    "description": waypoint.description,
                    "time": waypoint.time.isoformat() if waypoint.time else None,
                }
            )

        # Extract track points
        tracks = []
        for track in self.gpx.tracks:
            current_track = {}
            current_track["name"] = track.name
            current_track["track_points"] = []
            for segment in track.segments:
                for point in segment.points:
                    current_track["track_points"].append(
                        {
                            "lat": point.latitude,
                            "lon": point.longitude,
                            "time": point.time.isoformat() if point.time else None,
                        }
                    )
            tracks.append(current_track)

        return {"metadata": metadata, "waypoints": waypoints, "tracks": tracks}

    def get_waypoints(self):
        if not self.gpx:
            return []
        return [
            {
                "lat": waypoint.latitude,
                "lon": waypoint.longitude,
                "name": waypoint.name,
                "description": waypoint.description,
                "time": waypoint.time.isoformat() if waypoint.time else None,
            }
            for waypoint in self.gpx.waypoints
        ]

    def get_route_bounds(self) -> Optional[Dict[str, float]]:
        """
        Calculate the bounding box of the route.

        Returns:
            dict: Contains min_lat, max_lat, min_lon, max_lon
        """
        if not self.gpx:
            return None

        min_lat, max_lat, min_lon, max_lon = self.gpx.get_bounds()

        return {
            "min_lat": min_lat,
            "max_lat": max_lat,
            "min_lon": min_lon,
            "max_lon": max_lon,
        }

    def get_start_end_locations(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract start and end locations from waypoints.

        Returns:
            tuple: (start_location, end_location) or (None, None) if not found
        """
        if not self.gpx or not self.gpx.waypoints or len(self.gpx.waypoints) < 2:
            return None, None

        start = self.gpx.waypoints[0]
        end = self.gpx.waypoints[-1]

        start_name = start.description if start.description else start.name
        end_name = end.description if end.description else end.name

        return start_name, end_name

    def calculate_center_and_zoom(self) -> Tuple[float, float, int]:
        """
        Calculate the center point and appropriate zoom level for the route.

        Returns:
            tuple: (center_lat, center_lon, zoom_level)
        """
        bounds = self.get_route_bounds()
        if not bounds:
            # Get Berkeley Coordinates and default to Berkeley with higher zoom
            default_lat, default_lon = DEFAULT_LOCATION_COORDINATES[
                "Berkeley, California"
            ]
            return default_lat, default_lon, 12

        center_lat = (bounds["min_lat"] + bounds["max_lat"]) / 2
        center_lon = (bounds["min_lon"] + bounds["max_lon"]) / 2

        # Calculate zoom level based on the span of coordinates
        lat_span = bounds["max_lat"] - bounds["min_lat"]
        lon_span = bounds["max_lon"] - bounds["min_lon"]
        max_span = max(lat_span, lon_span)

        # Zoom level calculation (approximate)
        if max_span > 10:
            zoom = 5
        elif max_span > 5:
            zoom = 6
        elif max_span > 2:
            zoom = 7
        elif max_span > 1:
            zoom = 8
        elif max_span > 0.5:
            zoom = 9
        elif max_span > 0.25:
            zoom = 10
        elif max_span > 0.1:
            zoom = 11
        elif max_span > 0.05:
            zoom = 12
        else:
            zoom = 13

        return center_lat, center_lon, zoom

    def get_total_distance(self) -> float:
        """
        Calculate the total distance of the route in kilometers.

        Returns:
            float: Total distance in kilometers
        """
        if not self.gpx:
            return 0.0

        return self.gpx.length_3d() / 1000  # Convert meters to kilometers
