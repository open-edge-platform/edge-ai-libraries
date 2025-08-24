from pathlib import Path
from typing import Optional

from langgraph.graph import END, START, StateGraph

from agents import RoutePlannerState as State
from config import (
    ADVERSE_WEATHER_CONDITIONS,
    GPX_DIR,
    STATIC_ROUTE_OPTIMIZER_STACK,
    CongestionLevel,
    PlannerNode,
    StaticOptimizerName,
)
from controllers import (
    LiveTrafficController,
    StaticRouteOptimizerFactory,
    RouteStatusInterface,
    ThresholdController
)
from schema import RouteCondition
from utils.gpx_parser import MapDataParser
from utils.helper import get_all_available_route_files as route_files
from utils.logging_config import get_logger

logger = get_logger(__name__)


class RoutePlanner:
    """
    Route Planning Agent - Helps to find direct and optimal routes based on various data sources. Also updates route
    based on Real Time traffic.
    """

    def __init__(self):
        self.graph = StateGraph(State)
        self.all_routes: list[Path] = route_files()

        # Construct all required nodes and edges and compile the graph
        self.graph = self._build_graph()

    def _find_new_shortest_available_route(
        self, source: str, destination: str, no_fly_list: list[str]
    ) -> tuple[str, float]:
        """
        Finds the shortest available route between the source and destination waypoints,
        excluding any routes in the no-fly list i.e. already rejected routes.
        """

        shortest_distance: float = 0.0
        shortest_route: str = ""

        # Iterate over all available route files not present in no_fly_list
        for route_file in list(set(self.all_routes) - set(no_fly_list or [])):
            # Parse GPX file for current route
            temp_parser = MapDataParser(GPX_DIR / route_file)
            waypoints = temp_parser.get_waypoints()

            # Get source and destination waypoints
            source_wpt = waypoints[0] if waypoints else None
            destination_wpt = waypoints[-1] if waypoints else None

            # Check if waypoints match the source and destination in graph state
            if source_wpt and destination_wpt:
                if (
                    source_wpt["name"] == source
                    or source_wpt["description"] == source
                    and destination_wpt["name"] == destination
                    or destination_wpt["description"] == destination
                ):
                    # Get the route with shortest distance for given source and destination
                    route_distance = temp_parser.get_total_distance()
                    if route_distance < shortest_distance or shortest_distance == 0.0:
                        shortest_distance = route_distance
                        shortest_route = route_file

        return shortest_route, shortest_distance

    def find_direct_route(self, state: State) -> State:
        """Finds the direct route based on the available routes and provided source/destination."""

        logger.info("Finding direct shortest route ...")
        shortest_route, shortest_distance = self._find_new_shortest_available_route(
            state["source"], state["destination"], state.get("no_fly_list", [])
        )

        # Update the direct_route dict with required information
        direct_route_state = {
            "route_name": shortest_route,
            "distance": shortest_distance,
        }
        logger.debug(f"Direct Route: {direct_route_state}")

        return {
            "direct_route": direct_route_state,
            "optimal_route": direct_route_state,  # Initially, optimal route is same as direct route
            "static_optimizers": STATIC_ROUTE_OPTIMIZER_STACK,
            "no_fly_list": [shortest_route],
        }

    def find_optimal_route(self, state: State) -> State:
        """
        Finds the optimal route based on the available route status and information.
        #TODO Uses Brute Force Search - Need to be Improved.
        """
        logger.info("Finding optimal routes based on static data ...")
        route_status: RouteCondition | None = None

        if state.get("static_optimizers"):
            optimizer_name: StaticOptimizerName = state.get("static_optimizers").pop()
            route_optimizer: RouteStatusInterface = StaticRouteOptimizerFactory[
                optimizer_name
            ]
        else:
            logger.error(
                "Optimal route node invoked when no static optimizers are available!"
            )
            return state

        current_optimal_route = state.get("optimal_route", {})
        optimal_route_name = current_optimal_route.get("route_name")
        optimal_distance = current_optimal_route.get("distance")

        temp_parser = MapDataParser(GPX_DIR / optimal_route_name)
        route_data = temp_parser.get_route_data()

        for track in route_data["tracks"]:
            for track_point in track["track_points"]:
                route_status = route_optimizer(
                    track_point["lat"], track_point["lon"]
                ).fetch_route_status()
                if route_status:
                    # check if route_status has a required attributes and proceed accordingly
                    if hasattr(route_status, "weather_condition"):
                        if route_status.weather_condition in ADVERSE_WEATHER_CONDITIONS:
                            optimal_route_name, optimal_distance = (
                                self._find_new_shortest_available_route(
                                    state["source"],
                                    state["destination"],
                                    state.get("no_fly_list", []),
                                )
                            )
                            optimal_route_state = {
                                "route_name": optimal_route_name,
                                "distance": optimal_distance,
                                "weather_status": route_status.weather_condition,
                            }
                            break
                    elif hasattr(route_status, "congestion_level"):
                        if route_status.congestion_level in [
                            CongestionLevel.HIGH,
                            CongestionLevel.SEVERE,
                        ]:
                            optimal_route_name, optimal_distance = (
                                self._find_new_shortest_available_route(
                                    state["source"],
                                    state["destination"],
                                    state.get("no_fly_list", []),
                                )
                            )
                            optimal_route_state = {
                                "route_name": optimal_route_name,
                                "distance": optimal_distance,
                                "traffic_history": route_status.congestion_level,
                            }
                            if hasattr(route_status, "event_name"):
                                optimal_route_state["event_name"] = (
                                    route_status.event_name
                                )
                            break

        return {
            "optimal_route": optimal_route_state,
            "no_fly_list": [optimal_route_name],
        }

    def update_optimal_route_realtime(self, state: State) -> State:
        """Updates the optimal route in real-time based on live traffic data."""

        logger.info("Fetching real-time traffic updates and optimizing route accordingly...")

        # Get all routes from existing no_fly_list state except last. 
        # This is because, we may need to re-analyse the most latest optimal route.
        local_no_fly_list = state.get("no_fly_list", [])[:-1]

        # Default values for graph state to be returned if no traffic issues or new optimal routes are found
        optimal_route_state = state.get("optimal_route", {})
        live_traffic_state = {}

        # fetch the available live traffic data 
        live_traffic_controller = LiveTrafficController()
        route_status = live_traffic_controller.fetch_route_status()

        # Iterate till no new routes are available
        while True:
            route_not_optimal: bool = False
            logger.debug(f"Roads not to be taken : {local_no_fly_list}")

            # Get next available shortest route
            next_shortest_route_name, next_shortest_distance = self._find_new_shortest_available_route(
                state["source"], state["destination"], local_no_fly_list
            )

            if not next_shortest_route_name or not next_shortest_distance:
                logger.info("No more alternate routes available.")
                break

            # Parse the next available shortest route
            map_parser = MapDataParser(GPX_DIR / next_shortest_route_name)
            route_data = map_parser.get_route_data()

            # Get the first track and collect all trackpoints for the track
            trackpoints = route_data.get("tracks", [{}])[0].get("track_points", [])

            for i, trackpoint in enumerate(trackpoints):
                # If route has been found not to be optimal break out of loop
                if route_not_optimal:
                    break

                for traffic_status in route_status:
                    if (
                        abs(traffic_status.location_coordinates.latitude - trackpoint["lat"])
                        <= live_traffic_controller.proximity_factor
                        and abs(traffic_status.location_coordinates.longitude - trackpoint["lon"])
                        <= live_traffic_controller.proximity_factor
                    ):
                        if traffic_status.traffic_density > ThresholdController.TRAFFIC_DENSITY_THRESHOLD:
                            # If traffic is below threshold, stop looking for more trackpoints in current route
                            logger.info(f"High traffic density ({traffic_status.traffic_density}) in {next_shortest_route_name}. Finding next shortest route...")
                            route_not_optimal = True

                            # Update the live traffic data to provide details of traffic situation and intersection images
                            live_traffic_state = {
                                "route_name": next_shortest_route_name,
                                "intersection_name": traffic_status.intersection_name,
                                "timestamp": traffic_status.timestamp,
                                "location_coordinates": traffic_status.location_coordinates,
                                "traffic_density": traffic_status.traffic_density,
                                "traffic_description": traffic_status.traffic_description,
                                "intersection_images": traffic_status.intersection_images,
                            }

                            break

            if i == len(trackpoints) - 1 and not route_not_optimal:
                # If we reached the last trackpoint without finding high traffic, consider route to be optimal
                logger.info(f"Route {next_shortest_route_name} is optimal.")

                # Update the optimal_route_state for the graph state
                optimal_route_state = {
                    "route_name": next_shortest_route_name,
                    "distance": next_shortest_distance,
                }
                break
            else:
                logger.debug("Finding next shortest route")
                # Add current route to local no_fly_list and try next shortest route if any
                local_no_fly_list.append(next_shortest_route_name)

        return {
            "optimal_route": optimal_route_state,
            "live_traffic": live_traffic_state,
        }


    def _should_rerun_static_route_optimizers(self, state: State) -> bool:
        """Re-run static route optimizers until optimizer stack is empty"""
        return len(state["static_optimizers"]) > 0

    def _route_optimizers_selector(self, state: State) -> str:
        """
        Decide which optimizer node should be run first
        """
        # If direct route is not found, we need to find it first.
        if not state.get("direct_route"):
            return PlannerNode.DIRECT.value
        # if static optimizers are available, run static optimization node
        elif state.get("static_optimizers"):
            return PlannerNode.OPTIMAL.value
        # Otherwise run realtime route optimization node
        else:
            return PlannerNode.REALTIME.value

    def _build_graph(self) -> StateGraph:
        """Builds the state graph using different nodes and edges."""

        # Added all three tools as nodes in Graph
        self.graph.add_node(PlannerNode.DIRECT.value, self.find_direct_route)
        self.graph.add_node(PlannerNode.OPTIMAL.value, self.find_optimal_route)
        self.graph.add_node(
            PlannerNode.REALTIME.value, self.update_optimal_route_realtime
        )

        # Add conditional edges from START node to each of the three nodes, based on _route_optimizers_selector response.
        self.graph.add_conditional_edges(START, self._route_optimizers_selector)

        # Add final edges from all three nodes to END node
        self.graph.add_edge(PlannerNode.DIRECT.value, END)
        # Add conditional edge between optimal_route and END node, as we need to re-run this node until
        # the static route optimizer stack exhausts.
        self.graph.add_conditional_edges(
            PlannerNode.OPTIMAL.value,
            self._should_rerun_static_route_optimizers,
            {PlannerNode.OPTIMAL.value, END},
        )
        self.graph.add_edge(PlannerNode.REALTIME.value, END)

        # Compile the graph to be able to execute it
        return self.graph.compile()

    def plan_route(
        self, source: str, destination: str, previous_state: Optional[State] = None
    ) -> State:
        """
        Plans a route from the source to the destination using most optimal path.

        Args:
            source (str): The starting point of the route.
            destination (str): The endpoint of the route.
            previous_state (Optional[State]): Previous route state for continuing optimization

        Returns:
            State: The planned route as a state object.
        """

        logger.info(f"Planning route from {source} to {destination}")

        current_state = {"source": source, "destination": destination}

        if previous_state:
            current_state.update(previous_state)

        # Execute the graph to find the best route
        route_detail = self.graph.invoke(current_state)

        return route_detail
