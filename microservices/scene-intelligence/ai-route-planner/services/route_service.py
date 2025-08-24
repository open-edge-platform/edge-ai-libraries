from typing import Dict, List, Optional, Tuple

from agents import RoutePlanner, RoutePlannerState
from config import (
    DEFAULT_LOCATION_COORDINATES,
    DEFAULT_LOCATIONS,
    GPX_DIR,
    MAP_COLORS,
    StaticOptimizerName,
)
from utils.gpx_parser import MapDataParser
from utils.logging_config import get_logger
from utils.map_creator import MapCreator
from schema import GeoCoordinates

logger = get_logger(__name__)


class RouteService:
    """Service class to handle :
    - Route loading
    - Trigger Route Planner agent
    - Map Creation.
    """

    def __init__(self):
        self.map_creator: MapCreator = MapCreator()
        self.route_planner: RoutePlanner = RoutePlanner()

        self.main_route: Optional[Dict] = None
        self.alternate_route: Optional[Dict] = None
        self.alt_route_trackpoints: list[list] = []
        self.route_state: Optional[RoutePlannerState] = None

        self.locations: List[str] = DEFAULT_LOCATIONS
        self.location_coordinates: Dict[str, List[float]] = DEFAULT_LOCATION_COORDINATES

    def _load_direct_shortest_route(
        self, source: str, destination: str
    ) -> MapDataParser:
        """Load the shortest trivial route data using the RoutePlanner agent at startup"""

        try:
            # Running the agent for first time - finds direct trivial route.
            self.route_state: RoutePlannerState = self.route_planner.plan_route(
                source, destination
            )

            direct_route_name = self.route_state["direct_route"]["route_name"]
            map_data_parser = MapDataParser(GPX_DIR / direct_route_name)
            self.main_route = map_data_parser.get_route_data()

            logger.info(
                f"Successfully loaded shortest route between {source} and {destination}: {direct_route_name}"
            )
            logger.info(f"Found {len(self.main_route['waypoints'])} waypoints")
            logger.info(
                f"Found {len(self.main_route['tracks'][0]['track_points'])} track points"
            )

            return map_data_parser

        except Exception as e:
            logger.error(f"Error loading direct route file: {e}")
            self.main_route = None

    def _setup_locations(self, map_data_parser: MapDataParser) -> None:
        """Setup location lists based on GPX data if available"""
        if map_data_parser:
            start_location, end_location = map_data_parser.get_start_end_locations()
            if start_location and end_location:
                self.locations = [start_location, end_location]

        if self.main_route and self.main_route["waypoints"]:
            # Create coordinates mapping from GPX waypoints if available
            for waypoint in self.main_route["waypoints"]:
                name = waypoint.get("description", waypoint.get("name", "Unknown"))
                if name and name != "Unknown":
                    self.location_coordinates[name] = [waypoint["lat"], waypoint["lon"]]

    def _load_alternate_route(self, source: str, destination: str) -> None:
        """Load an alternate route using RoutePlanner Agent"""

        try:
            # Pass the previous saved route_state and get the updated state as result
            self.route_state: RoutePlannerState = self.route_planner.plan_route(
                source, destination, self.route_state
            )
            alternate_route_name = self.route_state["optimal_route"]["route_name"]

            temp_parser = MapDataParser(GPX_DIR / alternate_route_name)
            self.alternate_route = temp_parser.get_route_data()

            logger.info(
                f"Successfully loaded alternate route file: {alternate_route_name}"
            )
            logger.info(f"Found {len(self.alternate_route['waypoints'])} waypoints")
            logger.info(
                f"Found {len(self.alternate_route['tracks'][0]['track_points'])} track points"
            )

        except Exception as e:
            logger.error(f"Error loading alternate route : {e}")
            self.alternate_route = None

    def _get_route_trackpoints(self, route: Optional[Dict] = None) -> List[List[float]]:
        """
        Get track points from GPX data.
        """
        if not route:
            route = self.main_route

        if route and route.get("tracks"):
            # Convert GPX track points to coordinate list
            trackpoints = []
            for track in route["tracks"]:
                for track_point in track["track_points"]:
                    trackpoints.append([track_point["lat"], track_point["lon"]])
            return trackpoints
        else:
            raise Exception("No track points found in the route!")

    def _get_route_waypoints(self, route: Optional[Dict] = None) -> List[List[float]]:
        """
        Get Waypoints from GPX data.
        """
        if not route:
            route = self.main_route

        if route and route.get("waypoints"):
            # Convert GPX waypoints to coordinate list
            waypoints = []
            for point in route["waypoints"]:
                waypoints.append([point["lat"], point["lon"]])
            return waypoints
        else:
            logger.info("No waypoints found in the route!")
            return []

    def _get_route_issue_detail(self) -> str:
        """Get a detailed description of traffic issues with the route planning"""

        route_issue: str = ""

        if not self.route_state:
            logger.error("No route details found. route_state is not defined.")
            return route_issue

        optimal_route_data = self.route_state.get("optimal_route", {})
        if not optimal_route_data:
            logger.error("Optimal Route info not present in route_state")
            return route_issue

        if event_name := optimal_route_data.get("event_name"):
            congestion_level = optimal_route_data.get("traffic_history")
            route_issue = f"planned event '{event_name}' with expected {congestion_level.value} traffic congestion on the route."
        elif congestion_level := optimal_route_data.get("traffic_history"):
            route_issue = f"'{congestion_level.value}' historical traffic trends on the route."
        elif weather_condition := optimal_route_data.get("weather_status"):
            route_issue = f"'{weather_condition.value}' weather condition on the route."
        elif live_traffic := self.route_state.get("live_traffic", {}):
            if live_traffic.get("traffic_density", 0) > 0:
                route_issue = f"high traffic density of {live_traffic.get('traffic_density')} at {live_traffic.get('intersection_name')}"
                if live_traffic.get("traffic_description"):
                    route_issue += f" - {live_traffic.get('traffic_description')[:900]} ..."

        return route_issue

    def _get_next_data_source(self) -> str:
        """
        Get the next data source for route updates
        This information is used to display what conditions agent is going to analyze next.
        """

        if self.route_state.get("static_optimizers"):
            # If any static optimizer is available, it will be used as next data source to optimize route
            optimizer: StaticOptimizerName = self.route_state["static_optimizers"][-1]
            # Get description respective to the StaticOptimizerName
            return optimizer.get_description()
        else:
            return "Real-Time Traffic Scenarios"

    def get_default_locations(self) -> Tuple[str, str]:
        """Get default start and end locations"""
        return (
            self.locations[0] if len(self.locations) > 0 else "Berkeley, California",
            self.locations[-1] if len(self.locations) > 1 else "Santa Clara, California",
        )

    def create_direct_route_map(
        self, start_location: str, end_location: str
    ) -> tuple[str, str]:
        """Create initial map showing only the main route before AI analysis"""
        map_data_parser: MapDataParser = self._load_direct_shortest_route(
            start_location, end_location
        )

        # Setup location name and coordinates for the direct route.
        self._setup_locations(map_data_parser)

        # Get the next data source to be used for route optimization and current route map
        next_data_source = self._get_next_data_source()
        direct_route_map = self.create_route_map(start_location, end_location)
        return next_data_source, direct_route_map

    def create_alternate_route_map(
        self, start_location: str, end_location: str
    ) -> tuple[str, str, str, Optional[dict[str, str]]]:
        """Create map showing alternative route"""

        self._load_alternate_route(start_location, end_location)

        # Get issue details which triggered alternative route selection
        alternate_planning_reason: str = self._get_route_issue_detail()

        # Get the next data source to be used for route optimization
        next_data_source = self._get_next_data_source()
        
        # Get intersection images and lat and long for route incidents (if any) from live traffic data
        incident_location: Optional[GeoCoordinates] = None
        intersection_images: Optional[dict[str, str]] = None
        if live_traffic := self.route_state.get("live_traffic", {}):
            intersection_images = live_traffic.get("intersection_images")
            incident_location = live_traffic.get("location_coordinates")

        # Create alternate route map for the alternate route
        alternate_map = self.create_route_map(start_location, end_location, incident_location)

        return next_data_source, alternate_planning_reason, alternate_map, intersection_images

    def create_route_map(self, start_location: str, end_location: str, incident_location: Optional[GeoCoordinates] = None) -> str:
        """Create a complete route map with all routes and markers"""
        # Get coordinates for the selected locations
        start_coords = self.location_coordinates.get(start_location)
        end_coords = self.location_coordinates.get(end_location)

        if not start_coords or not end_coords:
            logger.error(
                f"Invalid start or end coordinates for route: {start_location} to {end_location}"
            )
            return "Error: Invalid route"

        # Load main route details (trackpoints and waypoints)
        main_route_trackpoints = (
            self._get_route_trackpoints(self.main_route)
            if self.main_route
            else self.map_creator.generate_realistic_route(start_coords, end_coords)
        )

        # Load alternative route if conditions detected
        route_info = {}
        if self.alternate_route and self.route_state:
            self.alt_route_trackpoints.append(
                self._get_route_trackpoints(self.alternate_route)
            )

            # Determine alternative route styling
            route_info = {
                "color": MAP_COLORS["optimal_route"],
                "label": f"Alternate Optimal Route from {start_location} to {end_location}",
                "points": len(self.alt_route_trackpoints[-1]),
            }

        # Calculate map center and zoom
        all_points = main_route_trackpoints[:]
        if self.alt_route_trackpoints:
            all_points.extend(self.alt_route_trackpoints[-1])

        center_lat, center_lon, zoom = self.map_creator.calculate_map_center_and_zoom(
            all_points
        )

        # Create base map
        map_obj = self.map_creator.create_base_map(center_lat, center_lon, zoom)

        # Add alternative route if available
        if self.alt_route_trackpoints:
            # Draw the direct route with dull color
            self.map_creator.add_route_line(
                map_obj,
                main_route_trackpoints,
                MAP_COLORS["non_optimal_route_direct"],
                f"Non-Optimal Route from {start_location} to {end_location}",
            )
            # Draw all the alternative routes with a different style
            for i, alt_route in enumerate(self.alt_route_trackpoints):
                self.map_creator.add_route_line(
                    map_obj,
                    alt_route,
                    MAP_COLORS["non_optimal_route"] if i < len(self.alt_route_trackpoints) - 1 else MAP_COLORS["optimal_route"],
                    f"Alternate Route {i + 1} from {start_location} to {end_location}",
                )
        else:
            # If no alternate routes available show only main routes
            self.map_creator.add_route_line(
                map_obj,
                main_route_trackpoints,
                MAP_COLORS["main_route"],
                f"Direct Shortest Route from {start_location} to {end_location}",
            )

        # Add location markers
        self.map_creator.add_location_markers(
            map_obj, start_location, end_location, start_coords, end_coords
        )

        if incident_location:
            self.map_creator.add_incident_marker(
                map_obj, incident_location.latitude, incident_location.longitude
            )

        # Add waypoint markers for longer routes using trackpoints
        if main_route_trackpoints and len(main_route_trackpoints) > 10:
            self.map_creator.add_waypoint_markers(map_obj, main_route_trackpoints)

        if (
            self.alt_route_trackpoints
            and len(self.alt_route_trackpoints) > 0
            and len(self.alt_route_trackpoints[-1]) > 10
        ):
            self.map_creator.add_waypoint_markers(
                map_obj, self.alt_route_trackpoints[-1]
            )

        # Create route info box
        data_source = "GPX Route Data" if main_route_trackpoints else "Synthetic Route"
        route_info_html = self.map_creator.create_route_info_box(
            start_location,
            end_location,
            main_route_trackpoints,
            data_source,
            route_info,
        )

        # Generate HTML and inject route info
        map_html = map_obj._repr_html_()
        map_html = map_html.replace("<body>", f"<body>{route_info_html}")

        return map_html

    def validate_route_request(
        self, start_location: str, end_location: str
    ) -> Tuple[bool, str]:
        """Validate route request parameters"""
        if not start_location or not end_location:
            return False, "Please select both start and end locations."

        if start_location == end_location:
            return False, "Start and end locations cannot be the same."

        return True, ""

    def get_fallback_map_html(self, message: str) -> str:
        """Generate fallback HTML for error cases"""
        return f"<div style='text-align: center; padding: 50px; font-size: 18px; color: #666;'>{message}</div>"
