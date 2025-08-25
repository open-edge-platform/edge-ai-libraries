import logging
from dataclasses import dataclass
from typing import Dict, List

from gstpipeline import GstPipeline
from utils import run_pipeline_and_extract_metrics

logging.basicConfig(level=logging.INFO)


@dataclass
class OptimizationResult:
    params: Dict[str, str]
    exit_code: int
    total_fps: float
    per_stream_fps: float
    stdout: str = ""
    stderr: str = ""

    def __repr__(self):
        return (
            f"OptimizationResult("
            f"params={self.params}, "
            f"exit_code={self.exit_code}, "
            f"total_fps={self.total_fps}, "
            f"per_stream_fps={self.per_stream_fps}"
            f")"
        )


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

        # Set the number of regular channels
        # If no tuple is provided, the number of regular channels is 0
        self.regular_channels = 0 if isinstance(channels, int) else channels[0]

        # Set the number of inference channels
        # If no tuple is provided, the number of inference channels is equal to the number of channels
        self.inference_channels = channels if isinstance(channels, int) else channels[1]

        # Initialize results
        self.results: List[OptimizationResult] = []

        # Configure logging
        self.logger = logging.getLogger("PipelineOptimizer")

    @staticmethod
    def is_success_result(exit_code, stderr) -> bool:
        # Accept exit_code==0 or shmsink bug (exit_code!=0 and specific error in stderr)
        # TODO: change this when bug is fixed https://gitlab.freedesktop.org/gstreamer/gstreamer/-/issues/4487
        if exit_code == 0:
            return True
        if (
            exit_code != 0
            and "Failed waiting on fd activity" in stderr
            and "gstshmsink.c" in stderr
            and "gst_poll_wait returned -1, errno: 16" in stderr
        ):
            return True
        return False

    def _run_and_collect_metrics(self, live_preview=False):
        result = run_pipeline_and_extract_metrics(
            pipeline_cmd=self.pipeline,
            constants=self.constants,
            parameters=self.param_grid,
            channels=(self.regular_channels, self.inference_channels),
            elements=self.elements,
        )

        metrics_list = None
        if live_preview:
            try:
                while True:
                    frame = next(result)
                    yield frame
            except StopIteration as e:
                metrics_list = e.value
            # After generator is exhausted, yield None to signal end
            yield None
        else:
            try:
                while True:
                    next(result)
            except StopIteration as e:
                metrics_list = e.value

        # Iterate over the list of metrics
        for metrics in metrics_list:
            exit_code = metrics.get("exit_code")
            stdout = metrics.get("stdout", "")
            stderr = metrics.get("stderr", "")

            success_result = self.is_success_result(exit_code, stderr)
            # If is success_result but shmsink bug, set exit_code to 0
            if exit_code != 0 and success_result:
                self.logger.debug(
                    "Detected shmsink bug, treating as success (exit_code=0)"
                )
                exit_code = 0

            if not success_result:
                self.logger.error("Pipeline failed with exit_code=%s", exit_code)
                self.logger.error("STDOUT:\n%s", stdout)
                self.logger.error("STDERR:\n%s", stderr)

            self.logger.info("Exit code: {}".format(exit_code))
            self.logger.info("Total FPS is {}".format(metrics["total_fps"]))
            self.logger.info("Per Stream FPS is {}".format(metrics["per_stream_fps"]))
            self.logger.info("Num of Streams is {}".format(metrics["num_streams"]))

            # Save results
            self.results.append(
                OptimizationResult(
                    params=metrics["params"],
                    exit_code=exit_code,
                    total_fps=metrics["total_fps"],
                    per_stream_fps=metrics["per_stream_fps"],
                    stdout=stdout,
                    stderr=stderr,
                )
            )

    def run_without_live_preview(self):
        # Call shared method without live_preview, don't yield frames
        for _ in self._run_and_collect_metrics(live_preview=False):
            pass

    def run_with_live_preview(self):
        # Yield frames from shared method, with live_preview enabled
        yield from self._run_and_collect_metrics(live_preview=True)

    def evaluate(self) -> OptimizationResult:
        if not self.results:
            raise ValueError("No results to evaluate")

        # ignore results that are not success results
        _results = [
            result
            for result in self.results
            if self.is_success_result(result.exit_code, result.stderr)
        ]

        # Find the best result
        best_result = max(_results, key=lambda x: x.per_stream_fps, default=None)

        # Log the best result
        self.logger.info("Best result:")
        self.logger.info(best_result)

        return best_result
