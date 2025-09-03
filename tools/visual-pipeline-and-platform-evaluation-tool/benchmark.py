"""benchmark.py

This module provides the Benchmark class for evaluating pipeline performance
based on configurable parameters and stream counts.
"""

import logging
import math
from typing import List, Dict, Tuple

from utils import run_pipeline_and_extract_metrics

logging.basicConfig(level=logging.INFO)


class Benchmark:
    """Benchmarking class for pipeline evaluation."""

    DEFAULT_RATE = 100  # Default rate for AI stream percentage

    def __init__(
        self,
        video_path: str,
        pipeline_cls,
        fps_floor: float,
        rate: int,
        parameters: Dict[str, List[str]],
        constants: Dict[str, str],
        elements: List[tuple[str, str, str]] | None = None,
    ):
        self.video_path = video_path
        self.pipeline_cls = pipeline_cls
        self.fps_floor = fps_floor
        self.rate = rate if rate is not None else self.DEFAULT_RATE
        self.parameters = parameters
        self.constants = constants
        self.elements = elements if elements is not None else []
        self.best_result = None
        self.results = []

        self.logger = logging.getLogger("Benchmark")

    def _run_pipeline_and_extract_metrics(
        self,
        pipeline_cls,
        constants: Dict[str, str],
        parameters: Dict[str, List[str]],
        channels: Tuple[int, int],
        elements: List[tuple[str, str, str]],
    ) -> List[Dict[str, float]]:
        """Run the pipeline and extract metrics."""
        result = run_pipeline_and_extract_metrics(
            pipeline_cls,
            constants=constants,
            parameters=parameters,
            channels=channels,
            elements=elements,
        )

        # Handle both generator and direct return
        try:
            # Exhaust generator to get StopIteration value
            while True:
                next(result)
        except StopIteration as e:
            results = e.value
        return results

    def run(self) -> Tuple[int, int, int, float]:
        """Run the benchmark and return the best configuration."""
        n_streams = 1
        exponential = True
        lower_bound = 1
        # We'll set this once we fall below the fps_floor
        higher_bound = -1
        best_config = (0, 0, 0, 0.0)

        while True:
            ai_streams = math.ceil(n_streams * (self.rate / 100))
            non_ai_streams = n_streams - ai_streams

            try:
                results = self._run_pipeline_and_extract_metrics(
                    self.pipeline_cls,
                    constants=self.constants,
                    parameters=self.parameters,
                    channels=(non_ai_streams, ai_streams),
                    elements=self.elements,
                )
            except StopIteration:
                return (0, 0, 0, 0.0)

            if not results or results[0] is None or not isinstance(results[0], dict):
                return (0, 0, 0, 0.0)
            if results[0].get("exit_code") != 0:
                return (0, 0, 0, 0.0)

            result = results[0]
            try:
                total_fps = float(result["total_fps"])
                per_stream_fps = total_fps / n_streams if n_streams > 0 else 0.0
            except (ValueError, TypeError, ZeroDivisionError):
                return (0, 0, 0, 0.0)
            if total_fps == 0 or math.isnan(per_stream_fps):
                return (0, 0, 0, 0.0)

            self.logger.info(
                "n_streams=%d, total_fps=%f, per_stream_fps=%f, exponential=%s, lower_bound=%d, higher_bound=%s",
                n_streams,
                total_fps,
                per_stream_fps,
                exponential,
                lower_bound,
                higher_bound,
            )

            # increase number of streams exponentially until we drop below fps_floor
            if exponential:
                if per_stream_fps >= self.fps_floor:
                    best_config = (
                        n_streams,
                        ai_streams,
                        non_ai_streams,
                        per_stream_fps,
                    )
                    n_streams *= 2
                else:
                    exponential = False
                    higher_bound = n_streams
                    lower_bound = n_streams // 2
                    n_streams = (lower_bound + higher_bound) // 2
            # use bisecting search for fine tune maximum number of streams
            else:
                if per_stream_fps >= self.fps_floor:
                    best_config = (
                        n_streams,
                        ai_streams,
                        non_ai_streams,
                        per_stream_fps,
                    )
                    lower_bound = n_streams + 1
                else:
                    higher_bound = n_streams - 1

                if lower_bound > higher_bound:
                    break  # Binary search complete

                n_streams = (lower_bound + higher_bound) // 2

            if n_streams <= 0:
                n_streams = 1  # Prevent N from going below 1

        return (
            best_config
            if best_config[0] > 0
            else (n_streams, ai_streams, non_ai_streams, per_stream_fps)
        )
