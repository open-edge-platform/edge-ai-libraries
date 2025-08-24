from config import StaticOptimizerName as route_optimizer

from .planned_events import PlannedEventsController
from .traffic_trends import TrafficTrendsController
from .weather import WeatherReportController

"""
Map relevant keys to different Route Information Controllers
"""
StaticRouteOptimizerFactory = {
    route_optimizer.TRAFFIC: TrafficTrendsController,
    route_optimizer.WEATHER: WeatherReportController,
    route_optimizer.PLANNED_EVENTS: PlannedEventsController,
}
