"""benchmark.py

This module provides the Benchmark class for evaluating pipeline performance
based on configurable parameters and stream counts.
"""

import logging
from dataclasses import dataclass
import math
from typing import List

from pipeline_runner import PipelineRunner, PipelineRunResult
from api.api_schemas import (
    PipelineDensitySpec,
    PipelinePerformanceSpec,
    VideoOutputConfig,
)
from managers.pipeline_manager import get_pipeline_manager

pipeline_manager = get_pipeline_manager()


@dataclass
class BenchmarkResult:
    n_streams: int
    streams_per_pipeline: List[PipelinePerformanceSpec]
    per_stream_fps: float
    video_output_paths: dict[str, List[str]]

    def __repr__(self):
        return (
            f"BenchmarkResult("
            f"n_streams={self.n_streams}, "
            f"streams_per_pipeline={self.streams_per_pipeline}, "
            f"per_stream_fps={self.per_stream_fps}"
            f")"
        )


class Benchmark:
    """Benchmarking class for pipeline evaluation."""

    def __init__(self):
        self.best_result = None
        self.runner = PipelineRunner()
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _calculate_streams_per_pipeline(
        pipeline_benchmark_specs: list[PipelineDensitySpec], total_streams: int
    ) -> list[int]:
        """
        Calculate the number of streams for each pipeline based on their stream_rate ratios.

        Args:
            pipeline_benchmark_specs: List of PipelineDensitySpec with stream_rate ratios.
            total_streams: Total number of streams to distribute.

        Returns:
            List of stream counts per pipeline.

        Raises:
            ValueError: If stream_rate ratios don't sum to 100.
        """
        # Validate that ratios sum to 100
        total_ratio = sum(spec.stream_rate for spec in pipeline_benchmark_specs)
        if total_ratio != 100:
            raise ValueError(
                f"Pipeline stream_rate ratios must sum to 100%, got {total_ratio}%"
            )

        # Calculate streams per pipeline
        streams_per_pipeline_counts = []
        remaining_streams = total_streams

        for i, spec in enumerate(pipeline_benchmark_specs):
            if i == len(pipeline_benchmark_specs) - 1:
                # Last pipeline gets all remaining streams to handle rounding
                streams_per_pipeline_counts.append(remaining_streams)
            else:
                # Calculate proportional streams and round
                streams = round(total_streams * spec.stream_rate / 100)
                streams_per_pipeline_counts.append(streams)
                remaining_streams -= streams

        return streams_per_pipeline_counts

    def run(
        self,
        pipeline_benchmark_specs: list[PipelineDensitySpec],
        fps_floor: float,
        video_config: VideoOutputConfig,
    ) -> BenchmarkResult:
        """
        Run the benchmark and return the best configuration.

        Args:
            pipeline_benchmark_specs: List of PipelineDensitySpec with stream_rate ratios.
            fps_floor: Minimum FPS threshold per stream.

        Returns:
            BenchmarkResult with optimal stream configuration.
        """

        n_streams = 1
        per_stream_fps = 0.0
        exponential = True
        lower_bound = 1
        # We'll set this once we fall below the fps_floor
        higher_bound = -1
        best_config: tuple[int, list[PipelinePerformanceSpec], float] = (
            0,
            [],
            0.0,
        )  # (total_streams, run_specs, fps)

        while True:
            # Calculate streams per pipeline based on ratios
            streams_per_pipeline_counts = self._calculate_streams_per_pipeline(
                pipeline_benchmark_specs, n_streams
            )

            # Build run specs with calculated stream counts
            run_specs = [
                PipelinePerformanceSpec(id=spec.id, streams=streams)
                for spec, streams in zip(
                    pipeline_benchmark_specs, streams_per_pipeline_counts
                )
            ]

            self.logger.info(
                "Running benchmark with n_streams=%d, streams_per_pipeline=%s",
                n_streams,
                streams_per_pipeline_counts,
            )

            # Build pipeline command
            pipeline_command, video_output_paths = (
                pipeline_manager.build_pipeline_command(run_specs, video_config)
            )

            # Run the pipeline
            results = self.runner.run(pipeline_command, n_streams)

            # Check for cancellation
            if self.runner.is_cancelled():
                self.logger.info("Benchmark cancelled.")
                break

            if results is None or not isinstance(results, PipelineRunResult):
                raise RuntimeError("Pipeline runner returned invalid results.")

            try:
                total_fps = results.total_fps
                per_stream_fps = total_fps / n_streams if n_streams > 0 else 0.0
            except (ValueError, TypeError, ZeroDivisionError):
                raise RuntimeError("Failed to parse FPS metrics from pipeline results.")
            if total_fps == 0 or math.isnan(per_stream_fps):
                raise RuntimeError("Pipeline returned zero or invalid FPS metrics.")

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
                if per_stream_fps >= fps_floor:
                    best_config = (
                        n_streams,
                        run_specs,
                        per_stream_fps,
                    )
                    n_streams *= 2
                else:
                    exponential = False
                    higher_bound = n_streams
                    lower_bound = max(1, n_streams // 2)
                    n_streams = (lower_bound + higher_bound) // 2
            # use bisecting search for fine tune maximum number of streams
            else:
                if per_stream_fps >= fps_floor:
                    best_config = (
                        n_streams,
                        run_specs,
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

        if best_config[0] > 0:
            # Use the best configuration found
            total_streams = best_config[0]
            best_run_specs = best_config[1]

            # Build streams_per_pipeline dict from best_run_specs
            streams_per_pipeline = [
                PipelinePerformanceSpec(id=spec.id, streams=spec.streams)
                for spec in best_run_specs
            ]

            bm_result = BenchmarkResult(
                n_streams=total_streams,
                streams_per_pipeline=streams_per_pipeline,
                per_stream_fps=best_config[2],
                video_output_paths=video_output_paths,
            )
        else:
            # Fallback to last attempt - build streams_per_pipeline from last run_specs
            streams_per_pipeline = [
                PipelinePerformanceSpec(id=spec.id, streams=spec.streams)
                for spec in run_specs
            ]

            bm_result = BenchmarkResult(
                n_streams=n_streams,
                streams_per_pipeline=streams_per_pipeline,
                per_stream_fps=per_stream_fps,
                video_output_paths=video_output_paths,
            )

        return bm_result

    def cancel(self):
        """Cancel the ongoing benchmark."""
        self.runner.cancel()
