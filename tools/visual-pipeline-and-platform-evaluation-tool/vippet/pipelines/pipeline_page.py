import logging
import os
import sys
from datetime import datetime
from typing import List, Optional

import gradio as gr
import pandas as pd
import plotly.graph_objects as go
import requests

import utils
from benchmark import Benchmark
from chart import Chart, ChartType, create_charts
from device import DeviceDiscovery, DeviceFamily, DeviceType
from explore import GstInspector
from gstpipeline import PipelineLoader
from models import SupportedModelsManager
from optimize import PipelineOptimizer
from utils import prepare_video_and_constants

TEMP_DIR = "/tmp/"
METRICS_FILE_PATH = "/home/dlstreamer/vippet/.collector-signals/metrics.txt"
FPS_FILE_PATH = "/home/dlstreamer/vippet/.collector-signals/fps.txt"

INFERENCING_CHANNELS_LABEL = "Number of Inferencing channels"
RECORDING_AND_INFERENCING_CHANNELS_LABEL = "Number of Recording + Inferencing channels"


logging.getLogger("httpx").setLevel(logging.WARNING)

device_discovery = DeviceDiscovery()
gst_inspector = GstInspector()
charts: List[Chart] = create_charts(device_discovery.list_devices())

try:
    supported_models_manager = SupportedModelsManager()
except Exception as e:
    logging.error(str(e))
    sys.exit(1)


class Pipeline:
    def __init__(self, id: int, dir: str):
        self.id = id
        self.dir = dir
        self.gst_pipeline, self.config = PipelineLoader.load(dir)
        self.enabled = self.config.get("metadata", {}).get("enabled", False)
        self._create_gradio_components()

    def _create_gradio_components(self):
        """
        Components declarations starts here.
        Only components that are used in event handlers need to be declared.
        Other components can be created directly in the Blocks context.
        """

        try:
            # Download the pipeline recording files
            download_file(
                self.config["recording"]["url"],
                self.config["recording"]["filename"],
            )
            label = "Input Video"
            path = os.path.join(TEMP_DIR, self.config["recording"]["filename"])
        except Exception as e:
            print(f"Error downloading pipeline recordings: {e}")
            label = "Error: Video file not found. Verify the recording URL or proxy settings."
            path = None

        # Video Player
        self.input_video_player = gr.Video(
            label=label,
            value=path,
            interactive=True,
            show_download_button=True,
            sources="upload",
            elem_id="input_video_player",
        )

        self.output_video_player = gr.Video(
            label="Output Video (File)",
            interactive=False,
            show_download_button=True,
            elem_id="output_video_player",
            visible=True,
        )

        # Output Live Image (for live preview)
        self.output_live_image = gr.Image(
            label="Output Video (Live Preview)",
            interactive=False,
            show_download_button=False,
            elem_id="output_live_image",
            visible=False,
            type="numpy",
        )

        # Pipeline diagram image
        self.pipeline_image = gr.Image(
            value=str(self.gst_pipeline.diagram()),
            label="Pipeline Diagram",
            elem_id="pipeline_image",
            interactive=False,
            show_download_button=False,
            show_fullscreen_button=False,
        )

        # Best configuration textbox
        self.best_config_textbox = gr.Textbox(
            label="Best Configuration",
            interactive=False,
            lines=2,
            placeholder="The best configuration will appear here after benchmarking.",
            visible=True,
        )

        # Inferencing channels
        self.inferencing_channels = gr.Slider(
            minimum=1,
            maximum=64,
            value=8,
            step=1,
            label=INFERENCING_CHANNELS_LABEL,
            interactive=True,
            elem_id="inferencing_channels",
        )
        if self.config["parameters"]["run"]["recording_channels"]:
            self.inferencing_channels.minimum = 0
            self.inferencing_channels.label = RECORDING_AND_INFERENCING_CHANNELS_LABEL

        # Recording channels
        self.recording_channels = gr.Slider(
            minimum=0,
            maximum=64,
            value=8,
            step=1,
            label="Number of Recording only channels",
            interactive=True,
            elem_id="recording_channels",
        )

        # Tracking type
        self.tracking_type = gr.Dropdown(
            label="Object Tracking Type",
            choices=["short-term-imageless", "zero-term", "zero-term-imageless"],
            value="short-term-imageless",
            elem_id="tracking_type",
        )

        # FPS floor
        self.fps_floor = gr.Number(
            label="Set FPS Floor",
            value=30.0,  # Default value
            minimum=1.0,
            interactive=True,
            elem_id="fps_floor",
        )

        # AI stream rate
        self.ai_stream_rate = gr.Slider(
            label="AI Stream Rate (%)",
            value=20,  # Default value
            minimum=0,
            maximum=100,
            step=1,
            interactive=True,
            elem_id="ai_stream_rate",
        )

        # Inference accordion
        self.inference_accordion = gr.Accordion("Inference Parameters", open=True)

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
            if d.device_family == DeviceFamily.GPU
            and d.device_type == DeviceType.DISCRETE
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
        devices = [
            (device.full_device_name, device.device_name) for device in device_list
        ]

        # Object detection model
        # Mapping of these choices to actual model path in utils.py
        self.object_detection_model = gr.Dropdown(
            label="Object Detection Model",
            elem_id="object_detection_model",
            # choices and value will be set for each pipeline later
        )

        # Object detection device
        self.object_detection_device = gr.Dropdown(
            label="Object Detection Device",
            choices=devices,
            value=preferred_device,
            elem_id="object_detection_device",
        )

        # Object detection batch size
        self.object_detection_batch_size = gr.Slider(
            minimum=0,
            maximum=32,
            value=0,
            step=1,
            label="Object Detection Batch Size",
            interactive=True,
            elem_id="object_detection_batch_size",
        )

        # Object detection inference interval
        self.object_detection_inference_interval = gr.Slider(
            minimum=1,
            maximum=6,
            value=3,
            step=1,
            label="Object Detection Inference Interval",
            interactive=True,
            elem_id="object_detection_inference_interval",
        )

        # Object Detection number of inference requests (nireq)
        self.object_detection_nireq = gr.Slider(
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
        self.object_classification_model = gr.Dropdown(
            label="Object Classification Model",
            elem_id="object_classification_model",
            # choices and value will be set for each pipeline later
        )

        # Object classification device
        self.object_classification_device = gr.Dropdown(
            label="Object Classification Device",
            choices=devices + ["Disabled"],
            value=preferred_device,
            elem_id="object_classification_device",
        )

        # Object classification batch size
        self.object_classification_batch_size = gr.Slider(
            minimum=0,
            maximum=32,
            value=0,
            step=1,
            label="Object Classification Batch Size",
            interactive=True,
            elem_id="object_classification_batch_size",
        )

        # Object classification inference interval
        self.object_classification_inference_interval = gr.Slider(
            minimum=1,
            maximum=6,
            value=3,
            step=1,
            label="Object Classification Inference Interval",
            interactive=True,
            elem_id="object_classification_inference_interval",
        )

        # Object classification number of inference requests (nireq)
        self.object_classification_nireq = gr.Slider(
            minimum=0,
            maximum=4,
            value=0,
            step=1,
            label="Object Classification Number of Inference Requests (nireq)",
            interactive=True,
            elem_id="object_classification_nireq",
        )

        # Object classification reclassify interval
        self.object_classification_reclassify_interval = gr.Slider(
            minimum=0,
            maximum=5,
            value=1,
            step=1,
            label="Object Classification Reclassification Interval",
            interactive=True,
            elem_id="object_classification_reclassify_interval",
        )

        self.pipeline_watermark_enabled = gr.Checkbox(
            label="Overlay inference results on inference channels",
            value=True,
            elem_id="pipeline_watermark_enabled",
        )

        self.pipeline_video_enabled = gr.Checkbox(
            label="Enable video output",
            value=True,
            elem_id="pipeline_video_enabled",
        )

        self.live_preview_enabled = gr.Checkbox(
            label="Enable Live Preview",
            value=False,
            elem_id="live_preview_enabled",
        )

        # Run button
        self.run_button = gr.Button("Run")

        # Benchmark button
        self.benchmark_button = gr.Button("Platform Ceiling Analysis")

        # Stop button
        self.stop_button = gr.Button("Stop", variant="stop", visible=False)

        # Metrics plots
        self.plots = [
            gr.Plot(
                value=charts[i].create_empty_fig(),
                label=charts[i].title,
                min_width=500,
                show_label=False,
            )
            for i in range(len(charts))
        ]

        # Timer for stream data
        self.timer = gr.Timer(1, active=False)

        self.pipeline_information = gr.Markdown(
            f"### {self.config['name']}\n{self.config['definition']}"
        )

        # Components Set
        self.components = set()
        self.components.add(self.input_video_player)
        self.components.add(self.output_video_player)
        self.components.add(self.output_live_image)
        self.components.add(self.pipeline_image)
        self.components.add(self.best_config_textbox)
        self.components.add(self.inferencing_channels)
        self.components.add(self.tracking_type)
        self.components.add(self.fps_floor)
        self.components.add(self.object_detection_model)
        self.components.add(self.object_detection_device)
        self.components.add(self.object_detection_batch_size)
        self.components.add(self.object_detection_inference_interval)
        self.components.add(self.object_detection_nireq)
        self.components.add(self.object_classification_model)
        self.components.add(self.object_classification_device)
        self.components.add(self.object_classification_batch_size)
        self.components.add(self.object_classification_inference_interval)
        self.components.add(self.object_classification_nireq)
        self.components.add(self.object_classification_reclassify_interval)
        self.components.add(self.pipeline_watermark_enabled)
        self.components.add(self.live_preview_enabled)
        if self.config["parameters"]["run"]["recording_channels"]:
            self.components.add(self.recording_channels)
        if self.config["parameters"]["run"]["video_output_checkbox"]:
            self.components.add(self.pipeline_video_enabled)
        if self.config["parameters"]["benchmark"]["ai_stream_rate"]:
            self.components.add(self.ai_stream_rate)

    def tab(self) -> gr.Blocks:
        with gr.Blocks() as page:
            """
            Component event handlers and interactions are defined here.
            """

            page.load(
                # Read supported models and update the model dropdowns every time a new pipeline is selected
                # (list of models may change)
                lambda: [
                    *(
                        lambda det, cls: [
                            gr.Dropdown(
                                choices=det[0],
                                value=det[1],
                            ),
                            gr.Dropdown(
                                choices=cls[0],
                                value=cls[1],
                            ),
                        ]
                    )(
                        supported_models_manager.filter_detection_models(
                            self.config["parameters"]["inference"]["detection_models"],
                            self.config["parameters"]["inference"][
                                "detection_model_default"
                            ],
                        ),
                        supported_models_manager.filter_classification_models(
                            self.config["parameters"]["inference"][
                                "classification_models"
                            ],
                            self.config["parameters"]["inference"][
                                "classification_model_default"
                            ],
                        ),
                    )
                ],
                outputs=[
                    self.object_detection_model,
                    self.object_classification_model,
                ],
            )

            # Handle click on the pipeline image
            self.pipeline_image.select(
                self._detect_click,
                None,
                [self.inference_accordion],
            )

            # Handle changes on the input video player
            self.input_video_player.change(
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
                inputs=self.input_video_player,
                outputs=[
                    self.run_button,
                    self.input_video_player,
                    self.output_video_player,
                ],
                queue=False,
            )

            # Handle timer ticks
            self.timer.tick(
                generate_stream_data,
                outputs=self.plots,
            )

            # Handle run button clicks
            self.run_button.click(
                # Update the state of the buttons
                lambda: [
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=True),
                ],
                outputs=[self.run_button, self.benchmark_button, self.stop_button],
                queue=True,
            ).then(
                # Reset the telemetry plots
                lambda: (
                    [c.reset() for c in charts]
                    or [
                        self.plots[i].value.update(data=[])
                        for i in range(len(self.plots))
                        if hasattr(self.plots[i], "value")
                        and self.plots[i].value is not None
                    ]
                    or self.plots
                ),
                outputs=self.plots,
            ).then(
                # Start the telemetry timer
                lambda: gr.update(active=True),
                inputs=None,
                outputs=self.timer,
            ).then(
                # Execute the pipeline and stream live preview (if enabled)
                self._on_run,
                inputs=self.components,
                outputs=[
                    self.output_live_image,
                    self.output_video_player,
                    self.best_config_textbox,
                ],
            ).then(
                # Stop the telemetry timer
                lambda: gr.update(active=False),
                inputs=None,
                outputs=self.timer,
            ).then(
                # Generate the persistent telemetry data
                generate_stream_data,
                inputs=None,
                outputs=self.plots,
            ).then(
                # Update the visibility of the buttons
                lambda: [
                    gr.update(visible=True),
                    gr.update(visible=True),
                    gr.update(visible=False),
                ],
                outputs=[self.run_button, self.benchmark_button, self.stop_button],
            )

            # Handle benchmark button clicks
            self.benchmark_button.click(
                # Update the state of the buttons
                lambda: [
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=True),
                ],
                outputs=[self.run_button, self.benchmark_button, self.stop_button],
                queue=False,
            ).then(
                # Clear output components here
                lambda: [
                    gr.update(value=""),
                    gr.update(value=None),
                ],
                None,
                [self.best_config_textbox, self.output_video_player],
            ).then(
                # Reset the telemetry plots
                lambda: (
                    [c.reset() for c in charts]
                    or [
                        self.plots[i].value.update(data=[])
                        for i in range(len(self.plots))
                        if hasattr(self.plots[i], "value")
                        and self.plots[i].value is not None
                    ]
                    or self.plots
                ),
                outputs=self.plots,
            ).then(
                # Start the telemetry timer
                lambda: gr.update(active=True),
                inputs=None,
                outputs=self.timer,
            ).then(
                # Execute the benchmark
                self._on_benchmark,
                inputs=self.components,
                outputs=[self.best_config_textbox],
            ).then(
                # Stop the telemetry timer
                lambda: gr.update(active=False),
                inputs=None,
                outputs=self.timer,
            ).then(
                # Generate the persistent telemetry data
                generate_stream_data,
                inputs=None,
                outputs=self.plots,
            ).then(
                # Reset the state of the buttons
                lambda: [
                    gr.update(visible=True),
                    gr.update(visible=True),
                    gr.update(visible=False),
                ],
                outputs=[self.run_button, self.benchmark_button, self.stop_button],
            )

            # Handle stop button clicks
            self.stop_button.click(
                # Execute the stop function
                on_stop,
            ).then(
                # Reset the state of the buttons
                lambda: [
                    gr.update(visible=True),
                    gr.update(visible=True),
                    gr.update(visible=False),
                ],
                outputs=[self.run_button, self.benchmark_button, self.stop_button],
                queue=False,
            )

            """
            Components rendering starts here.
            """

            # Main content
            with gr.Row():
                # Left column
                with gr.Column(scale=2, min_width=300):
                    # Render the pipeline information
                    self.pipeline_information.render()

                    # Render pipeline image
                    self.pipeline_image.render()

                    # Render the run button
                    self.run_button.render()

                    # Render the benchmark button
                    self.benchmark_button.render()

                    # Render the stop button
                    self.stop_button.render()

                    # Render the best configuration textbox
                    self.best_config_textbox.render()

                    # Metrics plots
                    with gr.Row():
                        # Render plots
                        for i in range(len(self.plots)):
                            self.plots[i].render()

                        # Render the timer
                        self.timer.render()

                # Right column
                with gr.Column(scale=1, min_width=150):
                    # Video Player Accordion
                    with gr.Accordion("Video Player", open=True):
                        # Input Video Player
                        self.input_video_player.render()

                        # Output Video Player (file)
                        self.output_video_player.render()

                        # Output Live Image (for live preview)
                        self.output_live_image.render()

                    # Pipeline Parameters Accordion
                    with gr.Accordion("Pipeline Parameters", open=True):
                        # Inference Channels
                        self.inferencing_channels.render()

                        # Recording Channels
                        if self.config["parameters"]["run"]["recording_channels"]:
                            self.recording_channels.render()

                        # Render tracking_type dropdown
                        self.tracking_type.render()
                        # Whether to overlay result with watermarks
                        self.pipeline_watermark_enabled.render()
                        # Render live_preview_enabled checkbox
                        self.live_preview_enabled.render()

                        # Enable video output checkbox
                        if self.config["parameters"]["run"]["video_output_checkbox"]:
                            self.pipeline_video_enabled.render()

                    # Benchmark Parameters Accordion
                    with gr.Accordion(
                        "Platform Ceiling Analysis Parameters", open=False
                    ):
                        # FPS Floor
                        self.fps_floor.render()

                        # AI Stream Rate
                        if self.config["parameters"]["benchmark"]["ai_stream_rate"]:
                            self.ai_stream_rate.render()

                    # Inference Parameters Accordion
                    self.inference_accordion.render()
                    with self.inference_accordion:
                        # Object Detection Parameters
                        self.object_detection_model.render()
                        self.object_detection_device.render()
                        self.object_detection_batch_size.render()
                        self.object_detection_inference_interval.render()
                        self.object_detection_nireq.render()

                        # Object Classification Parameters
                        self.object_classification_model.render()
                        self.object_classification_device.render()
                        self.object_classification_batch_size.render()
                        self.object_classification_inference_interval.render()
                        self.object_classification_nireq.render()
                        self.object_classification_reclassify_interval.render()

        return page

    # Function to check if a click is inside any bounding box
    def _detect_click(self, evt: gr.SelectData):
        x, y = evt.index

        for (
            x_min,
            y_min,
            x_max,
            y_max,
            label,
            description,
        ) in self.gst_pipeline.bounding_boxes():
            if x_min <= x <= x_max and y_min <= y <= y_max:
                match label:
                    case "Inference":
                        return gr.update(open=True)

        return gr.update(open=False)

    def _on_run(self, data):
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
            pipeline=self.gst_pipeline,
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

    def _on_benchmark(self, data):
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
            pipeline_cls=self.gst_pipeline,
            fps_floor=arguments["fps_floor"],
            rate=arguments.get("ai_stream_rate"),
            parameters=param_grid,
            constants=constants,
            elements=gst_inspector.get_elements(),
        )

        # Run the benchmark
        s, ai, non_ai, fps = bm.run()

        # Return results
        try:
            result = self.config["parameters"]["benchmark"]["result_format"]
        except KeyError:
            result = (
                "Best Config: {s} streams ({ai} AI, {non_ai} non_AI) -> {fps:.2f} FPS"
            )

        return result.format(s=s, ai=ai, non_ai=non_ai, fps=fps)


def download_file(url, local_filename):
    # Send a GET request to the URL
    with requests.get(url, stream=True) as response:
        response.raise_for_status()  # Check if the request was successful
        # Open a local file with write-binary mode
        with open(os.path.join(TEMP_DIR, local_filename), "wb") as file:
            # Iterate over the response content in chunks
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)  # Write each chunk to the local file


def on_stop():
    utils.cancelled = True
    logging.warning(f"utils.cancelled in on_stop: {utils.cancelled}")


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
