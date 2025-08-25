import base64
import queue
import threading
import time
from typing import Optional
from io import BytesIO

import gradio as gr
from PIL import Image

from config import APP_DETAILS, INITIAL_MAP_HTML
from controllers.threshold_controller import ThresholdController
from services.route_service import RouteService
from utils.logging_config import setup_logging

logger = setup_logging()
route_service = RouteService()

current_route_info = None
optimization_active = False
optimization_thread = None
UI_UPDATE_INTERVAL = 6  # Poll interval for new updates from data_queue used by thread
OPTIMIZATION_INTERVAL = 8  # Seconds between agent invocations

# Queue for passing data between agent thread and UI
data_queue = queue.Queue()

# Lock for thread-safe access to shared variables
thread_lock = threading.Lock()

def get_direct_route(source: str, destination: str) -> tuple[str, str, str]:
    """
    Uses RouteService to trigger RoutePlanner agent and gets direct route between source and destination.
    """

    # Validate input
    is_valid, error_message = route_service.validate_route_request(source, destination)
    if not is_valid:
        return error_message, route_service.get_fallback_map_html(
            "Select locations to see the route map"
        )

    # Start planning the route
    next_data_source, distance, main_route_map = route_service.create_direct_route_map(
        source, destination
    )

    thinking_message = (
        f"## Route Planning Started\n\n #### Route: {source} -> {destination}\n\n ### Direct route "
        + f"loaded by analysing shortest route between {source} and {destination}."
        + f" \n\n ##### Total Distance : {distance:.2f} Kms \n\n"
    )

    # Set message to show Real-time Agent actions
    agent_status_msg = f"Active - Analysing {next_data_source} ..."

    return agent_status_msg, thinking_message, main_route_map


def get_optimal_route(source: str, destination: str) -> tuple[str, str, str, Optional[dict[str, str]]]:
    """
    Uses RouteService to trigger RoutePlanner agent and gets optimized route.
    """

    # Validate input
    is_valid, error_message = route_service.validate_route_request(source, destination)
    if not is_valid:
        return (
            error_message,
            route_service.get_fallback_map_html("Select locations to see the route map"),
            None,
        )

    # Start planning the route
    next_data_source, route_issue, distance, optimized_route_map, intersection_images = (
        route_service.create_alternate_route_map(source, destination)
    )
    if route_issue:
        thinking_message = (
            f"\n #### Route: {source} -> {destination}\n\n ### Route Updated due to "
            + f"{route_issue} \n\n ##### Total Distance for Updated Route : {distance:.2f} Kms\n\n"
        )
    else:
        thinking_message = (
            f" #### Route: {source} -> {destination}\n\n ### No traffic or weather issues found on "
            + f"current route. \n\n ##### Total Distance : {distance:.2f} Kms \n\n"
        )

    # Set message to show Real-time Agent actions
    agent_status_msg = f"Active - Analysing {next_data_source} ..."

    return agent_status_msg, thinking_message, optimized_route_map, intersection_images


def planner_agent_thread(source: str, destination: str):
    """
    Background thread that continuously invokes the agent and updates the queue with results.
    This function runs in a separate thread and doesn't block the Gradio UI.
    """
    global optimization_active
    logger.info(f"Triggering Route Planner Agent for route {source} to {destination}")

    iteration_count = 1
    try:
        while optimization_active:
            logger.info(
                f"Running agent iteration {iteration_count} for route {source} to {destination}"
            )

            time.sleep(OPTIMIZATION_INTERVAL)

            if iteration_count == 1:
                # Start by getting direct shortest route. Shortest direct route needs to found only once.
                agent_status_msg, thinking_output, map_output = get_direct_route(
                    source, destination
                )
                intersection_images = None
            else:
                # Get optimal route information from the agent
                agent_status_msg, thinking_output, map_output, intersection_images = get_optimal_route(
                    source, destination
                )

            # Put the results in the queue to be picked up by the UI
            data_queue.put(
                {
                    "iteration": iteration_count,
                    "timestamp": time.time(),
                    "agent_status": agent_status_msg,
                    "thinking_output": thinking_output,
                    "map_output": map_output,
                    "intersection_images": intersection_images,
                }
            )

            iteration_count += 1

    except Exception as e:
        logger.error(f"Error in Route Planning Agent thread: {e}")
        data_queue.put(
            {"error": f"Route Planning error: {str(e)}", "timestamp": time.time()}
        )
    finally:
        logger.info(
            f"Route Planning Agent thread for route {source} to {destination} has stopped"
        )
        optimization_active = False


def start_agent(source: str, destination: str) -> tuple[gr.Button, gr.Button]:
    """
    This function launches a background thread that triggers an Agent which continuously
    checks for route conditions, starting with finding the shortest direct route.

    The background thread will periodically update the UI via the data_queue.
    """
    global optimization_active, optimization_thread

    with thread_lock:
        # Stop existing thread if running
        if (
            optimization_active
            and optimization_thread
            and optimization_thread.is_alive()
        ):
            optimization_active = False
            optimization_thread.join(timeout=2.0)  # Give it 2 seconds to stop

        # Clear the queue before starting the thread
        while not data_queue.empty():
            try:
                data_queue.get_nowait()
            except queue.Empty:
                break

        optimization_active = True
        optimization_thread = threading.Thread(
            target=planner_agent_thread, args=(source, destination), daemon=True
        )
        optimization_thread.start()

    return gr.Button(interactive=not optimization_active), gr.Button(interactive=optimization_active)


def stop_agent() -> tuple[gr.Button, gr.Button]:
    """
    Stops the agent runner thread if it's running.
    Returns status message.
    """
    global optimization_active, optimization_thread

    with thread_lock:
        if (
            optimization_active
            and optimization_thread
            and optimization_thread.is_alive()
        ):
            optimization_active = False
            optimization_thread.join(timeout=2.0)
            logger.info("Route Planning Stopped!")
            return gr.Button(interactive=optimization_active), gr.Button(interactive=not optimization_active)
        else:
            logger.info("No Route Planning Agents Running.")
            return gr.Button(), gr.Button()

    

def check_for_updates(*args):
    """
    Checks the queue for updates from the agent thread.
    This function is called periodically by Gradio Timer to check for updates.
    Returns updated thinking output and map output if available.
    """
    try:
        no_update_tuple = (gr.update(), *[gr.update() for _ in range(6)])
        logger.info("Checking for updates...")
        if optimization_active:
            update = data_queue.get_nowait()

            if "error" in update:
                logger.error(update["error"])
                return no_update_tuple

            agent_status = update.get("agent_status")
            thinking = update.get("thinking_output")
            map_html = update.get("map_output")
            intersection_images = update.get("intersection_images")
            timestamp = time.strftime("%H:%M:%S", time.localtime(update["timestamp"]))

            thinking_with_iteration = (
                f"## [Update #{update['iteration']} at {timestamp}]\n\n"
                f"{thinking}\n\n"
                f"## The agent will continue analyzing this route ..."
            )

            # Update the intersection images if available
            image_updates = []
            if intersection_images and isinstance(intersection_images, dict) and len(intersection_images) > 0:
                for view_name, image_data in list(intersection_images.items())[:4]:
                    if image_data and isinstance(image_data, str):
                        # Read base64 encoded image as bytes and then as a PIL Image
                        image_bytes = BytesIO(base64.b64decode(image_data))
                        image = Image.open(image_bytes)

                        image_updates.append(gr.update(
                            visible=True,
                            value=image,
                            label=f"Camera View: {view_name}",
                            type="pil"
                        ))
                    else:
                        image_updates.append(gr.update(visible=False))

                # If we didn't receive some of the images (less than 4), hide the remaining image components
                for i in range(len(intersection_images), 4):
                    image_updates.append(gr.update(visible=False))
            else:
                # Make all for components invisible if no image available
                image_updates = [gr.update(visible=False) for _ in range(4)]

            return (
                gr.update(value=agent_status),
                gr.update(value=thinking_with_iteration),
                gr.update(value=map_html),
                *image_updates,
            )
        
    except queue.Empty:
        logger.info("Empty Data Queue : No Updates available.")
        return no_update_tuple
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        return no_update_tuple

    return no_update_tuple


def update_traffic_threshold(threshold_value: int):
    """
    Update the traffic density threshold value both locally and in the API.
    
    Args:
        threshold_value (int): The new threshold value (1-15)
    
    Returns:
        str: A message indicating the result of the update
    """
    try:
        # Post the update the threshold to Scene Intellifence API
        threshold_controller = ThresholdController()
        response = threshold_controller.update_threshold(threshold_value)
        
        if response.get("status", "") == "success":
            return f"Traffic threshold updated to {threshold_value}."
        else:
            logger.error(f"API threshold update failed: {response.get('error', 'Unknown error')}")
            return f"Local threshold updated to {threshold_value}, but API update failed"
    
    except Exception as e:
        logger.error(f"Error updating traffic threshold: {e}")
        return f"Error updating threshold: {str(e)}"


def create_gradio_interface() -> gr.Blocks:
    """Create and configure the Gradio interface"""

    # Get default locations
    default_locations = route_service.get_default_locations()

    css = """
    /* Modern Font Import */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Global Font Styles */
    body, .gradio-container, .gradio-container *, .gradio-container label, .gradio-container input, .gradio-container textarea, .gradio-container select, .gradio-container button {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif !important;
    }
    
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Inter', sans-serif !important;
        font-weight: 600;
    }
    
    .map-container {
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        position: relative;
    }
    .map-container iframe {
        border-radius: 12px;
        box-shadow: 0 4px 8px rgba(192, 38, 38, 0.3);
    }

    .search-button {
        background: linear-gradient(135deg, #13B513 0%, #069106 100%);
    }

    .search-button:hover {
        background: linear-gradient(135deg, #13B513 0%, #069106 50%);
        transform: translateY(-2px);
    }
    .stop-button {
        background-color: #C02626;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: bold;
        margin-top: 10px;
        transition: all 0.2s ease;
        box-shadow: 0 2px 6px rgba(192, 38, 38, 0.25);
        letter-spacing: 0.5px;
    }
    .stop-button:hover {
        background-color: #d9342a;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(192, 38, 38, 0.3);
    }
    .main-content-row {
        min-height: 50vh;
        display: flex;
        flex-direction: row;
    }
    .horizontal-search {
        background: linear-gradient(135deg, #8a85e9 0%, #4a43ce 100%);
        padding: 24px;
        border-radius: 16px;
        margin-bottom: 24px;
        box-shadow: 0 8px 16px rgba(79, 70, 229, 0.15);
    }
    .horizontal-search .gr-dropdown {
        background: white;
        border-radius: 10px;
        border: none;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    }
    .progress-container {
        z-index: 10 !important;
    }
    .traffic-slider {
        width: 100%;
    }
    .threshold-status {
        display: flex;
        width: 100%;
        overflow: hidden;
        word-wrap: break-word;
    }
    .settings-panel {
        display: flex;
        background-color: #E3F2F0;
        padding: 15px;
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        overflow: visible;
    }
    .settings-panel .block {
        width: 100%;
    }
    
    /* Styling for the thinking output markdown component */
    .thinking-output {
        border-radius: 10px;
        border: solid 1px #EBE6E6;
        padding: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        overflow-y: auto;
        max-height: 50vh;
        line-height: 1.6;
    }
    
    .thinking-output h1, .thinking-output h2, .thinking-output h3 {
        color: #b112cd;
        margin-top: 1em;
        margin-bottom: 0.5em;
    }
    .thinking-output h2 {
        color: #9230a4
    }

    .thinking-output h3 {
        color: #1073be;
    }

    .thinking-output h4 {
        color: #950d85
    }
    
    .thinking-output h5, .thinking-output h6 {
        color: #b942ab;
    }

    .thinking-output code {
        background-color: #f3f4f6;
        padding: 2px 5px;
        border-radius: 4px;
        font-family: 'Roboto Mono', monospace;
        font-size: 0.9em;
    }
    
    .thinking-output pre {
        background-color: #f8fafc;
        padding: 12px;
        border-radius: 8px;
        border-left: 3px solid #4f46e5;
        overflow-x: auto;
    }
    
    .thinking-output em, .thinking-output i {
        color: #8d3419;
    }
    
    .thinking-output strong, .thinking-output b {
        color: #262E9E;
    }
    
    .status-indicator {
        padding: 10px 16px;
        border-radius: 4px;
        font-weight: bold;
        text-align: center;
        letter-spacing: 0.3px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.2s ease;
        font-size: 18px;
    }
    .status-active {
        background-color: #8ccf9b;
        color: #155724;
        border: 1px solid #4b8257;
    }
    .status-inactive {
        background-color: #e7bcbf;
        color: #721c24;
        border: 1px solid #986b6e;
        font-weight: bold;
        font-size: 18px;
    }
    """

    with gr.Blocks(
        title="Dynamic Route Updates with Agentic AI", theme=gr.themes.Soft(), css=css
    ) as app:
        gr.Markdown("# Route Planner - Agentic AI based Commuter Support System")
        gr.Markdown(
            "Get an optimal route using our Agentic AI system with **real GPX route data** that considers weather, live traffic, road events and environmental factors."
        )

        gr.Markdown("### Quick Route Search")
        with gr.Row(elem_classes=["horizontal-search"]):
            with gr.Column(scale=3):
                start_dropdown = gr.Dropdown(
                    choices=default_locations,
                    label="From",
                    value=default_locations[0],
                    container=True,
                )
            with gr.Column(scale=3):
                end_dropdown = gr.Dropdown(
                    choices=default_locations,
                    label="To",
                    value=default_locations[-1],
                    container=True,
                )
            with gr.Column(scale=1):
                search_btn = gr.Button("Find Route", variant="primary", size="lg", elem_classes=["search-button"], interactive=True)

        with gr.Row(elem_classes=["settings-panel"]):
            with gr.Column(scale=3):
                traffic_threshold = gr.Slider(
                    minimum=1,
                    maximum=15,
                    value=ThresholdController.TRAFFIC_DENSITY_THRESHOLD,
                    step=1,
                    label="Traffic Density Threshold",
                    info="Adjust threshold for rerouting (1-15)",
                    elem_classes=["traffic-slider"],
                    container=True
                )
                threshold_status = gr.Textbox(
                    label="Threshold Status",
                    visible=True,
                    interactive=False,
                    elem_classes=["threshold-status"],
                    container=True
                )

            with gr.Column(scale=2):
                agent_status = gr.Textbox(
                    label="AI Agent Planning Status",
                    value="Inactive",
                    elem_classes=["status-indicator", "status-inactive"],
                    interactive=False,
                )
                stop_agent_btn = gr.Button(
                    "Stop Route Planning", 
                    variant="stop", 
                    elem_classes=["stop-button"],
                    interactive=False
                )

        # AI Thinking Output and Route Map side by side
        with gr.Row(elem_classes=["main-content-row"]):
            with gr.Column(scale=1):
                thinking_output = gr.Markdown(
                    label="AI Agent Thinking Process",
                    value=APP_DETAILS,
                    elem_classes=["thinking-output"]
                )
                
                # Create a group for intersection images
                with gr.Group(visible=True):
                    with gr.Row():
                        intersection_image1 = gr.Image(
                            label="Camera View 1",
                            visible=False,
                            elem_id="intersection-image-1",
                            type="pil",  # Important for base64 images
                            format="jpeg"
                        )
                        intersection_image2 = gr.Image(
                            label="Camera View 2",
                            visible=False,
                            elem_id="intersection-image-2",
                            type="pil",
                            format="jpeg"
                        )
                    with gr.Row():
                        intersection_image3 = gr.Image(
                            label="Camera View 3",
                            visible=False,
                            elem_id="intersection-image-3",
                            type="pil",
                            format="jpeg"
                        )
                        intersection_image4 = gr.Image(
                            label="Camera View 4",
                            visible=False,
                            elem_id="intersection-image-4",
                            type="pil",
                            format="jpeg"
                        )
                
            with gr.Column(scale=2):
                with gr.Column():
                    map_output = gr.HTML(
                        label="Route Map",
                        value=INITIAL_MAP_HTML,
                        elem_id="route-map",
                        elem_classes=["map-container"],
                    )

        intersection_images = [intersection_image1, intersection_image2, intersection_image3, intersection_image4]

        traffic_threshold.change(
            fn=update_traffic_threshold,
            inputs=[traffic_threshold],
            outputs=[threshold_status],
        )

        # Connect the search button with initial route display and start the Route Planner agent
        search_btn.click(
            fn=start_agent,
            inputs=[start_dropdown, end_dropdown],
            outputs=[search_btn, stop_agent_btn],
        ).then(
            fn=lambda: "Active - Analysing fastest route ...",
            inputs=None,
            outputs=agent_status,
        ).then(
            fn=lambda: gr.update(elem_classes=["status-indicator", "status-active"]),
            inputs=None,
            outputs=agent_status,
        )

        stop_agent_btn.click(
            fn=stop_agent,
            inputs=None,
            outputs=[stop_agent_btn, search_btn]
        ).then(
            fn=lambda: ("Inactive", "Agent Stopped!", *[gr.update(visible=False) for _ in range(4)]),
            inputs=None,
            outputs=[agent_status, thinking_output, *intersection_images],
        ).then(
            fn=lambda: gr.update(elem_classes=["status-indicator", "status-inactive"]),
            inputs=None,
            outputs=agent_status,
        )

        app.load(
            fn=lambda: (APP_DETAILS, INITIAL_MAP_HTML, *[gr.update(visible=False) for _ in range(4)]),
            inputs=None,
            outputs=[thinking_output, map_output, *intersection_images],
        )

        # Run a function to check queue updates at regular interval and update the UI comps.
        gr.Timer(UI_UPDATE_INTERVAL).tick(
            fn=check_for_updates,
            inputs=None,
            outputs=[agent_status, thinking_output, map_output, *intersection_images],
        )

    return app


if __name__ == "__main__":
    server_config = {
        "server_name": "0.0.0.0",
        "server_port": 7864,
        "share": False,
        "pwa": True,  # Enable Progressive Web App features
    }
    app = create_gradio_interface()
    logger.info("Starting Route Planner application...")
    app.launch(**server_config)
