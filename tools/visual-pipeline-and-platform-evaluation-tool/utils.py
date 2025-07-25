import subprocess
import re
import time
import os
import random
import string
from typing import List, Dict, Tuple
from subprocess import Popen, PIPE
import psutil as ps
from itertools import product
import logging
from pipeline import GstPipeline
import select



cancelled = False


def prepare_video_and_constants(
    **kwargs: dict[str, any],
):
    """
    Prepares the video output path, constants, and parameter grid for the pipeline.

    Args:
        input_video_player (str): Path to the input video.
        object_detection_model (str): Selected object detection model.
        object_detection_device (str): Selected object detection device.

    Returns:
        tuple: A tuple containing video_output_path, constants, and param_grid.
    """

    # Collect parameters from kwargs
    input_video_player = kwargs.get("input_video_player", "")
    object_detection_model = kwargs.get("object_detection_model", "")
    object_detection_device = kwargs.get("object_detection_device", "")
    object_detection_batch_size = kwargs.get("object_detection_batch_size", 1)
    object_detection_inference_interval = kwargs.get(
        "object_detection_inference_interval", 0.0
    )
    object_detection_nireq = kwargs.get("object_detection_nireq", 1)
    object_classification_model = kwargs.get("object_classification_model", "")
    object_classification_device = kwargs.get("object_classification_device", "")
    object_classification_batch_size = kwargs.get("object_classification_batch_size", 1)
    object_classification_inference_interval = kwargs.get(
        "object_classification_inference_interval", 0.0
    )
    object_classification_reclassify_interval = kwargs.get(
        "object_classification_reclassify_interval", 0.0
    )
    object_classification_nireq = kwargs.get("object_classification_nireq", 1)
    pipeline_watermark_enabled = kwargs.get("pipeline_watermark_enabled", True)
    pipeline_video_enabled = kwargs.get("pipeline_video_enabled", True)

    random_string = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    video_output_path = input_video_player.replace(
        ".mp4", f"-output-{random_string}.mp4"
    )
    # Delete the video in the output folder before producing a new one
    # Otherwise, gstreamer will just save a few seconds of the video
    # and stop.
    if os.path.exists(video_output_path):
        os.remove(video_output_path)

    # Reset the FPS file
    with open("/home/dlstreamer/vippet/.collector-signals/fps.txt", "w") as f:
        f.write(f"0.0\n")

    param_grid = {
        "object_detection_device": object_detection_device.split(", "),
        "object_detection_batch_size": [object_detection_batch_size],
        "object_detection_inference_interval": [object_detection_inference_interval],
        "object_detection_nireq": [object_detection_nireq],
        "object_classification_device": object_classification_device.split(", "),
        "object_classification_batch_size": [object_classification_batch_size],
        "object_classification_inference_interval": [object_classification_inference_interval],
        "object_classification_reclassify_interval": [object_classification_reclassify_interval],
        "object_classification_nireq": [object_classification_nireq],
        "pipeline_watermark_enabled": [pipeline_watermark_enabled],
        "pipeline_video_enabled": [pipeline_video_enabled],
    }

    constants = {
        "VIDEO_PATH": input_video_player,
        "VIDEO_OUTPUT_PATH": video_output_path,
    }

    MODELS_PATH = "/home/dlstreamer/vippet/models"

    match object_detection_model:
        case "SSDLite MobileNet V2 (INT8)":
            constants["OBJECT_DETECTION_MODEL_PATH"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/ssdlite_mobilenet_v2_INT8/FP16-INT8/ssdlite_mobilenet_v2.xml"
            )
            constants["OBJECT_DETECTION_MODEL_PROC"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/ssdlite_mobilenet_v2_INT8/ssdlite_mobilenet_v2.json"
            )
        case "YOLO v5m 416x416 (INT8)":
            constants["OBJECT_DETECTION_MODEL_PATH"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/yolov5m-416_INT8/FP16-INT8/yolov5m-416_INT8.xml"
            )
            constants["OBJECT_DETECTION_MODEL_PROC"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/yolov5m-416_INT8/yolo-v5.json"
            )
        case "YOLO v5m 640x640 (INT8)":
            constants["OBJECT_DETECTION_MODEL_PATH"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/yolov5m-640_INT8/FP16-INT8/yolov5m-640_INT8.xml"
            )
            constants["OBJECT_DETECTION_MODEL_PROC"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/yolov5m-640_INT8/yolo-v5.json"
            )
        case "YOLO v5s 416x416 (INT8)":
            constants["OBJECT_DETECTION_MODEL_PATH"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/yolov5s-416_INT8/FP16-INT8/yolov5s.xml"
            )
            constants["OBJECT_DETECTION_MODEL_PROC"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/yolov5s-416_INT8/yolo-v5.json"
            )
        case "YOLO v10s 640x640 (FP16)":
            if object_detection_device == "NPU":
                raise ValueError(
                    "YOLO v10s model is not supported on NPU device. Please select another model."
                )

            constants["OBJECT_DETECTION_MODEL_PATH"] = (
                f"{MODELS_PATH}/public/yolov10s/FP16/yolov10s.xml"
            )
            constants["OBJECT_DETECTION_MODEL_PROC"] = None
        case "YOLO v10m 640x640 (FP16)":
            if object_detection_device == "NPU":
                raise ValueError(
                    "YOLO v10m model is not supported on NPU device. Please select another model."
                )

            constants["OBJECT_DETECTION_MODEL_PATH"] = (
                f"{MODELS_PATH}/public/yolov10m/FP16/yolov10m.xml"
            )
            constants["OBJECT_DETECTION_MODEL_PROC"] = None
        case "YOLO v8 License Plate Detector (FP16)":
            if object_detection_device == "NPU":
                raise ValueError(
                    "YOLO v8 License Plate Detector model is not supported on NPU device. Please select another model."
                )

            constants["OBJECT_DETECTION_MODEL_PATH"] = (
                f"{MODELS_PATH}/public/yolov8_license_plate_detector/FP16/yolov8_license_plate_detector.xml"
            )
            constants["OBJECT_DETECTION_MODEL_PROC"] = None
        case _:
            raise ValueError("Unrecognized Object Detection Model")

    match object_classification_model:
        case "Disabled":
            constants["OBJECT_CLASSIFICATION_MODEL_PATH"] = "Disabled"
            constants["OBJECT_CLASSIFICATION_MODEL_PROC"] = "Disabled"       
        case "ResNet-50 TF (INT8)":
            constants["OBJECT_CLASSIFICATION_MODEL_PATH"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/resnet-50-tf_INT8/resnet-50-tf_i8.xml"
            )
            constants["OBJECT_CLASSIFICATION_MODEL_PROC"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/resnet-50-tf_INT8/resnet-50-tf_i8.json"
            )
        case "EfficientNet B0 (INT8)":
            if object_classification_device == "NPU":
                raise ValueError(
                    "EfficientNet B0 model is not supported on NPU device. Please select another model."
                )

            constants["OBJECT_CLASSIFICATION_MODEL_PATH"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/efficientnet-b0_INT8/FP16-INT8/efficientnet-b0.xml"
            )
            constants["OBJECT_CLASSIFICATION_MODEL_PROC"] = (
                f"{MODELS_PATH}/pipeline-zoo-models/efficientnet-b0_INT8/efficientnet-b0.json"
            )
        case "MobileNet V2 PyTorch (FP16)":
            constants["OBJECT_CLASSIFICATION_MODEL_PATH"] = (
                f"{MODELS_PATH}/public/mobilenet-v2-pytorch/FP16/mobilenet-v2-pytorch.xml"
            )
            constants["OBJECT_CLASSIFICATION_MODEL_PROC"] = (
                f"{MODELS_PATH}/public/mobilenet-v2-pytorch/mobilenet-v2.json"
            )
        case "PaddleOCR (FP16)":
            constants["OBJECT_CLASSIFICATION_MODEL_PATH"] = (
                f"{MODELS_PATH}/public/ch_PP-OCRv4_rec_infer/FP16/ch_PP-OCRv4_rec_infer.xml"
            )
            constants["OBJECT_CLASSIFICATION_MODEL_PROC"] = None
        case "Vehicle Attributes Recognition Barrier 0039 (FP16)":
            constants["OBJECT_CLASSIFICATION_MODEL_PATH"] = (
                f"{MODELS_PATH}/public/vehicle-attributes-recognition-barrier-0039/FP16/vehicle-attributes-recognition-barrier-0039.xml"
            )
            constants["OBJECT_CLASSIFICATION_MODEL_PROC"] = (
                f"{MODELS_PATH}/public/vehicle-attributes-recognition-barrier-0039/vehicle-attributes-recognition-barrier-0039.json"
            )
        case _:
            raise ValueError("Unrecognized Object Classification Model")

    return video_output_path, constants, param_grid


def _iterate_param_grid(param_grid: Dict[str, List[str]]):
    keys, values = zip(*param_grid.items())
    for combination in product(*values):
        yield dict(zip(keys, combination))


def run_pipeline_and_extract_metrics(
    pipeline_cmd: GstPipeline,
    constants: Dict[str, str],
    parameters: Dict[str, List[str]],
    channels: int | tuple[int, int] = 1,
    elements: List[tuple[str, str, str]] = [],
    poll_interval: int = 1,
) -> Tuple[Dict[str, float], str, str]:
    global cancelled
    """

    Runs a GStreamer pipeline and extracts FPS metrics.

    Args:
        pipeline_cmd (str): The GStreamer pipeline command to execute.
        poll_interval (int): Interval to poll the process for metrics.
        channels (int): Number of channels to match in the FPS metrics.

    Returns:
        Tuple[Dict[str, float], str, str]: A dictionary of FPS metrics, stdout, and stderr.
    """
    logger = logging.getLogger("utils")
    results = []

    # Set the number of regular channels
    # If no tuple is provided, the number of regular channels is 0
    regular_channels = 0 if isinstance(channels, int) else channels[0]

    # Set the number of inference channels
    # If no tuple is provided, the number of inference channels is equal to the number of channels
    inference_channels = channels if isinstance(channels, int) else channels[1]

    for params in _iterate_param_grid(parameters):

        # Evaluate the pipeline with the given parameters, constants, and channels
        _pipeline = pipeline_cmd.evaluate(
            constants, params, regular_channels, inference_channels, elements
        )

        # Log the command
        logger.info(f"Pipeline Command: {_pipeline}")

        try:
            # Set the environment variable to enable all drivers
            env = os.environ.copy()
            env["GST_VA_ALL_DRIVERS"] = "1"

            # Spawn command in a subprocess
            process = Popen(_pipeline.split(" "), stdout=PIPE, stderr=PIPE, env=env)

            exit_code = None
            total_fps = None
            per_stream_fps = None
            num_streams = None
            last_fps = None
            channels = inference_channels + regular_channels
            avg_fps_dict = {}
            process_output = []

            # Define pattern to capture FPSCounter metrics
            overall_pattern = r"FpsCounter\(overall ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"
            avg_pattern = r"FpsCounter\(average ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"
            last_pattern = r"FpsCounter\(last ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"

            # Poll the process to check if it is still running
            while process.poll() is None:
                if cancelled:
                    process.terminate()
                    cancelled = False
                    break

                reads, _, _ = select.select([process.stdout], [], [], poll_interval)
                for r in reads:
                    line = r.readline()
                    if not line:
                        continue
                    process_output.append(line)

                    # Write the average FPS to the log
                    line_str = line.decode("utf-8")
                    match = re.search(avg_pattern, line_str)
                    if match:
                        result = {
                            "total_fps": float(match.group(2)),
                            "number_streams": int(match.group(3)),
                            "per_stream_fps": float(match.group(4)),
                        }
                        logger.info(
                            f"Avg FPS: {result['total_fps']} fps; Num Streams: {result['number_streams']}; Per Stream FPS: {result['per_stream_fps']} fps."
                        )

                        # Skip the result if the number of streams does not match the expected channels
                        if result["number_streams"] != channels:
                            continue

                        latest_fps = result["per_stream_fps"]
                        
                        # Write latest FPS to a file
                        with open("/home/dlstreamer/vippet/.collector-signals/fps.txt", "w") as f:
                            f.write(f"{latest_fps}\n")

                if ps.Process(process.pid).status() == "zombie":
                    exit_code = process.wait()
                    break

            # Process the output and extract FPS metrics
            for line in process_output:
                line_str = line.decode("utf-8")
                match = re.search(overall_pattern, line_str)
                if match:
                    result = {
                        "total_fps": float(match.group(2)),
                        "number_streams": int(match.group(3)),
                        "per_stream_fps": float(match.group(4)),
                    }
                    if result["number_streams"] == channels:
                        total_fps = result["total_fps"]
                        num_streams = result["number_streams"]
                        per_stream_fps = result["per_stream_fps"]
                        break

                match = re.search(avg_pattern, line_str)
                if match:
                    result = {
                        "total_fps": float(match.group(2)),
                        "number_streams": int(match.group(3)),
                        "per_stream_fps": float(match.group(4)),
                    }
                    avg_fps_dict[result["number_streams"]] = result

                match = re.search(last_pattern, line_str)
                if match:
                    result = {
                        "total_fps": float(match.group(2)),
                        "number_streams": int(match.group(3)),
                        "per_stream_fps": float(match.group(4)),
                    }
                    last_fps = result

            if total_fps is None and avg_fps_dict.keys():
                if channels in avg_fps_dict.keys():
                    total_fps = avg_fps_dict[channels]["total_fps"]
                    num_streams = avg_fps_dict[channels]["number_streams"]
                    per_stream_fps = avg_fps_dict[channels]["per_stream_fps"]
                else:
                    closest_match = min(
                        avg_fps_dict.keys(),
                        key=lambda x: abs(x - channels),
                        default=None,
                    )
                    total_fps = avg_fps_dict[closest_match]["total_fps"]
                    num_streams = avg_fps_dict[closest_match]["number_streams"]
                    per_stream_fps = avg_fps_dict[closest_match]["per_stream_fps"]

            if total_fps is None and last_fps:
                total_fps = last_fps["total_fps"]
                num_streams = last_fps["number_streams"]
                per_stream_fps = last_fps["per_stream_fps"]

            if total_fps is None:
                total_fps = "N/A"
                num_streams = "N/A"
                per_stream_fps = "N/A"

            # Log the metrics
            logger.info("Exit code: {}".format(exit_code))
            logger.info("Total FPS is {}".format(total_fps))
            logger.info("Per Stream FPS is {}".format(per_stream_fps))
            logger.info("Num of Streams is {}".format(num_streams))

            # Save results
            results.append(
                {
                    "params": params,
                    "exit_code": exit_code,
                    "total_fps": total_fps,
                    "per_stream_fps": per_stream_fps,
                    "num_streams": num_streams,
                }
            )

        except subprocess.CalledProcessError as e:
            logger.error(f"Error: {e}")
            continue
    return results
