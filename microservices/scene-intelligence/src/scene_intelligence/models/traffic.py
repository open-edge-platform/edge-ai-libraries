"""Traffic data models."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TrafficMetrics(BaseModel):
    """Traffic metrics for a specific time period."""
    vehicle_count: int = Field(default=0, description="Total vehicle count")
    pedestrian_count: int = Field(default=0, description="Total pedestrian count")
    average_density: float = Field(default=0.0, description="Average traffic density")
    peak_density: float = Field(default=0.0, description="Peak traffic density")
    timestamp: datetime = Field(description="Timestamp of the metrics")


class DirectionData(BaseModel):
    """Traffic data for a specific direction."""
    direction: str = Field(description="Traffic direction (north, south, east, west)")
    vehicle_count: int = Field(default=0, description="Vehicle count for this direction")
    pedestrian_count: int = Field(default=0, description="Pedestrian count for this direction")
    density: float = Field(default=0.0, description="Traffic density for this direction")


class IntersectionData(BaseModel):
    """Traffic data for a specific intersection."""
    intersection_id: str = Field(description="Unique intersection identifier")
    name: str = Field(description="Human-readable intersection name")
    location: Dict[str, float] = Field(description="Intersection location coordinates")
    timestamp: datetime = Field(description="Data timestamp")
    total_vehicles: int = Field(default=0, description="Total vehicle count")
    total_pedestrians: int = Field(default=0, description="Total pedestrian count")
    average_density: float = Field(default=0.0, description="Average traffic density")
    directions: List[DirectionData] = Field(default_factory=list, description="Per-direction data")
    metrics_window_seconds: int = Field(description="Time window for these metrics")


class RouteData(BaseModel):
    """Traffic data for a route (collection of intersections)."""
    route_id: str = Field(description="Unique route identifier")
    name: str = Field(description="Human-readable route name")
    intersections: List[IntersectionData] = Field(description="Intersections on this route")
    total_vehicles: int = Field(default=0, description="Total vehicles across route")
    total_pedestrians: int = Field(default=0, description="Total pedestrians across route")
    average_density: float = Field(default=0.0, description="Average density across route")


class TrafficSummary(BaseModel):
    """Overall traffic summary across all intersections."""
    timestamp: datetime = Field(description="Summary timestamp")
    total_intersections: int = Field(description="Number of intersections monitored")
    total_vehicles: int = Field(default=0, description="Total vehicle count across all intersections")
    total_pedestrians: int = Field(default=0, description="Total pedestrian count across all intersections")
    average_density: float = Field(default=0.0, description="Average density across all intersections")
    intersections: List[IntersectionData] = Field(description="Individual intersection data")
    routes: List[RouteData] = Field(description="Route-based data")
    metrics_window_seconds: int = Field(description="Time window for these metrics")
    busiest_intersection: Optional[str] = Field(default=None, description="ID of intersection with highest traffic")
    quietest_intersection: Optional[str] = Field(default=None, description="ID of intersection with lowest traffic")


class MQTTMessage(BaseModel):
    """MQTT message structure from SceneScape."""
    topic: str = Field(description="MQTT topic")
    payload: Dict = Field(description="Message payload")
    timestamp: datetime = Field(description="Message timestamp")
    intersection_id: Optional[str] = Field(default=None, description="Extracted intersection ID")
    region_id: Optional[str] = Field(default=None, description="Extracted region ID")
    object_type: Optional[str] = Field(default=None, description="Object type (vehicle, pedestrian)")
