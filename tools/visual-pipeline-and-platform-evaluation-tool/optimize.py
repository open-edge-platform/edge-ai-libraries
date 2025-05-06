import logging
import pprint
import re
import subprocess
import time
from dataclasses import dataclass
from itertools import product
from subprocess import PIPE, Popen
from typing import Dict, List
from utils import run_pipeline_and_extract_metrics

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
        elements: List[tuple[str, str, str]] = [],
    ):

        # Initialize class variables
        self.pipeline = pipeline
        self.constants = constants
        self.param_grid = param_grid
        self.poll_interval = poll_interval
        self.elements = elements

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

    def optimize(self):


        metrics_list = run_pipeline_and_extract_metrics(pipeline_cmd=self.pipeline, constants=self.constants, parameters=self.param_grid, channels=(self.regular_channels, self.inference_channels), 
                                                   elements=self.elements)
        # Iterate over the list of metrics
        for metrics in metrics_list:
            # Log the metrics
            self.logger.info(f"Metrics returned: {metrics}")
            self.logger.info("Exit code: {}".format(metrics["exit_code"]))
            self.logger.info("Total FPS is {}".format(metrics["total_fps"]))
            self.logger.info("Per Stream FPS is {}".format(metrics["per_stream_fps"]))

            # Save results
            self.results.append(
            OptimizationResult(
                params=metrics["params"],
                exit_code=metrics["exit_code"],
                total_fps=metrics["total_fps"],
                per_stream_fps=metrics["per_stream_fps"],
            )
        )

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
