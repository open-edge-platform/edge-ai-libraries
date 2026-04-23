"""benchmark.py

This module provides the Benchmark class for evaluating pipeline performance
based on configurable parameters and stream counts.
"""

import logging
import math
from dataclasses import dataclass, field

from internal_types import (
    InternalExecutionConfig,
    InternalOutputMode,
    InternalPipelineDensitySpec,
    InternalPipelinePerformanceSpec,
    InternalPipelineStreamSpec,
)
from managers.pipeline_manager import PipelineManager
from pipeline_runner import LatencyTracerSample, PipelineRunner


@dataclass
class BenchmarkResult:
    """
    Result of a density benchmark run.

    Attributes:
        n_streams: Total number of streams across all pipelines.
        streams_per_pipeline: List of InternalPipelineStreamSpec with pipeline IDs
            and their stream counts. Pipeline IDs follow the format:
            * For variant reference: "/pipelines/{pipeline_id}/variants/{variant_id}"
            * For inline graph: "__graph-{16-char-hash}"
        per_stream_fps: Average FPS per stream achieved.
        video_output_paths: Mapping from pipeline ID to output directory path.
            Keys use the same ID format as streams_per_pipeline entries.
            The directory contains all video files produced by the pipeline.
            Use collect_video_outputs_from_dirs() to get file lists after pipeline completes.
        latency_tracer_metrics: Last observed DLStreamer ``latency_tracer``
            sample per stream, keyed by ``stream_id``, captured from the
            run that produced the reported (``n_streams``,
            ``per_stream_fps``) pair — i.e. the best-configuration run
            the benchmark ultimately selected, NOT the final iteration
            of the search.

            * ``None`` when the tracer was not enabled for this
              benchmark.
            * Empty ``dict`` when the tracer was enabled but the
              best-configuration run produced no samples.
    """

    n_streams: int
    streams_per_pipeline: list[InternalPipelineStreamSpec]
    per_stream_fps: float
    video_output_paths: dict[str, str]
    latency_tracer_metrics: dict[str, LatencyTracerSample] | None = None

    def __repr__(self):
        return (
            f"BenchmarkResult("
            f"n_streams={self.n_streams}, "
            f"streams_per_pipeline={self.streams_per_pipeline}, "
            f"per_stream_fps={self.per_stream_fps}"
            f")"
        )


@dataclass
class _BestConfig:
    """
    Internal snapshot of the best-performing benchmark iteration so far.

    The search loop in :meth:`Benchmark.run` keeps updating this snapshot
    every time a new iteration meets ``fps_floor``. At the end of the
    search its contents are copied into :class:`BenchmarkResult`.

    ``latency_tracer_metrics`` is snapshotted by value (shallow copy of
    the dict) because :class:`PipelineRunner` resets its internal
    ``latency_tracer_metrics`` map at the start of every run; without a
    snapshot, by the time the search finishes the runner would only
    hold samples from the LAST iteration.

    Attributes:
        n_streams: Total number of streams of this configuration.
            ``0`` means "no configuration has met fps_floor yet".
        streams_per_pipeline: Per-pipeline stream allocation captured
            when this configuration was recorded.
        per_stream_fps: Per-stream FPS measured for this configuration.
        video_output_paths: Output directory paths declared by the
            pipeline command of this configuration.
        latency_tracer_metrics: Shallow copy of
            ``PipelineRunner.latency_tracer_metrics`` taken right after
            this configuration's run completed. ``None`` when the
            tracer was disabled.
    """

    n_streams: int = 0
    streams_per_pipeline: list[InternalPipelineStreamSpec] = field(default_factory=list)
    per_stream_fps: float = 0.0
    video_output_paths: dict[str, str] = field(default_factory=dict)
    latency_tracer_metrics: dict[str, LatencyTracerSample] | None = None


class Benchmark:
    """Benchmarking class for pipeline evaluation."""

    def __init__(self, max_runtime: float = 0, enable_latency_metrics: bool = False):
        self.best_result = None
        # Initialize PipelineRunner in normal mode with optional max_runtime for each run.
        # `enable_latency_metrics` is forwarded so that the GStreamer subprocess
        # is launched with the DLStreamer latency_tracer active when requested.
        self.runner = PipelineRunner(
            mode="normal",
            max_runtime=max_runtime,
            enable_latency_metrics=enable_latency_metrics,
        )
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
            field contains InternalPipelineStreamSpec with pipeline IDs already resolved
            in internal specs.

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
        # Snapshot of the best-performing iteration observed so far.
        # `n_streams=0` marks "nothing has met fps_floor yet".
        best_config = _BestConfig()

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

            # Build pipeline command using PipelineManager singleton.
            # `streams_per_pipeline` maps pipeline_id to the list of
            # `InternalStreamInfo` objects — we use its stream_ids to
            # populate `InternalPipelineStreamSpec.streams_ids` below
            # and to scope latency_tracer parsing to user-facing
            # source/sink pairs.
            pipeline_cmd = PipelineManager().build_pipeline_command(
                run_specs, execution_config, job_id
            )
            pipeline_command = pipeline_cmd.command
            video_output_paths = pipeline_cmd.video_output_paths
            streams_by_pipeline = pipeline_cmd.streams_per_pipeline

            # Run the pipeline
            # Run the pipeline. `allowed_stream_ids` scopes tracer
            # parsing to the user-facing streams declared by this run
            # so the density job's `latency_tracer_metrics` never
            # reports internal sinks.
            result = self.runner.run(
                pipeline_command,
                n_streams,
                allowed_stream_ids=set(pipeline_cmd.all_stream_ids),
            )

            # Check for cancellation
            if result.cancelled:
                self.logger.info("Benchmark cancelled.")
                break

            try:
                total_fps = result.total_fps
                per_stream_fps = total_fps / n_streams if n_streams > 0 else 0.0
            except (ValueError, TypeError, ZeroDivisionError):
                raise RuntimeError("Failed to parse FPS metrics from pipeline results.")
            if total_fps == 0 or math.isnan(per_stream_fps):
                raise RuntimeError("Pipeline returned zero or invalid FPS metrics.")

            self.logger.info(
                "exit_code=%d, n_streams=%d, total_fps=%f, per_stream_fps=%f, exponential=%s, lower_bound=%d, higher_bound=%s, details=%s",
                result.exit_code,
                n_streams,
                total_fps,
                per_stream_fps,
                exponential,
                lower_bound,
                higher_bound,
                result.details,
            )

            # Build streams_per_pipeline with pipeline IDs. `streams_ids`
            # mirrors the stream_ids that PipelineManager assigned to
            # the main-branch source/sink pair of every stream in this
            # run; they are the keys used by latency_tracer_metrics.
            streams_per_pipeline_with_ids = [
                InternalPipelineStreamSpec(
                    id=spec.pipeline_id,
                    streams=stream_count,
                    streams_ids=[
                        info.stream_id
                        for info in streams_by_pipeline.get(spec.pipeline_id, [])
                    ],
                )
                for spec, stream_count in zip(
                    pipeline_density_specs, streams_per_pipeline_counts
                )
            ]

            # increase number of streams exponentially until we drop below fps_floor
            if exponential:
                if per_stream_fps >= fps_floor:
                    best_config = self._snapshot_best(
                        n_streams=n_streams,
                        streams_per_pipeline=streams_per_pipeline_with_ids,
                        per_stream_fps=per_stream_fps,
                        video_output_paths=video_output_paths,
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
                    best_config = self._snapshot_best(
                        n_streams=n_streams,
                        streams_per_pipeline=streams_per_pipeline_with_ids,
                        per_stream_fps=per_stream_fps,
                        video_output_paths=video_output_paths,
                    )
                    lower_bound = n_streams + 1
                else:
                    higher_bound = n_streams - 1

                if lower_bound > higher_bound:
                    break  # Binary search complete

                n_streams = (lower_bound + higher_bound) // 2

            if n_streams <= 0:
                n_streams = 1  # Prevent N from going below 1

        if best_config.n_streams > 0:
            # Use the best configuration found
            bm_result = BenchmarkResult(
                n_streams=best_config.n_streams,
                streams_per_pipeline=best_config.streams_per_pipeline,
                per_stream_fps=best_config.per_stream_fps,
                video_output_paths=best_config.video_output_paths,
                latency_tracer_metrics=best_config.latency_tracer_metrics,
            )
        else:
            # Fallback to last attempt - build streams_per_pipeline from last run.
            # `streams_by_pipeline` reflects the MOST RECENT run, which
            # matches `n_streams` / `per_stream_fps` reported below.
            streams_per_pipeline_with_ids = [
                InternalPipelineStreamSpec(
                    id=spec.pipeline_id,
                    streams=stream_count,
                    streams_ids=[
                        info.stream_id
                        for info in streams_by_pipeline.get(spec.pipeline_id, [])
                    ],
                )
                for spec, stream_count in zip(
                    pipeline_density_specs, streams_per_pipeline_counts
                )
            ]

            bm_result = BenchmarkResult(
                n_streams=n_streams,
                streams_per_pipeline=streams_per_pipeline_with_ids,
                per_stream_fps=per_stream_fps,
                video_output_paths=video_output_paths,
                latency_tracer_metrics=self._snapshot_latency_tracer_metrics(),
            )

        return bm_result

    def _snapshot_best(
        self,
        n_streams: int,
        streams_per_pipeline: list[InternalPipelineStreamSpec],
        per_stream_fps: float,
        video_output_paths: dict[str, str],
    ) -> _BestConfig:
        """
        Capture the just-completed iteration as the new best configuration.

        The `PipelineRunner` resets its `latency_tracer_metrics` map at
        the start of every run, so the snapshot must be taken
        immediately after the iteration finishes — otherwise the next
        iteration would overwrite it. A shallow copy of the map is
        enough because `LatencyTracerSample` is a frozen-by-convention
        dataclass of floats.

        Args:
            n_streams: Total stream count of this iteration.
            streams_per_pipeline: Per-pipeline allocation for this iteration.
            per_stream_fps: Measured per-stream FPS of this iteration.
            video_output_paths: Output directory map of this iteration.

        Returns:
            A fully populated :class:`_BestConfig` snapshot.
        """
        return _BestConfig(
            n_streams=n_streams,
            streams_per_pipeline=streams_per_pipeline,
            per_stream_fps=per_stream_fps,
            video_output_paths=video_output_paths,
            latency_tracer_metrics=self._snapshot_latency_tracer_metrics(),
        )

    def _snapshot_latency_tracer_metrics(
        self,
    ) -> dict[str, LatencyTracerSample] | None:
        """
        Return a shallow copy of the runner's current latency_tracer map.

        Returns ``None`` when the tracer is disabled (the runner keeps
        its map as ``None`` in that case); otherwise returns a new
        ``dict`` so subsequent runs, which reset the runner's map,
        cannot mutate the snapshot.
        """
        current = self.runner.latency_tracer_metrics
        if current is None:
            return None
        return dict(current)

    def cancel(self):
        """Cancel the ongoing benchmark."""
        self.runner.cancel()
