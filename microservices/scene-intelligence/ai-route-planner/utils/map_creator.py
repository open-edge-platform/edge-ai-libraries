import math
import random
from typing import Dict, List, Optional, Tuple

import folium

from config import MAP_COLORS
from utils.logging_config import get_logger

logger = get_logger(__name__)


class MapCreator:
    """Handles all map creation and rendering functionality"""

    def __init__(self):
        self.map_colors = MAP_COLORS

    def generate_realistic_route(
        self, start_coords: List[float], end_coords: List[float], num_waypoints: int = 8
    ) -> List[List[float]]:
        """Generate a realistic route with waypoints between start and end coordinates"""
        lat_start, lon_start = start_coords
        lat_end, lon_end = end_coords

        # Calculate the direct distance
        distance = math.sqrt((lat_end - lat_start) ** 2 + (lon_end - lon_start) ** 2)

        route_points = [start_coords]

        # Generate waypoints that create a more realistic path
        for i in range(1, num_waypoints):
            progress = i / num_waypoints

            # Base interpolation
            lat = lat_start + (lat_end - lat_start) * progress
            lon = lon_start + (lon_end - lon_start) * progress

            # Add some realistic deviation to simulate following roads
            deviation_factor = 0.3 * distance * math.sin(progress * math.pi)

            # Add perpendicular deviation
            perpendicular_lat = -(lon_end - lon_start) / distance if distance > 0 else 0
            perpendicular_lon = (lat_end - lat_start) / distance if distance > 0 else 0

            # Random variation to make it more realistic
            random_factor = (random.random() - 0.5) * 0.1 * distance

            lat += (
                perpendicular_lat * deviation_factor + perpendicular_lat * random_factor
            )
            lon += (
                perpendicular_lon * deviation_factor + perpendicular_lon * random_factor
            )

            route_points.append([lat, lon])

        route_points.append(end_coords)
        return route_points

    def calculate_map_center_and_zoom(
        self, route_points: List[List[float]]
    ) -> Tuple[float, float, int]:
        """Calculate optimal center coordinates and zoom level for the map"""
        if not route_points:
            return 37.8715, -122.2730, 8

        # Calculate bounds
        lats = [point[0] for point in route_points]
        lons = [point[1] for point in route_points]

        center_lat = (min(lats) + max(lats)) / 2
        center_lon = (min(lons) + max(lons)) / 2

        lat_diff = max(lats) - min(lats)
        lon_diff = max(lons) - min(lons)
        max_diff = max(lat_diff, lon_diff)

        # Determine zoom level
        if max_diff > 20:
            zoom = 7
        elif max_diff > 10:
            zoom = 8
        elif max_diff > 5:
            zoom = 9
        else:
            zoom = 10

        return center_lat, center_lon, zoom

    def add_route_line(
        self,
        map_obj: folium.Map,
        route_points: List[List[float]],
        color: str,
        label: str,
        is_dashed: bool = False,
    ) -> None:
        """Add a route line to the map with proper styling"""
        # Add white border for better visibility
        folium.PolyLine(
            locations=route_points,
            color="white",
            weight=8,
            opacity=0.6,
            smooth_factor=1.0,
        ).add_to(map_obj)

        # Add the main route line
        line_options = {
            "locations": route_points,
            "color": color,
            "weight": 6,
            "opacity": 0.9,
            "smooth_factor": 1.0,
            "popup": label,
        }

        if is_dashed:
            line_options["dash_array"] = "10,5"

        folium.PolyLine(**line_options).add_to(map_obj)

    def add_incident_marker(self, map_obj: folium.Map, latitude: float, longitude: float) -> None:
        """Add a marker for route incidents"""

        # A dict mapping lats and longs to intersection name
        intersection_names: dict[tuple, str] = {
            (37.55336,  -122.29627): "Intersection 1",
            (37.82837, -122.29489): "Intersection 2",
            (37.69076, -122.09948): "Intersection 3",
            (37.70127, -121.92295): "Intersection 4"
        }

        # get current intersection name
        # current_intersection = intersection_names.get((latitude, longitude), "Unknown Intersection")

        incident_icon_html = f"""
        <div style="
            background-color: {self.map_colors["route_incident"]};
            border: 3px solid white;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        ">
            <div style="
                background-color: white;
                border-radius: 50%;
                width: 8px;
                height: 8px;
            "></div>
        </div>
        """
        no_incident_icon_html = f"""
        <div style="
            background-color: {self.map_colors["no_incident"]};
            border: 3px solid white;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        ">
            <div style="
                background-color: white;
                border-radius: 50%;
                width: 8px;
                height: 8px;
            "></div>
        </div>
        """
        for coordinates, intersection_name in intersection_names.items():
            
            current_latitude, current_longitude = coordinates

            if latitude == current_latitude and longitude == current_longitude:
                folium.Marker(
                    location=[latitude, longitude],
                    popup=folium.Popup(
                        f"<b>{intersection_name}</b><br>Traffic incident affecting the route",
                        max_width=200,
                    ),
                    icon=folium.DivIcon(
                        html=incident_icon_html, icon_size=(20, 20), icon_anchor=(10, 10)
                    ),
                ).add_to(map_obj)
            else:
                folium.Marker(
                    location=[current_latitude, current_longitude],
                    popup=folium.Popup(
                        f"<b>{intersection_name}</b><br>Traffic incident affecting the route",
                        max_width=200,
                    ),
                    icon=folium.DivIcon(
                        html=no_incident_icon_html, icon_size=(20, 20), icon_anchor=(10, 10)
                    ),
                ).add_to(map_obj)


    def add_location_markers(
        self,
        map_obj: folium.Map,
        start_location: str,
        end_location: str,
        start_coords: List[float],
        end_coords: List[float],
    ) -> None:
        """Add start and end location markers"""
        # Start marker (Green)
        start_icon_html = f"""
        <div style="
            background-color: {self.map_colors["start_marker"]};
            border: 3px solid white;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        ">
            <div style="
                background-color: white;
                border-radius: 50%;
                width: 8px;
                height: 8px;
            "></div>
        </div>
        """

        # End marker (Red)
        end_icon_html = f"""
        <div style="
            background-color: {self.map_colors["end_marker"]};
            border: 3px solid white;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        ">
            <div style="
                background-color: white;
                border-radius: 50%;
                width: 8px;
                height: 8px;
            "></div>
        </div>
        """

        # Add markers
        folium.Marker(
            location=start_coords,
            popup=folium.Popup(
                f"<b>START: {start_location}</b><br>Starting point of your journey",
                max_width=200,
            ),
            icon=folium.DivIcon(
                html=start_icon_html, icon_size=(20, 20), icon_anchor=(10, 10)
            ),
        ).add_to(map_obj)

        folium.Marker(
            location=end_coords,
            popup=folium.Popup(
                f"<b>DESTINATION: {end_location}</b><br>Your destination", max_width=200
            ),
            icon=folium.DivIcon(
                html=end_icon_html, icon_size=(20, 20), icon_anchor=(10, 10)
            ),
        ).add_to(map_obj)

    def add_waypoint_markers(
        self,
        map_obj: folium.Map,
        route_points: List[List[float]],
        max_waypoints: int = 5,
    ) -> None:
        """Add intermediate waypoint markers"""
        if len(route_points) <= 2:
            return

        # Calculate waypoint intervals
        num_intermediate = min(max_waypoints, len(route_points) // 20)
        if num_intermediate <= 0:
            return

        interval = len(route_points) // (num_intermediate + 1)

        for i in range(1, num_intermediate + 1):
            idx = i * interval
            if idx < len(route_points):
                waypoint_html = f"""
                <div style="
                    background-color: {self.map_colors["waypoint"]};
                    border: 2px solid white;
                    border-radius: 50%;
                    width: 12px;
                    height: 12px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
                "></div>
                """
                folium.Marker(
                    location=route_points[idx],
                    popup=folium.Popup(
                        f"<b>Waypoint {i}</b><br>Route checkpoint", max_width=200
                    ),
                    icon=folium.DivIcon(
                        html=waypoint_html, icon_size=(12, 12), icon_anchor=(6, 6)
                    ),
                ).add_to(map_obj)

    def create_route_info_box(
        self,
        start_location: str,
        end_location: str,
        route_points: List[List[float]],
        data_source: str,
        alt_route_info: Optional[Dict] = None,
    ) -> str:
        """Create HTML for route information box"""
        # Calculate distance and time
        distance_km = self.calculate_route_distance(route_points)
        estimated_time = max(1, int(distance_km / 80))  # Assuming 80 km/h average speed

        route_info_html = f"""
        <div style="
            position: fixed;
            top: 10px;
            left: 10px;
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.15);
            font-family: Arial, sans-serif;
            font-size: 14px;
            z-index: 1000;
            max-width: 300px;
        ">
            <div style="font-weight: bold; color: #1a73e8; margin-bottom: 8px;">
                Route Information
            </div>
            <div style="font-size: 12px; color: #666; margin-bottom: 8px;">
                {data_source}
            </div>
            <div style="margin-bottom: 5px;">
                <span style="color: {self.map_colors["start_marker"]};">●</span> From: <strong>{start_location}</strong>
            </div>
            <div style="margin-bottom: 10px;">
                <span style="color: {self.map_colors["end_marker"]};">●</span> To: <strong>{end_location}</strong>
            </div>
            <div style="border-top: 1px solid #e0e0e0; padding-top: 8px;">
                <div>Distance: ~{distance_km:.1f} km</div>
                <div>Est. Time: ~{estimated_time} hours</div>
                <div style="font-size: 12px; color: #666; margin-top: 5px;">
                    Main route points: {len(route_points)}
                </div>
        """

        # Add alternative route information if available
        if alt_route_info and alt_route_info.get("points", 0) > 0:
            route_info_html += f"""
                <div style="border-top: 1px solid #e0e0e0; padding-top: 8px; margin-top: 8px;">
                    <div style="font-weight: bold; color: {alt_route_info["color"]};">
                        {alt_route_info["label"]}
                    </div>
                    <div style="font-size: 12px; color: #666;">
                        Alt route points: {alt_route_info["points"]}
                    </div>
                </div>
            """

        route_info_html += """
            </div>
        </div>
        """

        return route_info_html

    def calculate_route_distance(self, route_points: List[List[float]]) -> float:
        """Calculate total distance along the route"""
        if len(route_points) <= 1:
            return 0.0

        total_distance = 0
        for i in range(len(route_points) - 1):
            lat1, lon1 = route_points[i]
            lat2, lon2 = route_points[i + 1]
            # Simple distance calculation (Haversine would be more accurate)
            dist = (
                math.sqrt((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2) * 111
            )  # Rough km conversion
            total_distance += dist

        return total_distance

    def create_base_map(
        self, center_lat: float, center_lon: float, zoom: int
    ) -> folium.Map:
        """Create a base map with tile layers"""
        # Create base map
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom,
            tiles="OpenStreetMap",
            prefer_canvas=True,
        )

        # Add additional tile layers
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            name="Satellite",
            overlay=False,
            control=True,
        ).add_to(m)

        folium.TileLayer(
            tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            attr="OpenStreetMap",
            name="Streets",
            overlay=False,
            control=True,
        ).add_to(m)

        # Add layer control
        folium.LayerControl().add_to(m)

        return m
