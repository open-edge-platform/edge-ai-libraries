import contextlib
import logging
import mmap
import os
import random
import re
import select
import string
import struct
import subprocess
import threading
import time
from itertools import product
from subprocess import Popen, PIPE
from typing import List, Dict

import cv2
import numpy as np
import psutil as ps

from gstpipeline import GstPipeline

cancelled = False
logger = logging.getLogger("utils")

UINT8_DTYPE_SIZE = 1
DEFAULT_FRAME_RATE = 30.0
VIDEO_STREAM_META_PATH = "/tmp/shared_memory/video_stream.meta"

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
    live_preview_enabled = kwargs.get("live_preview_enabled", False)

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
        f.write("0.0\n")

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
        "live_preview_enabled": [live_preview_enabled],
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


def find_shm_file():
    """
    Finds the most recent shared memory file for live preview.

    Returns:
        str or None: Full path of the most recent shared memory file, or None if not found.
    """
    try:
        shm_dir = "/dev/shm"
        files = os.listdir(shm_dir)
        shm_files = [f for f in files if f.startswith("shmpipe.")]
        if not shm_files:
            return None
        shm_files.sort(key=lambda x: os.path.getctime(os.path.join(shm_dir, x)), reverse=True)
        return os.path.join(shm_dir, shm_files[0])
    except OSError:
        logger.error("Error accessing /dev/shm directory.")
        return None


def read_latest_meta(meta_path):
    """
    Reads the metadata file for shared memory frame dimensions and dtype size.

    Args:
        meta_path (str): Path to the metadata file.

    Returns:
        tuple or None: (height, width, dtype_size) if successful, None otherwise.
    """
    try:
        with open(meta_path, "rb") as f:
            meta = f.read(12)
            if len(meta) != 12:
                logger.error("Metadata file does not contain expected 12 bytes.")
                return None
            height, width, dtype_size = struct.unpack("III", meta)
            return height, width, dtype_size
    except (OSError, struct.error) as e:
        logger.error(f"Error reading metadata file {meta_path}: {e}")
        return None


def read_shared_memory_frame(meta_path, shm_fd):
    """
    Reads a frame from shared memory using metadata for shape and dtype.

    Args:
        meta_path (str): Path to the metadata file.
        shm_fd (file object): File descriptor for shared memory.

    Returns:
        np.ndarray or None: RGB frame if successful, None otherwise.
    """
    if shm_fd is None:
        logger.error("Shared memory file descriptor is invalid.")
        return None

    meta = read_latest_meta(meta_path)
    if not meta:
        logger.error("Metadata is invalid.")
        return None
    height, width, dtype_size = meta
    try:
        frame_size = height * width * 3 * dtype_size
        mm = mmap.mmap(shm_fd.fileno(), 0, access=mmap.ACCESS_READ)
        buf = mm[:frame_size]
        mm.close()
        if len(buf) != frame_size:
            logger.error(f"Frame buffer size does not match expected frame size. Expected: {frame_size}, Actual: {len(buf)}")
            return None
        frame_bgr = np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 3))
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        return frame_rgb
    except (ValueError, OSError, cv2.error) as e:
        logger.error(f"Error reading shared memory frame: {e}")
        return None


def get_video_resolution(video_path):
    """
    Returns (width, height) of a video file or default (1280, 720) if any error occurs.
    """
    default_width = 1280
    default_height = 720

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logging.error(f"Cannot open video file: {video_path}")
            return default_width, default_height
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        # If width or height is zero, return defaults and log warning
        if width == 0 or height == 0:
            logging.warning(f"Could not read video resolution for file: {video_path}")
            return default_width, default_height
        return width, height
    except Exception:
        logging.error(f"Exception occurred while reading video resolution for file: {video_path}")
        return default_width, default_height

def run_pipeline_and_extract_metrics(
    pipeline_cmd: GstPipeline,
    constants: Dict[str, str],
    parameters: Dict[str, List[str]],
    channels: int | tuple[int, int] = 1,
    elements: List[tuple[str, str, str]] = [],
    poll_interval: int = 1,
):
    global cancelled
    """

    Runs a GStreamer pipeline and extracts FPS metrics.

    Args:
        pipeline_cmd (str): The GStreamer pipeline command to execute.
        poll_interval (int): Interval to poll the process for metrics.
        channels (int): Number of channels to match in the FPS metrics.

    Returns:
        List[Dict[str, any]]: A list of dictionaries containing the parameters and FPS metrics for each pipeline run.
    """

    results = []

    # Set the number of regular channels
    # If no tuple is provided, the number of regular channels is 0
    regular_channels = 0 if isinstance(channels, int) else channels[0]

    # Set the number of inference channels
    # If no tuple is provided, the number of inference channels is equal to the number of channels
    inference_channels = channels if isinstance(channels, int) else channels[1]

    for params in _iterate_param_grid(parameters):
        # Get live_preview_enabled from params
        live_preview_enabled = params.get("live_preview_enabled", False)

        # Evaluate the pipeline with the given parameters, constants, and channels
        _pipeline = pipeline_cmd.evaluate(constants, params, regular_channels, inference_channels, elements)

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
            process_stderr = []

            # Define pattern to capture FPSCounter metrics
            overall_pattern = r"FpsCounter\(overall ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"
            avg_pattern = r"FpsCounter\(average ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"
            last_pattern = r"FpsCounter\(last ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"

            stop_event = threading.Event()
            shm_fd = None

            def process_worker():
                try:
                    logger.debug("Starting process worker thread")
                    while not stop_event.is_set():
                        reads, _, _ = select.select([process.stdout, process.stderr], [], [], poll_interval)
                        for r in reads:
                            line = r.readline()
                            if not line:
                                continue
                            if r == process.stdout:
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
                            elif r == process.stderr:
                                process_stderr.append(line)
                except (OSError, ValueError, select.error) as e:
                    logger.error(f"process_worker exception: {e}")
                finally:
                    logger.debug("process_worker thread is stopping")

            # process_worker runs in a separate thread to avoid blocking the main thread in which we want to read frames as fast as possible
            worker_thread = threading.Thread(target=process_worker, daemon=True)
            worker_thread.start()

            try:
                if live_preview_enabled:
                    # Wait for the metadata file to be created, 10 seconds max
                    wait_time = 0
                    max_wait = 10
                    while not os.path.exists(VIDEO_STREAM_META_PATH) and wait_time < max_wait:
                        time.sleep(0.1)
                        wait_time += 0.1

                    # Wait for the shared memory file to be created, 10 seconds max
                    shm_file = None
                    wait_time = 0
                    while shm_file is None and wait_time < max_wait:
                        shm_file = find_shm_file()
                        if shm_file is None:
                            time.sleep(0.1)
                            wait_time += 0.1

                    if shm_file is None:
                        logger.error(f"Could not find shm_file for live preview after {max_wait} seconds, will not show live preview.")
                    else:
                        shm_fd = open(shm_file, "rb")

                    while True:
                        # Handle interruption
                        if cancelled:
                            process.terminate()
                            cancelled = False
                            logger.info("Process cancelled, terminating")
                            break

                        # If process is zombie, break and close shm_fd
                        try:
                            if ps.Process(process.pid).status() == "zombie":
                                exit_code = process.wait()
                                break
                        except ps.NoSuchProcess as e:
                            logger.info(f"Process {process.pid} is no longer running: {e}")
                            break

                        frame = read_shared_memory_frame(meta_path=VIDEO_STREAM_META_PATH, shm_fd=shm_fd)
                        yield frame
                        time.sleep(1.0 / DEFAULT_FRAME_RATE)

                    # Wait for GStreamer process to end if not already
                    try:
                        if process.poll() is None:
                            exit_code = process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        logger.warning("Process did not exit cleanly after closing socket.")

                else:
                    # No live preview: just wait for process
                    while process.poll() is None:
                        if cancelled:
                            process.terminate()
                            cancelled = False
                            logger.info("Process cancelled, terminating")
                            break
                        time.sleep(0.1)
                        try:
                            if ps.Process(process.pid).status() == "zombie":
                                exit_code = process.wait()
                                break
                        except ps.NoSuchProcess as e:
                            logger.info(f"Process {process.pid} is no longer running: {e}")
                            break

            finally:
                logger.debug("Stopping frame worker thread")
                stop_event.set()
                worker_thread.join()
                if shm_fd is not None:
                    with contextlib.suppress(Exception):
                        shm_fd.close()

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

            # Save results
            results.append(
                {
                    "params": params,
                    "exit_code": exit_code,
                    "total_fps": total_fps,
                    "per_stream_fps": per_stream_fps,
                    "num_streams": num_streams,
                    "stdout": "".join([line.decode("utf-8", errors="replace") for line in process_output]),
                    "stderr": "".join([line.decode("utf-8", errors="replace") for line in process_stderr]),
                }
            )

        except subprocess.CalledProcessError as e:
            logger.error(f"Error: {e}")
            continue
        except (OSError, ValueError) as e:
            logger.error(f"Pipeline execution error: {e}")
            continue
    return results
