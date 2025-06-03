import requests
import logging

import gradio as gr
import pandas as pd
import plotly.graph_objects as go

from datetime import datetime
from optimize import OptimizationResult, PipelineOptimizer
from pipeline import SmartNVRPipeline, Transportation2Pipeline

from device import DeviceDiscovery
from explore import GstInspector
from benchmark import Benchmark
from utils import prepare_video_and_constants
import utils

logging.getLogger("httpx").setLevel(logging.WARNING)

css_code = """

.spark-header {
  margin: 0px;
  padding: 0px;
  background: #0054ae;
  height:60px;
}

.spark-logo {
  margin-left: 20px;
  margin-right: 20px;
  width: 60px;
  height: 60px;
  float: left;
}

.spark-title {
  height: 60px;
  line-height: 60px;
  float: left;
  color:white;
  font-size: 24px;
  font-color: white;
}

.html-container {
  padding: 0;
}

.header {
  margin: 0px;
  padding: 10px;
  background: #0054ae;
  color: white;
  font-size: 24px;
  font-color: white;
}

.spark-footer {
  background: #0054ae;
  height:40px;
  justify-content: center;
  align-items: center;
}

.spark-footer-info {
  margin-left: auto; margin-right: auto;
  height: 40px;
  line-height: 40px;
  color:white;
  font-size: 18px;
  font-color: white;
  text-align: center;
}

footer {display:none !important}

#results_plot {
    height: 330px;
}

#pipeline_image img{
    cursor: pointer !important;
    padding: 40px;
}

"""


theme = gr.themes.Default(
    primary_hue="blue",
    font=[gr.themes.GoogleFont("Montserrat"), "ui-sans-serif", "sans-serif"],
)

# pipeline = Transportation2Pipeline()
pipeline = SmartNVRPipeline()
device_discovery = DeviceDiscovery()
gst_inspector = GstInspector()

# Download File
def download_file(url, local_filename):
    # Send a GET request to the URL
    with requests.get(url, stream=True) as response:
        response.raise_for_status()  # Check if the request was successful
        # Open a local file with write-binary mode
        with open(local_filename, 'wb') as file:
            # Iterate over the response content in chunks
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)  # Write each chunk to the local file


# This elements are not used in the current version of the app
# # Function to check if a click is inside any bounding box
# def detect_click(evt: gr.SelectData):
#     x, y = evt.index

#     for x_min, y_min, x_max, y_max, label, description in pipeline.bounding_boxes():
#         if x_min <= x <= x_max and y_min <= y <= y_max:

#             match label:
#                 case "Object Detection":
#                     return gr.update(open=True), gr.update(open=False)
#                 case "Object Classification":
#                     return gr.update(open=False), gr.update(open=True)

#     return gr.update(open=False), gr.update(open=False)


# Function to check if a click is inside any bounding box
def detect_click(evt: gr.SelectData):
    x, y = evt.index

    for x_min, y_min, x_max, y_max, label, description in pipeline.bounding_boxes():
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
    "GPU Compute Engine Utilization [%]"
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
    "Utilization"
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
            line for line in lines
            if line.split() and line.split()[-1].isdigit()
            and abs(int(line.split()[-1]) - target_ns) < 1e9  
        ]
        lines = surrounding_lines if surrounding_lines else []
  


    cpu_user = mem_used_percent = gpu_package_power = core_temp = gpu_power = None
    gpu_freq = cpu_freq = gpu_render = gpu_ve = gpu_video = gpu_copy =  gpu_compute = None

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
        
        if all(v is not None for v in [
            cpu_user, mem_used_percent, gpu_package_power, core_temp, gpu_power,
            gpu_freq, gpu_render, gpu_ve, gpu_video, gpu_copy, cpu_freq, gpu_compute]):
            break

    return [
        cpu_user, mem_used_percent, gpu_package_power, core_temp, gpu_power,
        gpu_freq, gpu_render, gpu_ve, gpu_video, gpu_copy, cpu_freq, gpu_compute
    ]


def create_empty_fig(title, y_axis_label):
    fig = go.Figure()
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title=y_axis_label
    )
    return fig


# Store figures globally
figs = [
    create_empty_fig(chart_titles[i], y_labels[i])
    for i in range(len(chart_titles))
]


def generate_stream_data(i, timestamp_ns=None):
    new_x = datetime.now() if timestamp_ns is None else datetime.fromtimestamp(timestamp_ns / 1e9)

    new_y = 0
    (
        cpu_val, mem_val, gpu_package_power, core_temp, gpu_power, 
        gpu_freq, gpu_render, gpu_ve, gpu_video, gpu_copy, cpu_freq, gpu_compute
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
    elif title ==  "CPU Temperature [C°]" and core_temp is not None:
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
        [stream_dfs[i] if not stream_dfs[i].empty else None, new_row], 
        ignore_index=True
    ).tail(50)

    fig = figs[i]
    fig.data = []  # clear previous trace
    fig.add_trace(go.Scatter(x=stream_dfs[i]["x"], y=stream_dfs[i]["y"], mode="lines"))

    return fig

# Create the interface
def create_interface():

    # Video Player
    input_video_player = None

    try:
        download_file(
            "https://github.com/intel-iot-devkit/sample-videos/raw/master/person-bicycle-car-detection.mp4",
            "/tmp/person-bicycle-car-detection.mp4"
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
        value=pipeline.diagram(),
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

    # Pipeline parameters accordion
    pipeline_parameters_accordion = gr.Accordion("Pipeline Parameters", open=True)

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
    benchmark_parameters_accordion = gr.Accordion("Benchmark Parameters", open=True)
    # FPS floor
    fps_floor = gr.Number(
        label="Set FPS Floor",
        value=30.0,  # Default value
        minimum=1.0,
        interactive=True
    )

    rate = gr.Slider(
        label="AI Stream Rate (%)",
        value=20,  # Default value
        minimum=0,
        maximum=100,
        step=1,
        interactive=True
    )

    # Object detection accordion
    object_detection_accordion = gr.Accordion("Object Detection Parameters", open=True)

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
    device_choices = [
        (device.full_device_name, device.device_name)
        for device in device_discovery.list_devices()
    ]
    preferred_device = next(
        ( "GPU" for device_name in device_choices if "GPU" in device_name),
        ( "CPU" ),
    )
    object_detection_device = gr.Dropdown(
        label="Object Detection Device",
        choices=device_choices,
        value=preferred_device,
    )

    # Batch size
    batch_size = gr.Slider(
        minimum=0,
        maximum=32,
        value=0,
        step=1,
        label="Batch Size",
        interactive=True,
    )

    # Inference interval
    inference_interval = gr.Slider(
        minimum=1,
        maximum=5,
        value=1,
        step=1,
        label="Inference Interval",
        interactive=True,
    )

    # Number of inference requests (nireq)
    nireq = gr.Slider(
        minimum=0,
        maximum=4,
        value=0,
        step=1,
        label="Number of Inference Requests (nireq)",
        interactive=True,
    )

    # This elements are not used in the current version of the app
    # # Object classification accordion
    # object_classification_accordion = gr.Accordion(
    #     "Object Classification Parameters", open=False
    # )

    # # Object classification model
    # object_classification_model = gr.Dropdown(
    #     label="Object Classification Model",
    #     choices=[
    #         "ResNet-50 TF",
    #         "EfficientNet B0",
    #         "Vehicle Attributes Recognition Barrier",
    #     ],
    #     value="Vehicle Attributes Recognition Barrier",
    # )

    # # Object classification device
    # object_classification_device = gr.Dropdown(
    #     label="Object Classification Device",
    #     choices=[
    #         "CPU",
    #         "GPU",
    #     ],
    #     value="CPU",
    # )

    # Run button
    run_button = gr.Button("Run")

    # Add a Benchmark button
    benchmark_button = gr.Button("Benchmark")

    # Add a Stop button
    stop_button = gr.Button("Stop", variant="stop",visible=False)

    # Interface layout
    with gr.Blocks(theme=theme, css=css_code) as demo:

        header = gr.HTML(
            "<div class='spark-header'>"
            "  <img src='https://www.intel.com/content/dam/logos/intel-header-logo.svg' class='spark-logo'></img>"
            "  <div class='spark-title'>Visual Pipeline and Platform Evaluation Tool (ViPPET)</div>"
            "</div>"
        )

        with gr.Row():
            with gr.Column(scale=2, min_width=300):
                pipeline_image.render()

                # Click event handling
                pipeline_image.select(
                    detect_click,
                    None,
                    # [object_detection_accordion, object_classification_accordion],
                    [object_detection_accordion],
                )
                run_button.render()
                benchmark_button.render()
                stop_button.render()  
                best_config_textbox.render()

                # Metrics plots
                with gr.Row():
                    plots = [
                        gr.Plot(
                            value=create_empty_fig(chart_titles[i], y_labels[i]), label=chart_titles[i],
                            min_width=500,
                            show_label=False,
                        )
                        for i in range(len(chart_titles))
                    ]
                    timer = gr.Timer(1, active=False)
                    def update_all_plots():
                        return [generate_stream_data(i) for i in range(len(chart_titles))]

                    timer.tick(update_all_plots, outputs=plots)

                def on_run(
                    recording_channels,
                    inferencing_channels,
                    object_detection_model,
                    object_detection_device,
                    # This elements are not used in the current version of the app
                    # object_classification_model,
                    # object_classification_device,
                    batch_size,
                    inference_interval,
                    nireq,
                    input_video_player,
                ):
                    global stream_dfs
                    stream_dfs = [pd.DataFrame(columns=["x", "y"]) for _ in range(len(chart_titles))]  # Reset all data
                    gr.update(active=True)

                    # Reset the FPS file
                    with open("/home/dlstreamer/vippet/.collector-signals/fps.txt", "w") as f:
                        f.write(f"0.0\n")

                    video_output_path, constants, param_grid = prepare_video_and_constants(
                        input_video_player,
                        object_detection_model,
                        object_detection_device,
                        batch_size,
                        nireq,
                        inference_interval,
                    )
             
                    # This elements are not used in the current version of the app
                    # match object_classification_model:
                    #     case "ResNet-50 TF":
                    #         constants["VEHICLE_CLASSIFICATION_MODEL_PATH"] = (
                    #             f"{MODELS_PATH}/pipeline-zoo-models/resnet-50-tf_INT8/resnet-50-tf_i8.xml"
                    #         )
                    #         constants["VEHICLE_CLASSIFICATION_MODEL_PROC"] = (
                    #             f"{MODELS_PATH}/pipeline-zoo-models/resnet-50-tf_INT8/resnet-50-tf_i8.json"
                    #         )
                    #     case "EfficientNet B0":
                    #         constants["VEHICLE_CLASSIFICATION_MODEL_PATH"] = (
                    #             f"{MODELS_PATH}/pipeline-zoo-models/efficientnet-b0_INT8/FP16-INT8/efficientnet-b0.xml"
                    #         )
                    #         constants["VEHICLE_CLASSIFICATION_MODEL_PROC"] = (
                    #             f"{MODELS_PATH}/pipeline-zoo-models/efficientnet-b0_INT8/efficientnet-b0.json"
                    #         )
                    #     case _:
                    #         raise ValueError("Unrecognized Object Classification Model")

                    # Validate channels
                    if recording_channels + inferencing_channels == 0:
                        raise gr.Error("Please select at least one channel for recording or inferencing.", duration=10)

                    optimizer = PipelineOptimizer(
                        pipeline=pipeline,
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

                    plot_updates = [generate_stream_data(i) for i in range(len(chart_titles))]

                    return [video_output_path] + plot_updates + [best_result_message]

                def on_benchmark(
                    fps_floor,
                    rate,
                    object_detection_model,
                    object_detection_device,
                    batch_size,
                    inference_interval,
                    nireq,
                    input_video_player,
                ):
                    
                    _, constants, param_grid = prepare_video_and_constants(
                        input_video_player,
                        object_detection_model,
                        object_detection_device,
                        batch_size,
                        nireq,
                        inference_interval,
                    )

                    # Initialize the benchmark class
                    bm = Benchmark(
                        video_path=input_video_player,
                        pipeline_cls=pipeline,
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
                    logging.warning(f"utils.cancelled in on_stop: {utils.cancelled}")  # This will appear in docker logs
                    return [
                        gr.update(visible=True),   # run_button
                        gr.update(visible=True),   # benchmark_button
                        gr.update(visible=False),  # stop_button
                    ]

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
                def on_run_click(*args):
                    # Hide Run and Benchmark, show Stop
                    return [
                        gr.update(visible=False),  # run_button
                        gr.update(visible=False),  # benchmark_button
                        gr.update(visible=True)    # stop_button
                    ]

                run_button.click(
                    on_run_click,
                    outputs=[run_button, benchmark_button, stop_button],
                    queue=True,
                ).then(
                    lambda: (
                        globals().update(
                            stream_dfs=[pd.DataFrame(columns=["x", "y"]) for _ in range(len(chart_titles))]
                        )
                        or [
                            plots[i].value.update(data=[])  # Clear data, keep layout
                            for i in range(len(chart_titles))
                        ]
                        or plots  # Return updated plot objects
                    ),
                    outputs=plots
                ).then(
                    lambda: gr.update(active=True),  # This updates the same timer
                    inputs=None,
                    outputs=timer,
                ).then(
                    on_run,
                    inputs=[
                        recording_channels,
                        inferencing_channels,
                        object_detection_model,
                        object_detection_device,
                        # This elements are not used in the current version of the app
                        # object_classification_model,
                        # object_classification_device,
                        batch_size,
                        inference_interval,
                        nireq,
                        input_video_player,
                    ],
                    outputs=[output_video_player] + plots + [best_config_textbox],
                ).then(
                    lambda: gr.update(active=False),  # This updates the same timer
                    inputs=None,
                    outputs=timer,
                ).then(
                    lambda: [
                        gr.update(visible=True),   # run_button
                        gr.update(visible=True),   # benchmark_button
                        gr.update(visible=False),  # stop_button
                    ],
                    outputs=[run_button, benchmark_button, stop_button],
                )

                benchmark_button.click(
                    on_run_click,
                    outputs=[run_button, benchmark_button, stop_button],
                    queue=False,
                ).then(
                    on_benchmark,
                    inputs=[
                        fps_floor,
                        rate,
                        object_detection_model,
                        object_detection_device,
                        batch_size,
                        inference_interval,
                        nireq,
                        input_video_player,
                    ],
                    outputs=[best_config_textbox],  
                ).then(
                    lambda: [
                        gr.update(visible=True),   # run_button
                        gr.update(visible=True),   # benchmark_button
                        gr.update(visible=False),  # stop_button
                    ],
                    outputs=[run_button, benchmark_button, stop_button],
                )

                stop_button.click(
                    on_stop,
                    outputs=[run_button, benchmark_button, stop_button],  # Remove gr.Info
                    queue=False,
                ) 

            with gr.Column(scale=1, min_width=150):
                with gr.Accordion("Video Player", open=True):
                    input_video_player.render()
                    output_video_player.render()

                with pipeline_parameters_accordion.render():
                    inferencing_channels.render()
                    recording_channels.render()

                with benchmark_parameters_accordion.render():
                    fps_floor.render()
                    rate.render()
                
                with object_detection_accordion.render():
                    object_detection_model.render()
                    object_detection_device.render()
                    batch_size.render()
                    inference_interval.render()
                    nireq.render()

                # This elements are not used in the current version of the app
                # with object_classification_accordion.render():
                #     object_classification_model.render()
                #     object_classification_device.render()

        footer = gr.HTML(
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
