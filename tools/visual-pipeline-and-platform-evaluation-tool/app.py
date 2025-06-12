import logging
import os
from datetime import datetime

import gradio as gr
import pandas as pd
import plotly.graph_objects as go
import requests

import utils
from benchmark import Benchmark
from device import DeviceDiscovery
from explore import GstInspector
from optimize import OptimizationResult, PipelineOptimizer
from pipeline import PipelineLoader
from utils import prepare_video_and_constants

logging.getLogger("httpx").setLevel(logging.WARNING)

with open(os.path.join(os.path.dirname(__file__), "app.css")) as f:
    css_code = f.read()

theme = gr.themes.Default(
    primary_hue="blue",
    font=[gr.themes.GoogleFont("Montserrat"), "ui-sans-serif", "sans-serif"],
)

# Initialize the pipeline based on the PIPELINE environment variable
current_pipeline = PipelineLoader.load(os.environ.get("PIPELINE", "").lower())[0]
device_discovery = DeviceDiscovery()
gst_inspector = GstInspector()


# Download File
def download_file(url, local_filename):
    # Send a GET request to the URL
    with requests.get(url, stream=True) as response:
        response.raise_for_status()  # Check if the request was successful
        # Open a local file with write-binary mode
        with open(local_filename, "wb") as file:
            # Iterate over the response content in chunks
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)  # Write each chunk to the local file


# Function to check if a click is inside any bounding box
def detect_click(evt: gr.SelectData):
    x, y = evt.index

    for (
        x_min,
        y_min,
        x_max,
        y_max,
        label,
        description,
    ) in current_pipeline.bounding_boxes():
        if x_min <= x <= x_max and y_min <= y <= y_max:

            match label:
                case "Inference":
                    return gr.update(open=True)

    return gr.update(open=False)


chart_titles = [
    "Pipeline Throughput [FPS]",
    "CPU Frequency [KHz]",
    "CPU Utilization [%]",
    "CPU Temperature [C°]",
    "Memory Utilization [%]",
    "GPU Package Power Usage [W]",
    "GPU Power Usage [W]",
    "GPU Frequency [MHz]",
    "GPU Render Engine Utilization [%]",
    "GPU Video Enhance Engine Utilization [%]",
    "GPU Video Engine Utilization [%]",
    "GPU Copy Engine Utilization [%]",
    "GPU Compute Engine Utilization [%]",
]

y_labels = [
    "Throughput",
    "Frequency",
    "Utilization",
    "Temperature",
    "Utilization",
    "Power",
    "Power",
    "Frequency",
    "Utilization",
    "Utilization",
    "Utilization",
    "Utilization",
    "Utilization",
]

# Create a dataframe for each chart
stream_dfs = [pd.DataFrame(columns=["x", "y"]) for _ in range(len(chart_titles))]


def read_latest_metrics(target_ns: int = None):
    try:
        with open("/home/dlstreamer/vippet/.collector-signals/metrics.txt", "r") as f:
            lines = [line.strip() for line in f.readlines()[-500:]]

    except FileNotFoundError:
        return [None] * 11

    if target_ns is not None:
        # Filter only lines near the target timestamp
        surrounding_lines = [
            line
            for line in lines
            if line.split()
            and line.split()[-1].isdigit()
            and abs(int(line.split()[-1]) - target_ns) < 1e9
        ]
        lines = surrounding_lines if surrounding_lines else []

    cpu_user = mem_used_percent = gpu_package_power = core_temp = gpu_power = None
    gpu_freq = cpu_freq = gpu_render = gpu_ve = gpu_video = gpu_copy = gpu_compute = (
        None
    )

    for line in reversed(lines):
        if cpu_user is None and "cpu" in line:
            parts = line.split()
            if len(parts) > 1:
                for field in parts[1].split(","):
                    if field.startswith("usage_user="):
                        try:
                            cpu_user = float(field.split("=")[1])
                        except:
                            pass

        if mem_used_percent is None and "mem" in line:
            parts = line.split()
            if len(parts) > 1:
                for field in parts[1].split(","):
                    if field.startswith("used_percent="):
                        try:
                            mem_used_percent = float(field.split("=")[1])
                        except:
                            pass

        if gpu_package_power is None and "pkg_cur_power" in line:
            parts = line.split()
            try:
                gpu_package_power = float(parts[1].split("=")[1])
            except:
                pass

        if gpu_power is None and "gpu_cur_power" in line:
            parts = line.split()
            try:
                gpu_power = float(parts[1].split("=")[1])
            except:
                pass

        if core_temp is None and "temp" in line:
            parts = line.split()
            if len(parts) > 1:
                for field in parts[1].split(","):
                    if "temp" in field:
                        try:
                            core_temp = float(field.split("=")[1])
                        except:
                            pass

        if gpu_freq is None and "gpu_frequency" in line:
            for part in line.split():
                if part.startswith("value="):
                    try:
                        gpu_freq = float(part.split("=")[1])
                    except:
                        pass

        if cpu_freq is None and "cpu_frequency_avg" in line:
            try:
                parts = [part for part in line.split() if "frequency=" in part]
                if parts:
                    cpu_freq = float(parts[0].split("=")[1])
            except:
                pass

        if gpu_render is None and "engine=render" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_render = float(part.split("=")[1])
                    except:
                        pass

        if gpu_copy is None and "engine=copy" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_copy = float(part.split("=")[1])
                    except:
                        pass

        if gpu_ve is None and "engine=video-enhance" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_ve = float(part.split("=")[1])
                    except:
                        pass

        if gpu_video is None and "engine=video" in line and "video-enhance" not in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_video = float(part.split("=")[1])
                    except:
                        pass

        if gpu_compute is None and "engine=compute" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_compute = float(part.split("=")[1])
                    except:
                        pass

        if all(
            v is not None
            for v in [
                cpu_user,
                mem_used_percent,
                gpu_package_power,
                core_temp,
                gpu_power,
                gpu_freq,
                gpu_render,
                gpu_ve,
                gpu_video,
                gpu_copy,
                cpu_freq,
                gpu_compute,
            ]
        ):
            break

    return [
        cpu_user,
        mem_used_percent,
        gpu_package_power,
        core_temp,
        gpu_power,
        gpu_freq,
        gpu_render,
        gpu_ve,
        gpu_video,
        gpu_copy,
        cpu_freq,
        gpu_compute,
    ]


def create_empty_fig(title, y_axis_label):
    fig = go.Figure()
    fig.update_layout(title=title, xaxis_title="Time", yaxis_title=y_axis_label)
    return fig


# Store figures globally
figs = [
    create_empty_fig(chart_titles[i], y_labels[i]) for i in range(len(chart_titles))
]


def generate_stream_data(i, timestamp_ns=None):
    new_x = (
        datetime.now()
        if timestamp_ns is None
        else datetime.fromtimestamp(timestamp_ns / 1e9)
    )

    new_y = 0
    (
        cpu_val,
        mem_val,
        gpu_package_power,
        core_temp,
        gpu_power,
        gpu_freq,
        gpu_render,
        gpu_ve,
        gpu_video,
        gpu_copy,
        cpu_freq,
        gpu_compute,
    ) = read_latest_metrics(timestamp_ns)

    try:
        with open("/home/dlstreamer/vippet/.collector-signals/fps.txt", "r") as f:
            lines = [line.strip() for line in f.readlines()[-500:]]
            latest_fps = float(lines[-1])

    except FileNotFoundError:
        latest_fps = 0

    except IndexError:
        latest_fps = 0

    title = chart_titles[i]

    if title == "Pipeline Throughput [FPS]":
        new_y = latest_fps
    elif title == "CPU Frequency [KHz]" and cpu_freq is not None:
        new_y = cpu_freq
    elif title == "CPU Utilization [%]" and cpu_val is not None:
        new_y = cpu_val
    elif title == "CPU Temperature [C°]" and core_temp is not None:
        new_y = core_temp
    elif title == "Memory Utilization [%]" and mem_val is not None:
        new_y = mem_val
    elif title == "GPU Package Power Usage [W]" and gpu_package_power is not None:
        new_y = gpu_package_power
    elif title == "GPU Power Usage [W]" and gpu_power is not None:
        new_y = gpu_power
    elif title == "GPU Frequency [MHz]" and gpu_freq is not None:
        new_y = gpu_freq
    elif title == "GPU Render Engine Utilization [%]" and gpu_render is not None:
        new_y = gpu_render
    elif title == "GPU Video Enhance Engine Utilization [%]" and gpu_ve is not None:
        new_y = gpu_ve
    elif title == "GPU Video Engine Utilization [%]" and gpu_video is not None:
        new_y = gpu_video
    elif title == "GPU Copy Engine Utilization [%]" and gpu_copy is not None:
        new_y = gpu_copy
    elif title == "GPU Compute Engine Utilization [%]" and gpu_compute is not None:
        new_y = gpu_compute

    new_row = pd.DataFrame([[new_x, new_y]], columns=["x", "y"])
    stream_dfs[i] = pd.concat(
        [stream_dfs[i] if not stream_dfs[i].empty else None, new_row], ignore_index=True
    ).tail(50)

    fig = figs[i]
    fig.data = []  # clear previous trace
    fig.add_trace(go.Scatter(x=stream_dfs[i]["x"], y=stream_dfs[i]["y"], mode="lines"))

    return fig


def on_run(
    recording_channels,
    inferencing_channels,
    object_detection_model,
    object_detection_device,
    object_detection_batch_size,
    object_detection_inference_interval,
    object_detection_nireq,
    object_classification_model,
    object_classification_device,
    object_classification_batch_size,
    object_classification_inference_interval,
    object_classification_nireq,
    object_classification_reclassify_interval,
    input_video_player,
):

    video_output_path, constants, param_grid = prepare_video_and_constants(
        input_video_player=input_video_player,
        object_detection_model=object_detection_model,
        object_detection_device=object_detection_device,
        object_detection_batch_size=object_detection_batch_size,
        object_detection_inference_interval=object_detection_inference_interval,
        object_detection_nireq=object_detection_nireq,
        object_classification_model=object_classification_model,
        object_classification_device=object_classification_device,
        object_classification_batch_size=object_classification_batch_size,
        object_classification_inference_interval=object_classification_inference_interval,
        object_classification_nireq=object_classification_nireq,
        object_classification_reclassify_interval=object_classification_reclassify_interval,
    )

    # Validate channels
    if recording_channels + inferencing_channels == 0:
        raise gr.Error(
            "Please select at least one channel for recording or inferencing.",
            duration=10,
        )

    optimizer = PipelineOptimizer(
        pipeline=current_pipeline,
        constants=constants,
        param_grid=param_grid,
        channels=(recording_channels, inferencing_channels),
        elements=gst_inspector.get_elements(),
    )
    optimizer.optimize()
    best_result = optimizer.evaluate()
    if best_result is None:
        best_result_message = "No valid result was returned by the optimizer."
    else:
        best_result_message = (
            f"Total FPS: {best_result.total_fps:.2f}, "
            f"Per Stream FPS: {best_result.per_stream_fps:.2f}"
        )

    return [video_output_path, best_result_message]


def on_benchmark(
    fps_floor,
    rate,
    object_detection_model,
    object_detection_device,
    object_detection_batch_size,
    object_detection_inference_interval,
    object_detection_nireq,
    object_classification_model,
    object_classification_device,
    object_classification_batch_size,
    object_classification_inference_interval,
    object_classification_nireq,
    object_classification_reclassify_interval,
    input_video_player,
):

    _, constants, param_grid = prepare_video_and_constants(
        input_video_player=input_video_player,
        object_detection_model=object_detection_model,
        object_detection_device=object_detection_device,
        object_detection_batch_size=object_detection_batch_size,
        object_detection_inference_interval=object_detection_inference_interval,
        object_detection_nireq=object_detection_nireq,
        object_classification_model=object_classification_model,
        object_classification_device=object_classification_device,
        object_classification_batch_size=object_classification_batch_size,
        object_classification_inference_interval=object_classification_inference_interval,
        object_classification_nireq=object_classification_nireq,
        object_classification_reclassify_interval=object_classification_reclassify_interval,
    )

    # Initialize the benchmark class
    bm = Benchmark(
        video_path=input_video_player,
        pipeline_cls=current_pipeline,
        fps_floor=fps_floor,
        rate=rate,
        parameters=param_grid,
        constants=constants,
        elements=gst_inspector.get_elements(),
    )

    # Run the benchmark
    s, ai, non_ai, fps = bm.run()

    # Return results
    return f"Best Config: {s} streams ({ai} AI, {non_ai} non-AI -> {fps:.2f} FPS)"


def on_stop():
    utils.cancelled = True
    logging.warning(f"utils.cancelled in on_stop: {utils.cancelled}")


# Create the interface
def create_interface():
    """
    Components declarations starts here.
    Only components that are used in event handlers needs to be declared.
    Other components can be created directly in the Blocks context.
    """

    # Video Player
    input_video_player = None

    try:
        download_file(
            "https://github.com/intel-iot-devkit/sample-videos/raw/master/person-bicycle-car-detection.mp4",
            "/tmp/person-bicycle-car-detection.mp4",
        )
        input_video_player = gr.Video(
            label="Input Video",
            interactive=True,
            value="/tmp/person-bicycle-car-detection.mp4",
            sources="upload",
        )
    except Exception as e:
        print(f"Error loading video player: {e}")
        print("Falling back to local video player")

        input_video_player = gr.Video(
            label="Input Video",
            interactive=True,
            value="/opt/intel/dlstreamer/gstreamer/src/gst-plugins-bad-1.24.12/tests/files/mse.mp4",
            sources="upload",
        )

    output_video_player = gr.Video(
        label="Output Video", interactive=False, show_download_button=True
    )

    # Input components
    pipeline_image = gr.Image(
        value=current_pipeline.diagram(),
        label="Pipeline Diagram",
        elem_id="pipeline_image",
        interactive=False,
        show_download_button=False,
        show_fullscreen_button=False,
    )

    # Textbox to display the best configuration (initially hidden)
    best_config_textbox = gr.Textbox(
        label="Best Configuration",
        interactive=False,
        lines=2,
        placeholder="The best configuration will appear here after benchmarking.",
        visible=True,  # Initially hidden
    )

    # Inferencing channels
    inferencing_channels = gr.Slider(
        minimum=0,
        maximum=30,
        value=11,
        step=1,
        label="Number of Recording + Inferencing channels",
        interactive=True,
    )

    # Recording channels
    recording_channels = gr.Slider(
        minimum=0,
        maximum=30,
        value=3,
        step=1,
        label="Number of Recording only channels",
        interactive=True,
    )

    # FPS floor
    fps_floor = gr.Number(
        label="Set FPS Floor",
        value=30.0,  # Default value
        minimum=1.0,
        interactive=True,
    )

    # AI stream rate
    rate = gr.Slider(
        label="AI Stream Rate (%)",
        value=20,  # Default value
        minimum=0,
        maximum=100,
        step=1,
        interactive=True,
    )

    # Inference accordion
    inference_accordion = gr.Accordion("Inference Parameters", open=True)

    # Get available and preferred devices for inference
    device_choices = [
        (device.full_device_name, device.device_name)
        for device in device_discovery.list_devices()
    ]
    preferred_device = next(
        ("GPU" for device_name in device_choices if "GPU" in device_name),
        ("CPU"),
    )

    # Object detection model
    object_detection_model = gr.Dropdown(
        label="Object Detection Model",
        choices=[
            "SSDLite MobileNet V2",
            "YOLO v5m 416x416",
            "YOLO v5s 416x416",
            "YOLO v5m 640x640",
            "YOLO v10s 640x640",
            "YOLO v10m 640x640",
        ],
        value="YOLO v5s 416x416",
    )

    # Object detection device
    object_detection_device = gr.Dropdown(
        label="Object Detection Device",
        choices=device_choices,
        value=preferred_device,
    )

    # Object detection batch size
    object_detection_batch_size = gr.Slider(
        minimum=0,
        maximum=32,
        value=0,
        step=1,
        label="Object Detection Batch Size",
        interactive=True,
    )

    # Object detection inference interval
    object_detection_inference_interval = gr.Slider(
        minimum=1,
        maximum=5,
        value=1,
        step=1,
        label="Object Detection Inference Interval",
        interactive=True,
    )

    # Object Detection number of inference requests (nireq)
    object_detection_nireq = gr.Slider(
        minimum=0,
        maximum=4,
        value=0,
        step=1,
        label="Object Detection Number of Inference Requests (nireq)",
        interactive=True,
    )

    # Object classification model
    object_classification_model = gr.Dropdown(
        label="Object Classification Model",
        choices=[
            "EfficientNet B0",
            "MobileNet V2 PyTorch",
            "ResNet-50 TF",
        ],
        value="ResNet-50 TF",
    )

    # Object classification device
    object_classification_device = gr.Dropdown(
        label="Object Classification Device",
        choices=device_choices,
        value=preferred_device,
    )

    # Object classification batch size
    object_classification_batch_size = gr.Slider(
        minimum=0,
        maximum=32,
        value=0,
        step=1,
        label="Object Classification Batch Size",
        interactive=True,
    )

    # Object classification inference interval
    object_classification_inference_interval = gr.Slider(
        minimum=1,
        maximum=5,
        value=1,
        step=1,
        label="Object Classification Inference Interval",
        interactive=True,
    )

    # Object classification number of inference requests (nireq)
    object_classification_nireq = gr.Slider(
        minimum=0,
        maximum=4,
        value=0,
        step=1,
        label="Object Classification Number of Inference Requests (nireq)",
        interactive=True,
    )

    # Object classification reclassify interval
    object_classification_reclassify_interval = gr.Slider(
        minimum=0,
        maximum=5,
        value=1,
        step=1,
        label="Object Classification Reclassification Interval",
        interactive=True,
    )

    # Run button
    run_button = gr.Button("Run")

    # Benchmark button
    benchmark_button = gr.Button("Benchmark")

    # Stop button
    stop_button = gr.Button("Stop", variant="stop", visible=False)

    # Metrics plots
    plots = [
        gr.Plot(
            value=create_empty_fig(chart_titles[i], y_labels[i]),
            label=chart_titles[i],
            min_width=500,
            show_label=False,
        )
        for i in range(len(chart_titles))
    ]

    # Timer for stream data
    timer = gr.Timer(1, active=False)

    # Interface layout
    with gr.Blocks(theme=theme, css=css_code) as demo:

        """
        Components events handlers and interactions are defined here.
        """

        # Handle click on the pipeline image
        pipeline_image.select(
            detect_click,
            None,
            [inference_accordion],
        )

        # Handle changes on the input video player
        input_video_player.change(
            lambda v: (
                (
                    gr.update(interactive=bool(v)),
                    gr.update(value=None),
                )  # Disable Run button  if input is empty, clears output
                if v is None or v == ""
                else (gr.update(interactive=True), gr.update(value=None))
            ),
            inputs=input_video_player,
            outputs=[run_button, output_video_player],
            queue=False,
        )

        # Handle timer ticks
        timer.tick(
            lambda: [generate_stream_data(i) for i in range(len(chart_titles))],
            outputs=plots,
        )

        # Handle run button clicks
        run_button.click(
            # Update the state of the buttons
            lambda: [
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=True),
            ],
            outputs=[run_button, benchmark_button, stop_button],
            queue=True,
        ).then(
            # Reset the telemetry plots
            lambda: (
                globals().update(
                    stream_dfs=[
                        pd.DataFrame(columns=["x", "y"])
                        for _ in range(len(chart_titles))
                    ]
                )
                or [
                    plots[i].value.update(data=[])
                    for i in range(len(plots))
                ]
                or plots
            ),
            outputs=plots,
        ).then(
            # Start the telemetry timer
            lambda: gr.update(active=True),
            inputs=None,
            outputs=timer,
        ).then(
            # Execute the pipeline
            on_run,
            inputs=[
                recording_channels,
                inferencing_channels,
                object_detection_model,
                object_detection_device,
                object_detection_batch_size,
                object_detection_inference_interval,
                object_detection_nireq,
                object_classification_model,
                object_classification_device,
                object_classification_batch_size,
                object_classification_inference_interval,
                object_classification_nireq,
                object_classification_reclassify_interval,
                input_video_player,
            ],
            outputs=[output_video_player, best_config_textbox],
        ).then(
            # Stop the telemetry timer
            lambda: gr.update(active=False),
            inputs=None,
            outputs=timer,
        ).then(
            # Generate the persistent telemetry data
            lambda: [generate_stream_data(i) for i in range(len(chart_titles))],
            inputs=None,
            outputs=plots,
        ).then(
            # Update the visibility of the buttons
            lambda: [
                gr.update(visible=True),
                gr.update(visible=True),
                gr.update(visible=False),
            ],
            outputs=[run_button, benchmark_button, stop_button],
        )

        # Handle benchmark button clicks
        benchmark_button.click(
            # Update the state of the buttons
            lambda: [
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=True),
            ],
            outputs=[run_button, benchmark_button, stop_button],
            queue=False,
        ).then(
            # Clear output components here
            lambda: [
                gr.update(value=""), 
                gr.update(value=None),
            ],
            None,
            [best_config_textbox, output_video_player],
        ).then(
            # Reset the telemetry plots
            lambda: (
                globals().update(
                    stream_dfs=[
                        pd.DataFrame(columns=["x", "y"])
                        for _ in range(len(chart_titles))
                    ]
                )
                or [
                    plots[i].value.update(data=[])
                    for i in range(len(plots))
                ]
                or plots
            ),
            outputs=plots,
        ).then(
            # Start the telemetry timer
            lambda: gr.update(active=True),
            inputs=None,
            outputs=timer,
        ).then(
            # Execute the benchmark
            on_benchmark,
            inputs=[
                fps_floor,
                rate,
                object_detection_model,
                object_detection_device,
                object_detection_batch_size,
                object_detection_inference_interval,
                object_detection_nireq,
                object_classification_model,
                object_classification_device,
                object_classification_batch_size,
                object_classification_inference_interval,
                object_classification_nireq,
                object_classification_reclassify_interval,
                input_video_player,
            ],
            outputs=[best_config_textbox],
        ).then(
            # Stop the telemetry timer
            lambda: gr.update(active=False),
            inputs=None,
            outputs=timer,
        ).then(
            # Generate the persistent telemetry data
            lambda: [generate_stream_data(i) for i in range(len(chart_titles))],
            inputs=None,
            outputs=plots,
        ).then(
            # Reset the state of the buttons
            lambda: [
                gr.update(visible=True),
                gr.update(visible=True),
                gr.update(visible=False),
            ],
            outputs=[run_button, benchmark_button, stop_button],
        )

        # Handle stop button clicks
        stop_button.click(
            # Execute the stop function
            on_stop,
        ).then(
            # Reset the state of the buttons
            lambda: [
                gr.update(visible=True),
                gr.update(visible=True),
                gr.update(visible=False),
            ],
            outputs=[run_button, benchmark_button, stop_button],
            queue=False,
        )

        """
        Components rendering starts here.
        """

        # Header
        gr.HTML(
            "<div class='spark-header'>"
            "  <div class='spark-header-line'></div>"
            "  <img src='https://www.intel.com/content/dam/logos/intel-header-logo.svg' class='spark-logo'></img>"
            "  <div class='spark-title'>Visual Pipeline and Platform Evaluation Tool</div>"
            "</div>"
        )

        # Tab Interface
        with gr.Tabs() as tabs:

            # Home Tab
            with gr.Tab("Home", id=0):

                gr.Markdown(
                    """
                    ## Recommended Pipelines

                    Below is a list of recommended pipelines you can use to evaluate video analytics performance.
                    Click on "Configure and Run" to get started with customizing and benchmarking a pipeline for your
                    use case.
                    """
                )

                with gr.Row():

                    for pipeline in PipelineLoader.list():

                        pipeline_info = PipelineLoader.config(pipeline)

                        with gr.Column(scale=1, min_width=100):

                            gr.Image(
                                value=lambda x=pipeline: f"./pipelines/{x}/thumbnail.png",
                                show_label=False,
                                show_download_button=False,
                                show_fullscreen_button=False,
                                interactive=False,
                                width=710,
                            )

                            gr.Markdown(
                                f"### {pipeline_info['name']}\n"
                                f"{pipeline_info['definition']}"
                            )

                            gr.Button(
                                value="Configure and Run",
                                elem_classes="configure-and-run-button",
                                interactive=True,
                            ).click(
                                lambda x=pipeline: globals().__setitem__(
                                    "current_pipeline", PipelineLoader.load(x)[0]
                                ),
                                None,
                                None,
                            ).then(
                                lambda: current_pipeline.diagram(),
                                None,
                                pipeline_image,
                            ).then(
                                # Clear output components here
                                lambda: [
                                    gr.update(value=""), 
                                    gr.update(value=None),
                                ],
                                None,
                                [best_config_textbox, output_video_player],
                            ).then(
                                # Reset the telemetry plots
                                lambda: (
                                    globals().update(
                                        stream_dfs=[
                                            pd.DataFrame(columns=["x", "y"])
                                            for _ in range(len(chart_titles))
                                        ]
                                    )
                                    or [
                                        plots[i].value.update(data=[])
                                        for i in range(len(plots))
                                    ]
                                    or plots
                                ),
                                outputs=plots,
                            ).then(
                                lambda: gr.Tabs(selected=1),
                                None,
                                tabs,
                            )

                gr.Markdown(
                    """
                    ## Your System

                    This section provides information about your system's hardware and software configuration.
                    """
                )

                devices = device_discovery.list_devices()
                if devices:
                    device_table_md = "| Name | Description |\n|------|-------------|\n"
                    for device in devices:
                        device_table_md += (
                            f"| {device.device_name} | {device.full_device_name} |\n"
                        )
                else:
                    device_table_md = "No devices found."
                gr.Markdown(
                    value=device_table_md,
                    elem_id="device_table",
                )

            # Run Tab
            with gr.Tab("Run", id=1):

                # Main content
                with gr.Row():

                    # Left column
                    with gr.Column(scale=2, min_width=300):

                        # Render pipeline image
                        pipeline_image.render()

                        # Render the run button
                        run_button.render()

                        # Render the benchmark button
                        benchmark_button.render()

                        # Render the stop button
                        stop_button.render()

                        # Render the best configuration textbox
                        best_config_textbox.render()

                        # Metrics plots
                        with gr.Row():

                            # Render plots
                            for i in range(len(plots)):
                                plots[i].render()

                            # Render the timer
                            timer.render()

                    # Right column
                    with gr.Column(scale=1, min_width=150):

                        # Video Player Accordion
                        with gr.Accordion("Video Player", open=True):

                            # Input Video Player
                            input_video_player.render()

                            # Output Video Player
                            output_video_player.render()

                        # Pipeline Parameters Accordion
                        with gr.Accordion("Pipeline Parameters", open=True):

                            # Inference Channels
                            inferencing_channels.render()

                            # Recording Channels
                            recording_channels.render()

                        # Benchmark Parameters Accordion
                        with gr.Accordion("Benchmark Parameters", open=True):

                            # FPS Floor
                            fps_floor.render()

                            # AI Stream Rate
                            rate.render()

                        # Inference Parameters Accordion
                        with inference_accordion.render():

                            # Object Detection Parameters
                            object_detection_model.render()
                            object_detection_device.render()
                            object_detection_batch_size.render()
                            object_detection_inference_interval.render()
                            object_detection_nireq.render()

                            # Object Classification Parameters
                            object_classification_model.render()
                            object_classification_device.render()
                            object_classification_batch_size.render()
                            object_classification_inference_interval.render()
                            object_classification_nireq.render()
                            object_classification_reclassify_interval.render()

        # Footer
        gr.HTML(
            "<div class='spark-footer'>"
            "  <div class='spark-footer-info'>"
            "    ©2025 Intel Corporation  |  Terms of Use  |  Cookies  |  Privacy"
            "  </div>"
            "</div>"
        )

    gr.close_all()
    return demo


if __name__ == "__main__":
    # Launch the app
    demo = create_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
    )
