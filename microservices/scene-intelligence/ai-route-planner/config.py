import os
from enum import Enum
from pathlib import Path

# Configs and Constants for the Route Planner Application

# Default locations and coordinates
DEFAULT_LOCATIONS = [
    "Berkeley, California",
    "Santa Clara, California",
]

# Coordinates mapping for locations with default values for lats and long
DEFAULT_LOCATION_COORDINATES = {
    "Berkeley, California": [37.8715, -122.2730],
    "Santa Clara, California": [37.3541, -121.9552],
}

# Directory where GPX files reside
GPX_DIR: Path = Path(__file__).parent / "data" / "routes"

# Directory where route status (Weather, traffic, etc. ) data is stored
ROUTE_STATUS_DIR: Path = Path(__file__).parent / "data" / "csv"

# Real-time traffic API endpoint
# Get the API BASE from env var or a default value is picked
SCENE_INTELLIGENCE_API_BASE = os.getenv("SI_API_BASE", "http://localhost:8082")
SCENE_INTELLIGENCE_ENDPOINTS = {
    "traffic_summary": "/api/v1/traffic/directional/summary",
    "update_threshold": "/api/v1/config/vlm/threshold"
}

class CongestionLevel(Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"
    SEVERE = "Severe"

class WeatherStatus(Enum):
    SUNNY = "Sunny"
    CLEAR = "Clear"
    CLOUDY = "Cloudy"
    FOG = "Foggy"
    RAINY = "Rainy"
    STORMY = "Stormy"
    SNOWY = "Snowy"

# Weather conditions that trigger alternate route search
ADVERSE_WEATHER_CONDITIONS = [
    WeatherStatus.FOG,
    WeatherStatus.RAINY,
    WeatherStatus.STORMY,
    WeatherStatus.SNOWY,
]

class StaticOptimizerName(Enum):
    """
    An Enum to id all static route optimizers
    """

    TRAFFIC = "traffic_trend"
    WEATHER = "weather_conditions"
    PLANNED_EVENTS = "planned_events"

    # add a method which returns a detailed description of the optimizer
    def get_description(self) -> str:
        descriptions = {
            StaticOptimizerName.TRAFFIC: "Historical Traffic Trends",
            StaticOptimizerName.WEATHER: "Weather Conditions",
            StaticOptimizerName.PLANNED_EVENTS: "Planned Events",
        }
        return descriptions.get(self, "No description available.")


STATIC_ROUTE_OPTIMIZER_STACK: list[StaticOptimizerName] = [
    StaticOptimizerName.PLANNED_EVENTS,
    StaticOptimizerName.WEATHER,
    StaticOptimizerName.TRAFFIC,
]


class PlannerNode(Enum):
    """
    An Enum to identify all planning nodes
    """

    DIRECT = "direct_route_planner"
    OPTIMAL = "optimal_route_planner"
    REALTIME = "realtime_route_planner"


# Map styling
MAP_COLORS = {
    "main_route": "#4285F4",
    "optimal_route": "#13B513",
    "start_marker": "#0AB438",
    "route_incident": "#FA1B07",
    "end_marker": "#FF9D00",
    "waypoint": "#A47C02",
    "non_optimal_route_direct": "#9C9B9B",
    "non_optimal_route": "#726565",
}

# UI constants
APP_DETAILS = """# Welcome to Agentic AI Route Planning

## Select your start and end locations, then click 'Find Route' to begin route planning.

### The AI agent will:
 1. Analyse the shortest route between source and destination and load it.
 2. Analyze planned events, historical traffic trends and weather conditions along the shortest route and load an alternate optimized route, if needed.
 3. Continously monitor the live traffic conditions on the optimized route and update the route as needed in real-time.
"""

INITIAL_MAP_HTML = "<div style='text-align: center; padding: 50px; font-size: 18px; color: #666;'>Select locations and click 'Find Route' to see the route map</div>"
