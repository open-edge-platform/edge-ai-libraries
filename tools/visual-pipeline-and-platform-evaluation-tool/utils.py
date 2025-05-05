import subprocess
import re
import time
from typing import List, Dict, Tuple
from subprocess import Popen, PIPE
import psutil as ps
from itertools import product
import logging
from pipeline import GstPipeline

def _iterate_param_grid(param_grid: Dict[str, List[str]]):
    keys, values = zip(*param_grid.items())
    for combination in product(*values):
        yield dict(zip(keys, combination))

def run_pipeline_and_extract_metrics(
    pipeline_cmd: str,
    inference_channels,
    regular_channels,
    parameters,
    constants,
    elements,
    poll_interval: int = 1,
) -> Tuple[Dict[str, float], str, str]:
    """
    Runs a GStreamer pipeline and extracts FPS metrics.

    Args:
        pipeline_cmd (str): The GStreamer pipeline command to execute.
        poll_interval (int): Interval to poll the process for metrics.
        channels (int): Number of channels to match in the FPS metrics.

    Returns:
        Tuple[Dict[str, float], str, str]: A dictionary of FPS metrics, stdout, and stderr.
    """
    logger = logging.getLogger("run_pipeline_and_extract_metrics")
    results = []
   # for params in parameters:
    for params in _iterate_param_grid(parameters):        

            # Evaluate the pipeline with the given parameters, constants, and channels
            _pipeline = pipeline_cmd.evaluate(
                constants, params, regular_channels, inference_channels, elements
            )

            # Log the command
            logger.info(f"run_pipeline_and_extract_metrics: {pipeline_cmd}")

            try:
                # Spawn command in a subprocess
                process = Popen(_pipeline.split(" "), stdout=PIPE, stderr=PIPE)

                exit_code = None
                total_fps = None
                per_stream_fps = None
                num_streams = None
                last_fps = None
                channels = inference_channels + regular_channels
                avg_fps_dict = {}
                
                # Capture Memory and CPU metrics
                while process.poll() is None:

                    time.sleep(poll_interval)

                    if ps.Process(process.pid).status() == "zombie":
                        exit_code = process.wait()
                        break

                # Define pattern to capture FPSCounter metrics
                overall_pattern = r"FpsCounter\(overall ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"
                avg_pattern = r"FpsCounter\(average ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"
                last_pattern = r"FpsCounter\(last ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"
                
                logger.info("overall_pattern: {}".format(overall_pattern))
                logger.info("avg_pattern {}".format(avg_pattern))
                logger.info("last_pattern {}".format(last_pattern))
                # Capture FPSCounter metrics
                for line in iter(process.stdout.readline, b""):
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
                        closest_match = min(avg_fps_dict.keys(), key=lambda x: abs(x -channels), default=None)
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