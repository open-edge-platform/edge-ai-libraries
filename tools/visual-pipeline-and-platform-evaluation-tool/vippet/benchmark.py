"""benchmark.py

This module provides the Benchmark class for evaluating pipeline performance
based on configurable parameters and stream counts.
"""

import logging
from dataclasses import dataclass
import math
from typing import List

from pipeline_runner import PipelineRunner, PipelineRunResult
from api.api_schemas import PipelineStreamSpec
from internal_types import (
    InternalExecutionConfig,
    InternalOutputMode,
    InternalPipelineDensitySpec,
    InternalPipelinePerformanceSpec,
)
from managers.pipeline_manager import PipelineManager


@dataclass
class BenchmarkResult:
    """
    Result of a density benchmark run.

    Attributes:
        n_streams: Total number of streams across all pipelines.
        streams_per_pipeline: List of pipeline IDs with their stream counts.
            Pipeline IDs follow the format:
            * For variant reference: "/pipelines/{pipeline_id}/variants/{variant_id}"
            * For inline graph: "__graph-{16-char-hash}"
        per_stream_fps: Average FPS per stream achieved.
        video_output_paths: Mapping from pipeline ID to list of output file paths.
            Keys use the same ID format as streams_per_pipeline entries.
    """

    n_streams: int
    streams_per_pipeline: List[PipelineStreamSpec]
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
        # Initialize PipelineRunner in normal mode with max_runtime=0 (run until EOS)
        self.runner = PipelineRunner(mode="normal", max_runtime=0)
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _calculate_streams_per_pipeline(
        pipeline_density_specs: list[InternalPipelineDensitySpec], total_streams: int
    ) -> list[int]:
        """
        Calculate the number of streams for each pipeline based on their stream_rate ratios.

        Args:
            pipeline_density_specs: List of InternalPipelineDensitySpec with stream_rate ratios.
            total_streams: Total number of streams to distribute.

        Returns:
            List of stream counts per pipeline.

        Raises:
            ValueError: If stream_rate ratios don't sum to 100.
        """
        # Validate that ratios sum to 100
        total_ratio = sum(spec.stream_rate for spec in pipeline_density_specs)
        if total_ratio != 100:
            raise ValueError(
                f"Pipeline stream_rate ratios must sum to 100%, got {total_ratio}%"
            )

        # Calculate streams per pipeline
        streams_per_pipeline_counts = []
        remaining_streams = total_streams

        for i, spec in enumerate(pipeline_density_specs):
            if i == len(pipeline_density_specs) - 1:
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
        pipeline_density_specs: list[InternalPipelineDensitySpec],
        fps_floor: float,
        execution_config: InternalExecutionConfig,
        job_id: str,
    ) -> BenchmarkResult:
        """
        Run the benchmark and return the best configuration.

        Args:
            pipeline_density_specs: List of InternalPipelineDensitySpec with resolved
                pipeline information and stream_rate ratios.
            fps_floor: Minimum FPS threshold per stream.
            execution_config: InternalExecutionConfig for output and runtime.
                Note: output_mode=live_stream is not supported for density tests.
            job_id: Unique job identifier used for generating output filenames.

        Returns:
            BenchmarkResult with optimal stream configuration. The streams_per_pipeline
            field contains pipeline IDs already resolved in internal specs.

        Raises:
            ValueError: If output_mode is live_stream (not supported for density tests).
            ValueError: If stream_rate ratios don't sum to 100.
            RuntimeError: If pipeline execution fails.
        """
        # Validate that live_stream is not used for density tests
        if execution_config.output_mode == InternalOutputMode.LIVE_STREAM:
            raise ValueError(
                "Density tests do not support output_mode='live_stream'. "
                "Use output_mode='disabled' or output_mode='file' instead."
            )

        n_streams = 1
        per_stream_fps = 0.0
        exponential = True
        lower_bound = 1
        # We'll set this once we fall below the fps_floor
        higher_bound = -1
        best_config: tuple[
            int, list[PipelineStreamSpec], float, dict[str, List[str]]
        ] = (
            0,
            [],
            0.0,
            {},
        )  # (total_streams, streams_per_pipeline, fps, video_output_paths)

        while True:
            # Calculate streams per pipeline based on ratios
            streams_per_pipeline_counts = self._calculate_streams_per_pipeline(
                pipeline_density_specs, n_streams
            )

            # Build run specs with calculated stream counts
            # Convert density specs to performance specs for pipeline command building
            run_specs = [
                InternalPipelinePerformanceSpec(
                    pipeline_id=spec.pipeline_id,
                    pipeline_name=spec.pipeline_name,
                    pipeline_graph=spec.pipeline_graph,
                    streams=streams,
                )
                for spec, streams in zip(
                    pipeline_density_specs, streams_per_pipeline_counts
                )
            ]

            self.logger.info(
                "Running benchmark with n_streams=%d, streams_per_pipeline=%s",
                n_streams,
                streams_per_pipeline_counts,
            )

            # Build pipeline command using PipelineManager singleton
            pipeline_command, video_output_paths, _ = (
                PipelineManager().build_pipeline_command(
                    run_specs, execution_config, job_id
                )
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

            # Build streams_per_pipeline with pipeline IDs
            streams_per_pipeline_with_ids = [
                PipelineStreamSpec(id=spec.pipeline_id, streams=stream_count)
                for spec, stream_count in zip(
                    pipeline_density_specs, streams_per_pipeline_counts
                )
            ]

            # increase number of streams exponentially until we drop below fps_floor
            if exponential:
                if per_stream_fps >= fps_floor:
                    best_config = (
                        n_streams,
                        streams_per_pipeline_with_ids,
                        per_stream_fps,
                        video_output_paths,
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
                        streams_per_pipeline_with_ids,
                        per_stream_fps,
                        video_output_paths,
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
            bm_result = BenchmarkResult(
                n_streams=best_config[0],
                streams_per_pipeline=best_config[1],
                per_stream_fps=best_config[2],
                video_output_paths=best_config[3],
            )
        else:
            # Fallback to last attempt - build streams_per_pipeline from last run
            streams_per_pipeline_with_ids = [
                PipelineStreamSpec(id=spec.pipeline_id, streams=stream_count)
                for spec, stream_count in zip(
                    pipeline_density_specs, streams_per_pipeline_counts
                )
            ]

            bm_result = BenchmarkResult(
                n_streams=n_streams,
                streams_per_pipeline=streams_per_pipeline_with_ids,
                per_stream_fps=per_stream_fps,
                video_output_paths=video_output_paths,
            )

        return bm_result

    def cancel(self):
        """Cancel the ongoing benchmark."""
        self.runner.cancel()
