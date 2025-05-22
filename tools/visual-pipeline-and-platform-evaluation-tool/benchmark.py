"""benchmark.py

This module provides the Benchmark class for evaluating pipeline performance
based on configurable parameters and stream counts.
"""
from typing import List, Dict, Tuple
import math
import logging
from utils import run_pipeline_and_extract_metrics

logging.basicConfig(level=logging.INFO)


class Benchmark:

    """Benchmarking class for pipeline evaluation."""

    def __init__(
        self,
        video_path: str,
        pipeline_cls,
        fps_floor: float,
        rate: int,
        parameters: Dict[str, str],
        constants: Dict[str, str],
        elements: List[tuple[str, str, str]] = None,
    ):
        self.video_path = video_path
        self.pipeline_cls = pipeline_cls
        self.fps_floor = fps_floor
        self.rate = rate
        self.parameters = parameters
        self.constants = constants
        self.elements = elements if elements is not None else []
        self.best_result = None
        self.results = []

        self.logger = logging.getLogger("Benchmark")

    def run(self) -> Tuple[int, int, int, float]:
        """Run the benchmark and return the best configuration."""
        n_streams = 1
        increments = 1
        incrementing = True
        best_config = (0, 0, 0, 0.0)

        while True:
            ai_streams = math.ceil(n_streams * (self.rate / 100))
            non_ai_streams = n_streams - ai_streams

            results = run_pipeline_and_extract_metrics(
                self.pipeline_cls,
                constants=self.constants,
                parameters=self.parameters,
                channels=(non_ai_streams, ai_streams),
                elements=self.elements,
            )
            if not results:
                self.logger.info("No results returned from run_pipeline_and_extract_metrics")
                break

            result = results[0]
            try:
                total_fps = float(result["total_fps"])
                per_stream_fps = total_fps / n_streams if n_streams > 0 else 0.0
            except (ValueError, TypeError, ZeroDivisionError):
                self.logger.info("Invalid FPS value, skipping this result.")
                break

            self.logger.info(
                "n_streams=%d, total_fps=%f, per_stream_fps=%f, increments=%d, incrementing=%s",
                n_streams, total_fps, per_stream_fps, increments, incrementing
            )

            if incrementing:
                if per_stream_fps >= self.fps_floor:
                    increments = int(per_stream_fps / self.fps_floor)
                    if increments <= 1:
                        increments = 5
                else:
                    incrementing = False
                    increments = -1
            else:
                if per_stream_fps >= self.fps_floor:
                    best_config = (n_streams, ai_streams, non_ai_streams, per_stream_fps)
                    break  # Success
                else:
                    if n_streams <= 1:
                        self.logger.info("Failed to find a valid configuration.")
                        break  # Fail

            n_streams += increments
            if n_streams <= 0:
                n_streams = 1  # Prevent N from going below 1

        return (
            best_config
            if best_config[0] > 0
            else (n_streams, ai_streams, non_ai_streams, per_stream_fps)
        )
