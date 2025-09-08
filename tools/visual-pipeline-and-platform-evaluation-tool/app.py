import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import gradio as gr
import pandas as pd
import plotly.graph_objects as go
import requests

import utils
from benchmark import Benchmark
from chart import Chart, ChartType, create_charts
from device import DeviceDiscovery, DeviceFamily, DeviceType
from explore import GstInspector
from optimize import PipelineOptimizer
from gstpipeline import GstPipeline, PipelineLoader
from utils import prepare_video_and_constants

logging.getLogger("httpx").setLevel(logging.WARNING)

TEMP_DIR = "/tmp/"

METRICS_FILE_PATH = "/home/dlstreamer/vippet/.collector-signals/metrics.txt"
FPS_FILE_PATH = "/home/dlstreamer/vippet/.collector-signals/fps.txt"

INFERENCING_CHANNELS_LABEL = "Number of Inferencing channels"
RECORDING_AND_INFERENCING_CHANNELS_LABEL = "Number of Recording + Inferencing channels"

with open(os.path.join(os.path.dirname(__file__), "app.css")) as f:
    css_code = f.read()

theme = gr.themes.Default(  # pyright: ignore[reportPrivateImportUsage]
    primary_hue="blue",
    font=[gr.themes.GoogleFont("Montserrat"), "ui-sans-serif", "sans-serif"],  # pyright: ignore[reportPrivateImportUsage]
)

# Initialize the pipeline based on the PIPELINE environment variable
current_pipeline: Tuple[GstPipeline, Dict] = PipelineLoader.load(
    os.environ.get("PIPELINE", "").lower()
)
gst_inspector = GstInspector()
device_discovery = DeviceDiscovery()

# Device detection and chart title logic
charts: List[Chart] = create_charts(device_discovery.list_devices())


# Download File
def download_file(url, local_filename):
    # Send a GET request to the URL
    with requests.get(url, stream=True) as response:
        response.raise_for_status()  # Check if the request was successful
        # Open a local file with write-binary mode
        with open(os.path.join(TEMP_DIR, local_filename), "wb") as file:
            # Iterate over the response content in chunks
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)  # Write each chunk to the local file


# Set video path for the input video player
def set_video_path(filename):
    if not os.path.exists(os.path.join(TEMP_DIR, filename)):
        return gr.update(
            label="Error: Video file not found. Verify the recording URL or proxy settings.",
            value=None,
        )
    return gr.update(label="Input Video", value=os.path.join(TEMP_DIR, filename))


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


def read_latest_metrics():
    # Get all gpu_ids present in charts
    gpu_ids_in_charts = set(
        chart.gpu_id for chart in charts if chart.gpu_id is not None
    )

    # Prepare metrics map with all keys set to None
    metrics: dict[str, Optional[float]] = {
        "cpu_user": None,
        "mem_used_percent": None,
        "core_temp": None,
        "cpu_freq": None,
    }
    # For each GPU id, add all relevant metrics keys
    gpu_metric_keys = [
        "gpu_package_power",
        "gpu_power",
        "gpu_freq",
        "gpu_render",
        "gpu_ve",
        "gpu_video",
        "gpu_copy",
        "gpu_compute",
    ]
    for gpu_id in gpu_ids_in_charts:
        for key in gpu_metric_keys:
            metrics[f"{key}_{gpu_id}"] = None

    try:
        with open(METRICS_FILE_PATH, "r") as metrics_file:
            lines = [line.strip() for line in metrics_file.readlines()[-500:]]
    except FileNotFoundError:
        return metrics

    for line in reversed(lines):
        line = normalize_engine_names(line)

        # CPU metrics
        if metrics["cpu_user"] is None and "cpu" in line:
            parts = line.split()
            if len(parts) > 1:
                for field in parts[1].split(","):
                    if field.startswith("usage_user="):
                        try:
                            metrics["cpu_user"] = float(field.split("=")[1])
                        except (ValueError, IndexError):
                            pass

        if metrics["mem_used_percent"] is None and "mem" in line:
            parts = line.split()
            if len(parts) > 1:
                for field in parts[1].split(","):
                    if field.startswith("used_percent="):
                        try:
                            metrics["mem_used_percent"] = float(field.split("=")[1])
                        except (ValueError, IndexError):
                            pass

        if metrics["core_temp"] is None and "temp" in line:
            parts = line.split()
            if len(parts) > 1:
                for field in parts[1].split(","):
                    if "temp" in field:
                        try:
                            metrics["core_temp"] = float(field.split("=")[1])
                        except (ValueError, IndexError):
                            pass

        if metrics["cpu_freq"] is None and "cpu_frequency_avg" in line:
            try:
                parts = [part for part in line.split() if "frequency=" in part]
                if parts:
                    metrics["cpu_freq"] = float(parts[0].split("=")[1])
            except (ValueError, IndexError):
                pass

        # GPU metrics for all detected gpu_ids
        for gpu_id in gpu_ids_in_charts:
            id_str = f"gpu_id={gpu_id}"
            # Package Power
            key = f"gpu_package_power_{gpu_id}"
            if metrics[key] is None and "pkg_cur_power" in line and id_str in line:
                parts = line.split()
                try:
                    metrics[key] = float(parts[1].split("=")[1])
                except (ValueError, IndexError):
                    pass
            # Total Power
            key = f"gpu_power_{gpu_id}"
            if metrics[key] is None and "gpu_cur_power" in line and id_str in line:
                parts = line.split()
                try:
                    metrics[key] = float(parts[1].split("=")[1])
                except (ValueError, IndexError):
                    pass
            # Frequency
            key = f"gpu_freq_{gpu_id}"
            if metrics[key] is None and "gpu_frequency" in line and id_str in line:
                for part in line.split():
                    if part.startswith("value="):
                        try:
                            metrics[key] = float(part.split("=")[1])
                        except (ValueError, IndexError):
                            pass
            # Render
            key = f"gpu_render_{gpu_id}"
            if metrics[key] is None and "engine=render" in line and id_str in line:
                for part in line.split():
                    if part.startswith("usage="):
                        try:
                            metrics[key] = float(part.split("=")[1])
                        except (ValueError, IndexError):
                            pass
            # Copy
            key = f"gpu_copy_{gpu_id}"
            if metrics[key] is None and "engine=copy" in line and id_str in line:
                for part in line.split():
                    if part.startswith("usage="):
                        try:
                            metrics[key] = float(part.split("=")[1])
                        except (ValueError, IndexError):
                            pass
            # Video Enhance
            key = f"gpu_ve_{gpu_id}"
            if (
                metrics[key] is None
                and "engine=video-enhance" in line
                and id_str in line
            ):
                for part in line.split():
                    if part.startswith("usage="):
                        try:
                            metrics[key] = float(part.split("=")[1])
                        except (ValueError, IndexError):
                            pass
            # Video
            key = f"gpu_video_{gpu_id}"
            if (
                metrics[key] is None
                and "engine=video" in line
                and "engine=video-enhance" not in line
                and id_str in line
            ):
                for part in line.split():
                    if part.startswith("usage="):
                        try:
                            metrics[key] = float(part.split("=")[1])
                        except (ValueError, IndexError):
                            pass
            # Compute
            key = f"gpu_compute_{gpu_id}"
            if metrics[key] is None and "engine=compute" in line and id_str in line:
                for part in line.split():
                    if part.startswith("usage="):
                        try:
                            metrics[key] = float(part.split("=")[1])
                        except (ValueError, IndexError):
                            pass

        # Early exit if all metrics are filled
        if all(v is not None for v in metrics.values()):
            break

    return metrics


def normalize_engine_names(line: str) -> str:
    """
    Class names for XE drivers: https://github.com/ulissesf/qmassa/blob/v1.0.1/src/drm_drivers/xe.rs#L79-L92
    are different from those used in i915 drivers: https://github.com/ulissesf/qmassa/blob/v1.0.1/src/drm_drivers/i915.rs#L100-L113
    Normalize them to the i915 names.
    """
    return (
        line.replace("engine=rcs", "engine=render")
        .replace("engine=bcs", "engine=copy")
        .replace("engine=ccs", "engine=compute")
        .replace("engine=vcs", "engine=video")
        .replace("engine=vecs", "engine=video-enhance")
    )


def generate_stream_data():
    new_x = datetime.now()

    # Read metrics once
    metrics = read_latest_metrics()

    # Read FPS once
    latest_fps = 0
    try:
        with open(FPS_FILE_PATH, "r") as fps_file:
            lines = [line.strip() for line in fps_file.readlines()[-500:]]
            latest_fps = float(lines[-1])
    except (FileNotFoundError, IndexError):
        latest_fps = 0

    figs = []
    for chart in charts:
        new_y = 0

        if chart.type == ChartType.PIPELINE_THROUGHPUT:
            new_y = latest_fps
        elif chart.type == ChartType.CPU_FREQUENCY and metrics["cpu_freq"] is not None:
            new_y = metrics["cpu_freq"]
        elif (
            chart.type == ChartType.CPU_UTILIZATION and metrics["cpu_user"] is not None
        ):
            new_y = metrics["cpu_user"]
        elif (
            chart.type == ChartType.CPU_TEMPERATURE and metrics["core_temp"] is not None
        ):
            new_y = metrics["core_temp"]
        elif (
            chart.type == ChartType.MEMORY_UTILIZATION
            and metrics["mem_used_percent"] is not None
        ):
            new_y = metrics["mem_used_percent"]
        elif chart.type == ChartType.DGPU_POWER and chart.gpu_id is not None:
            metrics_dict = {
                "Package Power": metrics.get(f"gpu_package_power_{chart.gpu_id}"),
                "Total Power": metrics.get(f"gpu_power_{chart.gpu_id}"),
            }
            figs.append(update_multi_metric_chart(chart, metrics_dict, new_x))
            continue
        elif chart.type == ChartType.DGPU_FREQUENCY and chart.gpu_id is not None:
            freq = metrics.get(f"gpu_freq_{chart.gpu_id}")
            if freq is not None:
                new_y = freq
        elif (
            chart.type == ChartType.DGPU_ENGINE_UTILIZATION and chart.gpu_id is not None
        ):
            metrics_dict = {
                "Render": metrics.get(f"gpu_render_{chart.gpu_id}"),
                "Video Enhance": metrics.get(f"gpu_ve_{chart.gpu_id}"),
                "Video": metrics.get(f"gpu_video_{chart.gpu_id}"),
                "Copy": metrics.get(f"gpu_copy_{chart.gpu_id}"),
                "Compute": metrics.get(f"gpu_compute_{chart.gpu_id}"),
            }
            figs.append(update_multi_metric_chart(chart, metrics_dict, new_x))
            continue
        elif chart.type == ChartType.IGPU_POWER and chart.gpu_id is not None:
            metrics_dict = {
                "Package Power": metrics.get(f"gpu_package_power_{chart.gpu_id}"),
                "Total Power": metrics.get(f"gpu_power_{chart.gpu_id}"),
            }
            figs.append(update_multi_metric_chart(chart, metrics_dict, new_x))
            continue
        elif chart.type == ChartType.IGPU_FREQUENCY and chart.gpu_id is not None:
            freq = metrics.get(f"gpu_freq_{chart.gpu_id}")
            if freq is not None:
                new_y = freq
        elif (
            chart.type == ChartType.IGPU_ENGINE_UTILIZATION and chart.gpu_id is not None
        ):
            metrics_dict = {
                "Render": metrics.get(f"gpu_render_{chart.gpu_id}"),
                "Video Enhance": metrics.get(f"gpu_ve_{chart.gpu_id}"),
                "Video": metrics.get(f"gpu_video_{chart.gpu_id}"),
                "Copy": metrics.get(f"gpu_copy_{chart.gpu_id}"),
                "Compute": metrics.get(f"gpu_compute_{chart.gpu_id}"),
            }
            figs.append(update_multi_metric_chart(chart, metrics_dict, new_x))
            continue

        new_row = pd.DataFrame({"x": [new_x], "y": [new_y]})
        # Only include non-empty DataFrames in concat to avoid FutureWarning
        if chart.df.empty:
            chart.df = new_row
        else:
            chart.df = pd.concat([chart.df, new_row], ignore_index=True).tail(50)

        chart.fig.data = []  # clear previous trace
        chart.fig.add_trace(go.Scatter(x=chart.df["x"], y=chart.df["y"], mode="lines"))

        figs.append(chart.fig)

    return figs


def update_multi_metric_chart(chart, metrics, new_x):
    """
    Update chart DataFrame and figure for charts with multiple metrics.
    """
    if chart.df.empty:
        chart.df = pd.DataFrame(columns=pd.Index(["x"] + list(metrics.keys())))
    new_row = pd.DataFrame([{"x": new_x, **metrics}])
    # Only include non-empty DataFrames in concat to avoid FutureWarning
    if chart.df.empty:
        chart.df = new_row
    else:
        chart.df = pd.concat([chart.df, new_row], ignore_index=True).tail(50)
    chart.fig.data = []
    for key in metrics.keys():
        chart.fig.add_trace(
            go.Scatter(x=chart.df["x"], y=chart.df[key], mode="lines", name=key)
        )
    return chart.fig


def on_run(data):
    arguments = {}

    for component in data:
        component_id = component.elem_id
        if component_id:
            arguments[component_id] = data[component]

    try:
        video_output_path, constants, param_grid = prepare_video_and_constants(
            **arguments
        )
    except ValueError as e:
        raise gr.Error(
            f"Error: {str(e)}",
            duration=10,
        )

    recording_channels = arguments.get("recording_channels", 0) or 0
    inferencing_channels = arguments.get("inferencing_channels", 0) or 0
    live_preview_enabled = arguments.get("live_preview_enabled", False)
    # Validate channels
    if recording_channels + inferencing_channels == 0:
        raise gr.Error(
            "Please select at least one channel for recording or inferencing.",
            duration=10,
        )

    optimizer = PipelineOptimizer(
        pipeline=current_pipeline[0],
        constants=constants,
        param_grid=param_grid,
        channels=(recording_channels, inferencing_channels),
        elements=gst_inspector.get_elements(),
    )

    # If live preview is enabled, stream frames using a generator.
    # Otherwise, just run optimization (not a generator).
    if live_preview_enabled:
        # Show live preview, hide video player while streaming frames
        for live_frame in optimizer.run_with_live_preview():
            yield [
                gr.update(value=live_frame, visible=True),
                gr.update(visible=False),
                None,
            ]
    else:
        # Only show video player, never show live preview
        optimizer.run_without_live_preview()

    best_result = optimizer.evaluate()
    if best_result is None:
        best_result_message = "No valid result was returned by the optimizer."
    else:
        best_result_message = (
            f"Total FPS: {best_result.total_fps:.2f}, "
            f"Per Stream FPS: {best_result.per_stream_fps:.2f}"
        )

    # Hide live preview and show video player and best result message
    yield [
        gr.update(visible=False),
        gr.update(value=video_output_path, visible=True),
        best_result_message,
    ]


def on_benchmark(data):
    arguments = {}

    for component in data:
        component_id = component.elem_id
        if component_id:
            arguments[component_id] = data[component]

    try:
        _, constants, param_grid = prepare_video_and_constants(**arguments)
    except ValueError as e:
        raise gr.Error(
            f"Error: {str(e)}",
            duration=10,
        )

    # Enable Live Preview checkbox must not be taken into account for benchmarking
    param_grid["live_preview_enabled"] = [False]

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
    try:
        result = current_pipeline[1]["parameters"]["benchmark"]["result_format"]
    except KeyError:
        result = "Best Config: {s} streams ({ai} AI, {non_ai} non_AI) -> {fps:.2f} FPS"

    return result.format(s=s, ai=ai, non_ai=non_ai, fps=fps)


def on_stop():
    utils.cancelled = True
    logging.warning(f"utils.cancelled in on_stop: {utils.cancelled}")


def show_hide_component(component, config_key):
    component.unrender()
    try:
        if config_key:
            component.render()
    except KeyError:
        pass


def update_inferencing_channels_label():
    if current_pipeline[1]["parameters"]["run"]["recording_channels"]:
        return gr.update(
            minimum=0, value=8, label=RECORDING_AND_INFERENCING_CHANNELS_LABEL
        )
    return gr.update(minimum=1, value=8, label=INFERENCING_CHANNELS_LABEL)


# Create the interface
def create_interface(title: str = "Visual Pipeline and Platform Evaluation Tool"):
    """
    Components declarations starts here.
    Only components that are used in event handlers needs to be declared.
    Other components can be created directly in the Blocks context.
    """

    try:
        # Download the pipeline recording files
        for pipeline in PipelineLoader.list():
            pipeline_info = PipelineLoader.config(pipeline)
            download_file(
                pipeline_info["recording"]["url"],
                pipeline_info["recording"]["filename"],
            )
    except Exception as e:
        print(f"Error downloading pipeline recordings: {e}")

    # Video Player
    input_video_player = gr.Video(
        label="Input Video",
        interactive=True,
        show_download_button=True,
        sources="upload",
        elem_id="input_video_player",
    )

    output_video_player = gr.Video(
        label="Output Video (File)",
        interactive=False,
        show_download_button=True,
        elem_id="output_video_player",
        visible=True,
    )

    # Output Live Image (for live preview)
    output_live_image = gr.Image(
        label="Output Video (Live Preview)",
        interactive=False,
        show_download_button=False,
        elem_id="output_live_image",
        visible=False,
        type="numpy",
    )

    # Pipeline diagram image
    pipeline_image = gr.Image(
        value=str(current_pipeline[0].diagram()),
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
        maximum=64,
        value=8,
        step=1,
        label="Number of Recording + Inferencing channels",
        interactive=True,
        elem_id="inferencing_channels",
    )

    # Recording channels
    recording_channels = gr.Slider(
        minimum=0,
        maximum=64,
        value=8,
        step=1,
        label="Number of Recording only channels",
        interactive=True,
        elem_id="recording_channels",
    )

    # Tracking type
    tracking_type = gr.Dropdown(
        label="Object Tracking Type",
        choices=["short-term-imageless", "zero-term", "zero-term-imageless"],
        value="short-term-imageless",
        elem_id="tracking_type",
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

    # Select preferred device for inference
    # 1. If any discrete GPU, pick the one with the smallest gpu_id
    # 2. If any GPU, pick the one with the smallest gpu_id
    # 3. Else pick NPU
    # 4. Else pick CPU
    device_list = device_discovery.list_devices()
    # Find discrete GPUs
    discrete_gpus = [
        d
        for d in device_list
        if d.device_family == DeviceFamily.GPU and d.device_type == DeviceType.DISCRETE
    ]
    if discrete_gpus:
        # Pick discrete GPU with smallest gpu_id
        preferred_device = min(discrete_gpus, key=lambda d: d.gpu_id).device_name
    else:
        # Find any GPU
        gpus = [d for d in device_list if d.device_family == DeviceFamily.GPU]
        if gpus:
            # Pick GPU with smallest gpu_id
            preferred_device = min(gpus, key=lambda d: d.gpu_id).device_name
        else:
            # Find NPU
            npus = [d for d in device_list if d.device_family == DeviceFamily.NPU]
            if npus:
                # Pick first NPU
                preferred_device = npus[0].device_name
            else:
                # Default to CPU
                preferred_device = "CPU"

    # Get available devices for inference
    devices = [(device.full_device_name, device.device_name) for device in device_list]

    # Object detection model
    # Mapping of these choices to actual model path in utils.py
    object_detection_model = gr.Dropdown(
        label="Object Detection Model",
        choices=[
            "SSDLite MobileNet V2 (INT8)",
            "YOLO v5m 416x416 (INT8)",
            "YOLO v5s 416x416 (INT8)",
            "YOLO v5m 640x640 (INT8)",
            "YOLO v10s 640x640 (FP16)",
            "YOLO v10m 640x640 (FP16)",
            "YOLO v8 License Plate Detector (FP32)",
        ],
        value="YOLO v5s 416x416 (INT8)",
        elem_id="object_detection_model",
    )

    # Object detection device
    object_detection_device = gr.Dropdown(
        label="Object Detection Device",
        choices=devices,
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
        maximum=6,
        value=3,
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
    # Mapping of these choices to actual model path in utils.py
    object_classification_model = gr.Dropdown(
        label="Object Classification Model",
        choices=[
            "Disabled",
            "EfficientNet B0 (INT8)",
            "MobileNet V2 PyTorch (FP16)",
            "ResNet-50 TF (INT8)",
            "PaddleOCR (FP32)",
            "Vehicle Attributes Recognition Barrier 0039 (FP16)",
        ],
        value="ResNet-50 TF (INT8)",
        elem_id="object_classification_model",
    )

    # Object classification device
    object_classification_device = gr.Dropdown(
        label="Object Classification Device",
        choices=devices + ["Disabled"],
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
        maximum=6,
        value=3,
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

    pipeline_watermark_enabled = gr.Checkbox(
        label="Overlay inference results on inference channels",
        value=True,
        elem_id="pipeline_watermark_enabled",
    )

    pipeline_video_enabled = gr.Checkbox(
        label="Enable video output",
        value=True,
        elem_id="pipeline_video_enabled",
    )

    live_preview_enabled = gr.Checkbox(
        label="Enable Live Preview",
        value=False,
        elem_id="live_preview_enabled",
    )

    # Run button
    run_button = gr.Button("Run")

    # Benchmark button
    benchmark_button = gr.Button("Platform Ceiling Analysis")

    # Stop button
    stop_button = gr.Button("Stop", variant="stop", visible=False)

    # Metrics plots
    plots = [
        gr.Plot(
            value=charts[i].create_empty_fig(),
            label=charts[i].title,
            min_width=500,
            show_label=False,
        )
        for i in range(len(charts))
    ]

    # Timer for stream data
    timer = gr.Timer(1, active=False)

    pipeline_information = gr.Markdown(
        f"### {current_pipeline[1]['name']}\n{current_pipeline[1]['definition']}"
    )

    # Components Set
    components = set()
    components.add(input_video_player)
    components.add(output_video_player)
    components.add(output_live_image)
    components.add(pipeline_image)
    components.add(best_config_textbox)
    components.add(inferencing_channels)
    components.add(recording_channels)
    components.add(tracking_type)
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
    components.add(pipeline_watermark_enabled)
    components.add(pipeline_video_enabled)
    components.add(live_preview_enabled)

    # Interface layout
    with gr.Blocks(theme=theme, css=css_code, title=title) as demo:
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
                    gr.update(value=None),
                )  # Disable Run button  if input is empty, clears output
                if v is None or v == ""
                else (
                    gr.update(interactive=True),
                    gr.update(label="Input Video"),
                    gr.update(value=None),
                )
            ),
            inputs=input_video_player,
            outputs=[run_button, input_video_player, output_video_player],
            queue=False,
        )

        # Handle timer ticks
        timer.tick(
            generate_stream_data,
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
                [c.reset() for c in charts]
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
            # Execute the pipeline and stream live preview (if enabled)
            on_run,
            inputs=components,
            outputs=[output_live_image, output_video_player, best_config_textbox],
        ).then(
            # Stop the telemetry timer
            lambda: gr.update(active=False),
            inputs=None,
            outputs=timer,
        ).then(
            # Generate the persistent telemetry data
            generate_stream_data,
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
                [c.reset() for c in charts]
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
            generate_stream_data,
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
                                lambda: (
                                    f"### {current_pipeline[1]['name']}\n"
                                    f"{current_pipeline[1]['definition']}"
                                ),
                                None,
                                pipeline_information,
                            ).then(
                                lambda: current_pipeline[0].diagram(),
                                None,
                                pipeline_image,
                            ).then(
                                lambda: update_inferencing_channels_label(),
                                None,
                                inferencing_channels,
                            ).then(
                                lambda: [
                                    gr.Dropdown(
                                        choices=current_pipeline[1]["parameters"][
                                            "inference"
                                        ]["detection_models"],
                                        value=current_pipeline[1]["parameters"][
                                            "inference"
                                        ]["detection_model_default"],
                                    ),
                                    gr.Dropdown(
                                        choices=current_pipeline[1]["parameters"][
                                            "inference"
                                        ]["classification_models"],
                                        value=current_pipeline[1]["parameters"][
                                            "inference"
                                        ]["classification_model_default"],
                                    ),
                                ],
                                outputs=[
                                    object_detection_model,
                                    object_classification_model,
                                ],
                            ).then(
                                lambda: set_video_path(
                                    current_pipeline[1]["recording"]["filename"]
                                ),
                                None,
                                input_video_player,
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
                                    [c.reset() for c in charts]
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
            with gr.Tab("Run", id=1) as run_tab:
                # Main content
                with gr.Row():
                    # Left column
                    with gr.Column(scale=2, min_width=300):
                        # Render the pipeline information
                        pipeline_information.render()

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

                            # Output Video Player (file)
                            output_video_player.render()

                            # Output Live Image (for live preview)
                            output_live_image.render()

                        # Pipeline Parameters Accordion
                        with gr.Accordion("Pipeline Parameters", open=True):
                            # Inference Channels
                            inferencing_channels.render()

                            # Recording Channels
                            @gr.render(triggers=[run_tab.select])
                            def _():
                                show_hide_component(
                                    recording_channels,
                                    current_pipeline[1]["parameters"]["run"][
                                        "recording_channels"
                                    ],
                                )

                            # Render tracking_type dropdown
                            tracking_type.render()
                            # Whether to overlay result with watermarks
                            pipeline_watermark_enabled.render()
                            # Render live_preview_enabled checkbox
                            live_preview_enabled.render()

                            # Enable video output checkbox
                            @gr.render(triggers=[run_tab.select])
                            def _():
                                show_hide_component(
                                    pipeline_video_enabled,
                                    current_pipeline[1]["parameters"]["run"][
                                        "video_output_checkbox"
                                    ],
                                )

                        # Benchmark Parameters Accordion
                        with gr.Accordion(
                            "Platform Ceiling Analysis Parameters", open=False
                        ):
                            # FPS Floor
                            fps_floor.render()

                            # AI Stream Rate
                            @gr.render(triggers=[run_tab.select])
                            def _():
                                show_hide_component(
                                    ai_stream_rate,
                                    current_pipeline[1]["parameters"]["benchmark"][
                                        "ai_stream_rate"
                                    ],
                                )

                        # Inference Parameters Accordion
                        inference_accordion.render()
                        with inference_accordion:
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
