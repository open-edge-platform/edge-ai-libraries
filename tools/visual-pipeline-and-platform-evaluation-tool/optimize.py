import logging
import pprint
import re
import subprocess
import time
from dataclasses import dataclass
from itertools import product
from subprocess import PIPE, Popen
from typing import Dict, List

import psutil as ps

from pipeline import GstPipeline

logging.basicConfig(level=logging.INFO)


@dataclass
class OptimizationResult:
    params: Dict[str, str]
    exit_code: int
    total_fps: float
    per_stream_fps: float


class PipelineOptimizer:
    def __init__(
        self,
        pipeline: GstPipeline,
        constants: Dict[str, str],
        param_grid: Dict[str, List[str]],
        poll_interval: int = 1,
        channels: int | tuple[int, int] = 1,
    ):

        # Initialize class variables
        self.pipeline = pipeline
        self.constants = constants
        self.param_grid = param_grid
        self.poll_interval = poll_interval

        # Set the number of channels
        self.channels = (
            channels if isinstance(channels, int) else channels[0] + channels[1]
        )

        # Set the number if regular channels
        # If no tuple is provided, the number of regular channels is 0
        self.regular_channels = 0 if isinstance(channels, int) else channels[0]

        # Set the number of inference channels
        # If no tuple is provided, the number of inference channels is equal to the number of channels
        self.inference_channels = channels if isinstance(channels, int) else channels[1]

        # Initialize results
        self.results: List[OptimizationResult] = []

        # Configure logging
        self.logger = logging.getLogger("PipelineOptimizer")

    def _iterate_param_grid(self, param_grid: Dict[str, List[str]]):
        keys, values = zip(*param_grid.items())
        for combination in product(*values):
            yield dict(zip(keys, combination))

    def optimize(self):

        # Run gst-inspect-1.0 to get the list of elements
        process = Popen(["gst-inspect-1.0", "va"], stdout=PIPE, stderr=PIPE)
        elements = process.communicate()[0].decode("utf-8").split("\n")

        # Log the elements
        self.logger.info("Elements:")
        self.logger.info(pprint.pformat(elements))

        # Find the available encoder
        # Note that the selected encoder is the last one on the list.
        # This is usually vah264lpenc if the encoder is available.
        # Otherwise, fallback to the only available encoder, usually vah264enc.
        encoder = [element for element in elements if "vah264enc" in element or "vah264lpenc" in element][-1]
        encoder = encoder.split(":")[0].strip()

        # Log the encoder
        self.logger.info(f"Encoder: {encoder}")

        for params in self._iterate_param_grid(self.param_grid):

            # Evaluate the pipeline with the given parameters, constants, and channels
            _pipeline = self.pipeline.evaluate(
                self.constants, params, self.regular_channels, self.inference_channels, encoder
            )

            # Log the command
            self.logger.info(f"Running pipeline: {_pipeline}")

            try:
                # Spawn command in a subprocess
                process = Popen(_pipeline.split(" "), stdout=PIPE, stderr=PIPE)

                exit_code = None
                total_fps = 0
                per_stream_fps = 0

                # Capture Memory and CPU metrics
                while process.poll() is None:

                    time.sleep(self.poll_interval)

                    if ps.Process(process.pid).status() == "zombie":
                        exit_code = process.wait()
                        break

                # Define pattern to capture FPSCounter metrics
                pattern = r"FpsCounter\(overall ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"

                # Capture FPSCounter metrics
                for line in iter(process.stdout.readline, b""):
                    line_str = line.decode("utf-8")

                    match = re.search(pattern, line_str)
                    if match:
                        result = {
                            "total_fps": float(match.group(2)),
                            "number_streams": int(match.group(3)),
                            "per_stream_fps": float(match.group(4)),
                        }
                        if result["number_streams"] == self.channels:
                            total_fps = result["total_fps"]
                            per_stream_fps = result["per_stream_fps"]
                            break

                # Log the metrics
                self.logger.info("Exit code: {}".format(exit_code))
                self.logger.info("Total FPS is {}".format(total_fps))
                self.logger.info("Per Stream FPS is {}".format(per_stream_fps))

                # Save results
                self.results.append(
                    OptimizationResult(
                        params=params,
                        exit_code=exit_code,
                        total_fps=total_fps,
                        per_stream_fps=per_stream_fps,
                    )
                )

            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error: {e}")
                continue

    def evaluate(self) -> OptimizationResult:
        if not self.results:
            raise ValueError("No results to evaluate")

        # ignore results where the exit code is not 0
        _results = [result for result in self.results if result.exit_code == 0]

        # Find the best result
        best_result = max(_results, key=lambda x: x.per_stream_fps, default=None)

        # Log the best result
        self.logger.info("Best result:")
        self.logger.info(best_result)

        return best_result


if __name__ == "__main__":

    # Define constants grid
    constants = {"NUM_BUFFERS": "1000"}

    # Define parameter grid
    # param_grid = {"pattern": ["snow", "ball", "gradient"]}
    param_grid = {"pattern": ["snow"]}

    class TestPipeline(GstPipeline):
        def __init__(self):
            super().__init__()
            self._pipeline = (
                "videotestsrc "
                " num-buffers={NUM_BUFFERS} "
                " pattern={pattern} ! "
                "videoconvert ! "
                "gvafpscounter ! "
                "fakesink"
            )

        def evaluate(self, constants, parameters, inference_channels, regular_channels):
            return "gst-launch-1.0 -q " + " ".join(
                [self._pipeline.format(**parameters, **constants)]
                * (inference_channels + regular_channels)
            )

    # Define parametrized pipeline
    pipeline = TestPipeline()
    optimizer = PipelineOptimizer(
        pipeline=pipeline, constants=constants, param_grid=param_grid, channels=20
    )
    optimizer.optimize()
    _ = optimizer.evaluate()
