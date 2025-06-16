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
from pipeline import PipelineLoader, GstPipeline
from utils import prepare_video_and_constants
from typing import Tuple, Dict

logging.getLogger("httpx").setLevel(logging.WARNING)

with open(os.path.join(os.path.dirname(__file__), "app.css")) as f:
    css_code = f.read()

theme = gr.themes.Default(
    primary_hue="blue",
    font=[gr.themes.GoogleFont("Montserrat"), "ui-sans-serif", "sans-serif"],
)

# Initialize the pipeline based on the PIPELINE environment variable
current_pipeline: Tuple[GstPipeline, Dict] = PipelineLoader.load(
    os.environ.get("PIPELINE", "").lower()
)
device_discovery = DeviceDiscovery()
gst_inspector = GstInspector()

# Get available and preferred devices for inference
device_choices = [
    (device.full_device_name, device.device_name)
    for device in device_discovery.list_devices()
]

# Device detection and chart title logic (move here, fix indentation)
has_igpu = any("iGPU" in name or "igpu" in name for name, _ in device_choices)
has_dgpu = any(
    "dGPU" in name or "dgpu" in name or "Discrete" in name or "discrete" in name
    for name, _ in device_choices
)

all_chart_titles = [
    "Pipeline Throughput [FPS]",
    "CPU Frequency [KHz]",
    "CPU Utilization [%]",
    "CPU Temperature [C°]",
    "Memory Utilization [%]",
    "Integrated GPU Power Usage [W] (Package & Total)",
    "Integrated GPU Frequency [MHz]",
    "Integrated GPU Engine Utilization [%]",
    "Discrete GPU Power Usage [W] (Package & Total)",
    "Discrete GPU Frequency [MHz]",
    "Discrete GPU Engine Utilization [%]",
]
all_y_labels = [
    "Throughput",
    "Frequency",
    "Utilization",
    "Temperature",
    "Utilization",
    "Power",
    "Frequency",
    "Utilization",
    "Power",
    "Frequency",
    "Utilization",
]

igpu_indices = [5, 6, 7]
dgpu_indices = [8, 9, 10]

indices_to_remove = []
if not has_igpu:
    indices_to_remove += igpu_indices
if not has_dgpu:
    indices_to_remove += dgpu_indices

chart_titles = [t for i, t in enumerate(all_chart_titles) if i not in indices_to_remove]
y_labels = [y for i, y in enumerate(all_y_labels) if i not in indices_to_remove]

# Create a dataframe for each chart
stream_dfs = [pd.DataFrame(columns=["x", "y"]) for _ in range(len(chart_titles))]
figs = [
    go.Figure().update_layout(
        title=chart_titles[i], xaxis_title="Time", yaxis_title=y_labels[i]
    )
    for i in range(len(chart_titles))
]


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
    ) in current_pipeline[0].bounding_boxes():
        if x_min <= x <= x_max and y_min <= y <= y_max:

            match label:
                case "Inference":
                    return gr.update(open=True)

    return gr.update(open=False)


def read_latest_metrics(target_ns: int = None):
    try:
        with open("/home/dlstreamer/vippet/.collector-signals/metrics.txt", "r") as f:
            lines = [line.strip() for line in f.readlines()[-500:]]

    except FileNotFoundError:
        return [None] * 20  # 12 original + 8 extra for GPU 0

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

    # GPU 0 variables (do not change existing ones for gpu_1)
    gpu_package_power_0 = gpu_power_0 = gpu_freq_0 = gpu_render_0 = gpu_ve_0 = (
        gpu_video_0
    ) = gpu_copy_0 = gpu_compute_0 = None

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

        # Only consider GPU-related metrics for gpu_id=1
        if gpu_package_power is None and "pkg_cur_power" in line and "gpu_id=1" in line:
            parts = line.split()
            try:
                gpu_package_power = float(parts[1].split("=")[1])
            except:
                pass

        if gpu_power is None and "gpu_cur_power" in line and "gpu_id=1" in line:
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

        if gpu_freq is None and "gpu_frequency" in line and "gpu_id=1" in line:
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

        if gpu_render is None and "engine=render" in line and "gpu_id=1" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_render = float(part.split("=")[1])
                    except:
                        pass

        if gpu_copy is None and "engine=copy" in line and "gpu_id=1" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_copy = float(part.split("=")[1])
                    except:
                        pass

        if gpu_ve is None and "engine=video-enhance" in line and "gpu_id=1" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_ve = float(part.split("=")[1])
                    except:
                        pass

        if (
            gpu_video is None
            and "engine=video" in line
            and "engine=video-enhance" not in line
            and "gpu_id=1" in line
        ):
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_video = float(part.split("=")[1])
                    except:
                        pass

        if gpu_compute is None and "engine=compute" in line and "gpu_id=1" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_compute = float(part.split("=")[1])
                    except:
                        pass

        # GPU 0 metrics (new variables)
        if (
            gpu_package_power_0 is None
            and "pkg_cur_power" in line
            and "gpu_id=0" in line
        ):
            parts = line.split()
            try:
                gpu_package_power_0 = float(parts[1].split("=")[1])
            except:
                pass

        if gpu_power_0 is None and "gpu_cur_power" in line and "gpu_id=0" in line:
            parts = line.split()
            try:
                gpu_power_0 = float(parts[1].split("=")[1])
            except:
                pass

        if gpu_freq_0 is None and "gpu_frequency" in line and "gpu_id=0" in line:
            for part in line.split():
                if part.startswith("value="):
                    try:
                        gpu_freq_0 = float(part.split("=")[1])
                    except:
                        pass

        if gpu_render_0 is None and "engine=render" in line and "gpu_id=0" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_render_0 = float(part.split("=")[1])
                    except:
                        pass

        if gpu_copy_0 is None and "engine=copy" in line and "gpu_id=0" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_copy_0 = float(part.split("=")[1])
                    except:
                        pass

        if gpu_ve_0 is None and "engine=video-enhance" in line and "gpu_id=0" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_ve_0 = float(part.split("=")[1])
                    except:
                        pass

        if (
            gpu_video_0 is None
            and "engine=video" in line
            and "engine=video-enhance" not in line
            and "gpu_id=0" in line
        ):
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_video_0 = float(part.split("=")[1])
                    except:
                        pass

        if gpu_compute_0 is None and "engine=compute" in line and "gpu_id=0" in line:
            for part in line.split():
                if part.startswith("usage="):
                    try:
                        gpu_compute_0 = float(part.split("=")[1])
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
                gpu_package_power_0,
                gpu_power_0,
                gpu_freq_0,
                gpu_render_0,
                gpu_ve_0,
                gpu_video_0,
                gpu_copy_0,
                gpu_compute_0,
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
        gpu_package_power_0,
        gpu_power_0,
        gpu_freq_0,
        gpu_render_0,
        gpu_ve_0,
        gpu_video_0,
        gpu_copy_0,
        gpu_compute_0,
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
    # Unpack all returned values, but only use the first 13 for current charts
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
        gpu_package_power_0,
        gpu_power_0,
        gpu_freq_0,
        gpu_render_0,
        gpu_ve_0,
        gpu_video_0,
        gpu_copy_0,
        gpu_compute_0,
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
    elif title == "Discrete GPU Power Usage [W] (Package & Total)":
        metrics = {
            "Package Power": gpu_package_power,
            "Total Power": gpu_power,
        }
        if stream_dfs[i].empty:
            stream_dfs[i] = pd.DataFrame(columns=["x"] + list(metrics.keys()))
        new_row = {"x": new_x}
        new_row.update(metrics)
        stream_dfs[i] = pd.concat(
            [
                stream_dfs[i] if not stream_dfs[i].empty else None,
                pd.DataFrame([new_row]),
            ],
            ignore_index=True,
        ).tail(50)
        fig = figs[i]
        fig.data = []
        for key in metrics.keys():
            fig.add_trace(
                go.Scatter(
                    x=stream_dfs[i]["x"], y=stream_dfs[i][key], mode="lines", name=key
                )
            )
        return fig
    elif title == "Discrete GPU Frequency [MHz]" and gpu_freq is not None:
        new_y = gpu_freq
    elif title == "Discrete GPU Engine Utilization [%]":
        metrics = {
            "Render": gpu_render,
            "Video Enhance": gpu_ve,
            "Video": gpu_video,
            "Copy": gpu_copy,
            "Compute": gpu_compute,
        }
        # Prepare or update the DataFrame for this chart
        if stream_dfs[i].empty:
            stream_dfs[i] = pd.DataFrame(columns=["x"] + list(metrics.keys()))
        new_row = {"x": new_x}
        new_row.update(metrics)
        stream_dfs[i] = pd.concat(
            [
                stream_dfs[i] if not stream_dfs[i].empty else None,
                pd.DataFrame([new_row]),
            ],
            ignore_index=True,
        ).tail(50)
        fig = figs[i]
        fig.data = []
        for key in metrics.keys():
            fig.add_trace(
                go.Scatter(
                    x=stream_dfs[i]["x"], y=stream_dfs[i][key], mode="lines", name=key
                )
            )
        return fig
    elif title == "Integrated GPU Power Usage [W] (Package & Total)":
        metrics = {
            "Package Power": gpu_package_power_0,
            "Total Power": gpu_power_0,
        }
        if stream_dfs[i].empty:
            stream_dfs[i] = pd.DataFrame(columns=["x"] + list(metrics.keys()))
        new_row = {"x": new_x}
        new_row.update(metrics)
        stream_dfs[i] = pd.concat(
            [
                stream_dfs[i] if not stream_dfs[i].empty else None,
                pd.DataFrame([new_row]),
            ],
            ignore_index=True,
        ).tail(50)
        fig = figs[i]
        fig.data = []
        for key in metrics.keys():
            fig.add_trace(
                go.Scatter(
                    x=stream_dfs[i]["x"], y=stream_dfs[i][key], mode="lines", name=key
                )
            )
        return fig
    elif title == "Integrated GPU Frequency [MHz]" and gpu_freq_0 is not None:
        new_y = gpu_freq_0
    # Consolidated GPU 0 Engine Utilization chart
    elif title == "Integrated GPU Engine Utilization [%]":
        # Each line is a metric, so we store all 5 in the same DataFrame
        # We'll use a wide DataFrame for this chart
        metrics = {
            "Render": gpu_render_0,
            "Video Enhance": gpu_ve_0,
            "Video": gpu_video_0,
            "Copy": gpu_copy_0,
            "Compute": gpu_compute_0,
        }
        # Prepare or update the DataFrame for this chart
        if stream_dfs[i].empty:
            stream_dfs[i] = pd.DataFrame(columns=["x"] + list(metrics.keys()))
        new_row = {"x": new_x}
        new_row.update(metrics)
        stream_dfs[i] = pd.concat(
            [
                stream_dfs[i] if not stream_dfs[i].empty else None,
                pd.DataFrame([new_row]),
            ],
            ignore_index=True,
        ).tail(50)
        fig = figs[i]
        fig.data = []
        for key in metrics.keys():
            fig.add_trace(
                go.Scatter(
                    x=stream_dfs[i]["x"], y=stream_dfs[i][key], mode="lines", name=key
                )
            )
        return fig

    new_row = pd.DataFrame([[new_x, new_y]], columns=["x", "y"])
    stream_dfs[i] = pd.concat(
        [stream_dfs[i] if not stream_dfs[i].empty else None, new_row], ignore_index=True
    ).tail(50)

    fig = figs[i]
    fig.data = []  # clear previous trace
    fig.add_trace(go.Scatter(x=stream_dfs[i]["x"], y=stream_dfs[i]["y"], mode="lines"))

    return fig


def on_run(data):

    arguments = {}

    for component in data:
        component_id = component.elem_id
        if component_id:
            arguments[component_id] = data[component]

    video_output_path, constants, param_grid = prepare_video_and_constants(**arguments)

    # Validate channels
    if arguments["recording_channels"] + arguments["inferencing_channels"] == 0:
        raise gr.Error(
            "Please select at least one channel for recording or inferencing.",
            duration=10,
        )

    optimizer = PipelineOptimizer(
        pipeline=current_pipeline[0],
        constants=constants,
        param_grid=param_grid,
        channels=(arguments["recording_channels"], arguments["inferencing_channels"]),
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


def on_benchmark(data):

    arguments = {}

    for component in data:
        component_id = component.elem_id
        if component_id:
            arguments[component_id] = data[component]

    _, constants, param_grid = prepare_video_and_constants(**arguments)

    # Initialize the benchmark class
    bm = Benchmark(
        video_path=arguments["input_video_player"],
        pipeline_cls=current_pipeline[0],
        fps_floor=arguments["fps_floor"],
        rate=arguments["ai_stream_rate"],
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
            elem_id="input_video_player",
        )
    except Exception as e:
        print(f"Error loading video player: {e}")
        print("Falling back to local video player")

        input_video_player = gr.Video(
            label="Input Video",
            interactive=True,
            value="/opt/intel/dlstreamer/gstreamer/src/gst-plugins-bad-1.24.12/tests/files/mse.mp4",
            sources="upload",
            elem_id="input_video_player",
        )

    output_video_player = gr.Video(
        label="Output Video", interactive=False, show_download_button=True
    )

    # Pipeline diagram image
    pipeline_image = gr.Image(
        value=current_pipeline[0].diagram(),
        label="Pipeline Diagram",
        elem_id="pipeline_image",
        interactive=False,
        show_download_button=False,
        show_fullscreen_button=False,
    )

    # Best configuration textbox
    best_config_textbox = gr.Textbox(
        label="Best Configuration",
        interactive=False,
        lines=2,
        placeholder="The best configuration will appear here after benchmarking.",
        visible=True,
    )

    # Inferencing channels
    inferencing_channels = gr.Slider(
        minimum=0,
        maximum=30,
        value=11,
        step=1,
        label="Number of Recording + Inferencing channels",
        interactive=True,
        elem_id="inferencing_channels",
    )

    # Recording channels
    recording_channels = gr.Slider(
        minimum=0,
        maximum=30,
        value=3,
        step=1,
        label="Number of Recording only channels",
        interactive=True,
        elem_id="recording_channels",
    )

    # FPS floor
    fps_floor = gr.Number(
        label="Set FPS Floor",
        value=30.0,  # Default value
        minimum=1.0,
        interactive=True,
        elem_id="fps_floor",
    )

    # AI stream rate
    ai_stream_rate = gr.Slider(
        label="AI Stream Rate (%)",
        value=20,  # Default value
        minimum=0,
        maximum=100,
        step=1,
        interactive=True,
        elem_id="ai_stream_rate",
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
        elem_id="object_detection_model",
    )

    # Object detection device
    object_detection_device = gr.Dropdown(
        label="Object Detection Device",
        choices=device_choices,
        value=preferred_device,
        elem_id="object_detection_device",
    )

    # Object detection batch size
    object_detection_batch_size = gr.Slider(
        minimum=0,
        maximum=32,
        value=0,
        step=1,
        label="Object Detection Batch Size",
        interactive=True,
        elem_id="object_detection_batch_size",
    )

    # Object detection inference interval
    object_detection_inference_interval = gr.Slider(
        minimum=1,
        maximum=5,
        value=1,
        step=1,
        label="Object Detection Inference Interval",
        interactive=True,
        elem_id="object_detection_inference_interval",
    )

    # Object Detection number of inference requests (nireq)
    object_detection_nireq = gr.Slider(
        minimum=0,
        maximum=4,
        value=0,
        step=1,
        label="Object Detection Number of Inference Requests (nireq)",
        interactive=True,
        elem_id="object_detection_nireq",
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
        elem_id="object_classification_model",
    )

    # Object classification device
    object_classification_device = gr.Dropdown(
        label="Object Classification Device",
        choices=device_choices,
        value=preferred_device,
        elem_id="object_classification_device",
    )

    # Object classification batch size
    object_classification_batch_size = gr.Slider(
        minimum=0,
        maximum=32,
        value=0,
        step=1,
        label="Object Classification Batch Size",
        interactive=True,
        elem_id="object_classification_batch_size",
    )

    # Object classification inference interval
    object_classification_inference_interval = gr.Slider(
        minimum=1,
        maximum=5,
        value=1,
        step=1,
        label="Object Classification Inference Interval",
        interactive=True,
        elem_id="object_classification_inference_interval",
    )

    # Object classification number of inference requests (nireq)
    object_classification_nireq = gr.Slider(
        minimum=0,
        maximum=4,
        value=0,
        step=1,
        label="Object Classification Number of Inference Requests (nireq)",
        interactive=True,
        elem_id="object_classification_nireq",
    )

    # Object classification reclassify interval
    object_classification_reclassify_interval = gr.Slider(
        minimum=0,
        maximum=5,
        value=1,
        step=1,
        label="Object Classification Reclassification Interval",
        interactive=True,
        elem_id="object_classification_reclassify_interval",
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

    # Components Set
    components = set()
    components.add(input_video_player)
    components.add(output_video_player)
    components.add(pipeline_image)
    components.add(best_config_textbox)
    components.add(inferencing_channels)
    components.add(recording_channels)
    components.add(fps_floor)
    components.add(ai_stream_rate)
    components.add(object_detection_model)
    components.add(object_detection_device)
    components.add(object_detection_batch_size)
    components.add(object_detection_inference_interval)
    components.add(object_detection_nireq)
    components.add(object_classification_model)
    components.add(object_classification_device)
    components.add(object_classification_batch_size)
    components.add(object_classification_inference_interval)
    components.add(object_classification_nireq)
    components.add(object_classification_reclassify_interval)

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
                    if hasattr(plots[i], "value") and plots[i].value is not None
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
            inputs=components,
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
                    if hasattr(plots[i], "value") and plots[i].value is not None
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
            inputs=components,
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

                            is_enabled = pipeline_info.get("metadata", {}).get(
                                "enabled", False
                            )

                            gr.Button(
                                value=(
                                    "Configure and Run" if is_enabled else "Coming Soon"
                                ),
                                elem_classes="configure-and-run-button",
                                interactive=is_enabled,
                            ).click(
                                lambda x=pipeline: globals().__setitem__(
                                    "current_pipeline", PipelineLoader.load(x)
                                ),
                                None,
                                None,
                            ).then(
                                lambda: current_pipeline[0].diagram(),
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
                                        if hasattr(plots[i], "value")
                                        and plots[i].value is not None
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

                        # Render the pipeline information
                        gr.Markdown(
                            f"### {current_pipeline[1]['name']}\n"
                            f"{current_pipeline[1]['definition']}"
                        )

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
                            ai_stream_rate.render()

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
