import unittest
from unittest.mock import patch, MagicMock

from benchmark import (
    Benchmark,
    BenchmarkResult,
)
from graph import Graph, Node, Edge
from internal_types import (
    InternalExecutionConfig,
    InternalMetadataMode,
    InternalOutputMode,
    InternalPipelineDensitySpec,
    InternalPipelineStreamSpec,
)
from managers.pipeline_manager import PipelineCommand
from pipeline_runner import LatencyTracerSample, PipelineResult


def create_simple_graph() -> Graph:
    """Helper to create a simple test pipeline Graph object."""
    return Graph(
        nodes=[
            Node(id="0", type="filesrc", data={"location": "/videos/test.mp4"}),
            Node(id="1", type="fakesink", data={}),
        ],
        edges=[
            Edge(id="0", source="0", target="1"),
        ],
    )


def create_internal_density_spec(
    pipeline_id: str, pipeline_name: str, stream_rate: int = 100
) -> InternalPipelineDensitySpec:
    """Helper to create InternalPipelineDensitySpec for testing."""
    return InternalPipelineDensitySpec(
        pipeline_id=pipeline_id,
        pipeline_name=pipeline_name,
        pipeline_graph=create_simple_graph(),
        stream_rate=stream_rate,
    )


def create_internal_execution_config(
    output_mode: InternalOutputMode = InternalOutputMode.DISABLED,
    max_runtime: float = 0,
    metadata_mode: InternalMetadataMode = InternalMetadataMode.DISABLED,
) -> InternalExecutionConfig:
    """Helper to create InternalExecutionConfig for testing."""
    return InternalExecutionConfig(
        output_mode=output_mode,
        max_runtime=max_runtime,
        metadata_mode=metadata_mode,
    )


class TestBenchmark(unittest.TestCase):
    def setUp(self):
        self.fps_floor = 30
        self.job_id = "test-job-123"
        # Use internal types with resolved pipeline information
        self.pipeline_benchmark_specs = [
            create_internal_density_spec(
                pipeline_id="/pipelines/pipeline-test1/variants/variant-1",
                pipeline_name="Test Pipeline 1",
                stream_rate=50,
            ),
            create_internal_density_spec(
                pipeline_id="/pipelines/pipeline-test2/variants/variant-2",
                pipeline_name="Test Pipeline 2",
                stream_rate=50,
            ),
        ]
        self.benchmark = Benchmark()

    @patch("benchmark.PipelineManager")
    def test_run_successful_scaling(self, mock_pipeline_manager_cls):
        # Return tuple with 4 elements: command, video_output_paths, live_stream_urls, metadata_file_paths
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = PipelineCommand(
            command="",
            video_output_paths={},
            live_stream_urls={},
            metadata_file_paths={},
            streams_per_pipeline={},
        )
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        # Expected result uses InternalPipelineStreamSpec with variant path format
        expected_result = BenchmarkResult(
            n_streams=3,
            streams_per_pipeline=[
                InternalPipelineStreamSpec(
                    id="/pipelines/pipeline-test1/variants/variant-1",
                    streams=2,
                ),
                InternalPipelineStreamSpec(
                    id="/pipelines/pipeline-test2/variants/variant-2",
                    streams=1,
                ),
            ],
            per_stream_fps=31.0,
            video_output_paths={},
        )

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                # First call with 1 stream
                PipelineResult(
                    total_fps=30, per_stream_fps=30, num_streams=1, exit_code=0
                ),
                # Second call with 2 streams
                PipelineResult(
                    total_fps=80, per_stream_fps=40, num_streams=2, exit_code=0
                ),
                # Third call with 4 streams
                PipelineResult(
                    total_fps=100, per_stream_fps=25, num_streams=4, exit_code=0
                ),
                # Fourth call with 3 streams
                PipelineResult(
                    total_fps=93, per_stream_fps=31, num_streams=3, exit_code=0
                ),
                # Fifth call with 3 streams
                PipelineResult(
                    total_fps=93, per_stream_fps=31, num_streams=3, exit_code=0
                ),
                # Sixth call with 4 streams
                PipelineResult(
                    total_fps=100, per_stream_fps=25, num_streams=4, exit_code=0
                ),
            ]

            result = self.benchmark.run(
                self.pipeline_benchmark_specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(),
                job_id=self.job_id,
            )

            self.assertEqual(result, expected_result)

    def test_invalid_ratio_raises_value_error(self):
        # Set stream rates to create an invalid ratio
        self.pipeline_benchmark_specs[0].stream_rate = 60
        self.pipeline_benchmark_specs[1].stream_rate = 50

        total_ratio = sum(spec.stream_rate for spec in self.pipeline_benchmark_specs)

        with self.assertRaises(
            ValueError,
            msg=f"Pipeline stream_rate ratios must sum to 100%, got {total_ratio}%",
        ):
            self.benchmark.run(
                self.pipeline_benchmark_specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(),
                job_id=self.job_id,
            )

    @patch("benchmark.PipelineManager")
    def test_zero_total_fps(self, mock_pipeline_manager_cls):
        # Return tuple with 4 elements
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = PipelineCommand(
            command="",
            video_output_paths={},
            live_stream_urls={},
            metadata_file_paths={},
            streams_per_pipeline={},
        )
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                # First call with 1 stream
                PipelineResult(
                    total_fps=0, per_stream_fps=30, num_streams=1, exit_code=0
                ),
            ]
            with self.assertRaises(
                RuntimeError, msg="Pipeline returned zero or invalid FPS metrics."
            ):
                _ = self.benchmark.run(
                    self.pipeline_benchmark_specs,
                    fps_floor=self.fps_floor,
                    execution_config=create_internal_execution_config(),
                    job_id=self.job_id,
                )

    def test_calculate_streams_per_pipeline(self):
        # Use internal types with resolved pipeline information
        pipeline_benchmark_specs = [
            create_internal_density_spec(
                pipeline_id="/pipelines/pipeline-1/variants/variant-1",
                pipeline_name="Pipeline 1",
                stream_rate=50,
            ),
            create_internal_density_spec(
                pipeline_id="/pipelines/pipeline-2/variants/variant-2",
                pipeline_name="Pipeline 2",
                stream_rate=30,
            ),
            create_internal_density_spec(
                pipeline_id="/pipelines/pipeline-3/variants/variant-3",
                pipeline_name="Pipeline 3",
                stream_rate=20,
            ),
        ]

        # Test with total_streams = 10
        total_streams = 10
        expected_streams = [5, 3, 2]  # 50%, 30%, 20% of 10
        calculated_streams = self.benchmark._calculate_streams_per_pipeline(
            pipeline_benchmark_specs, total_streams
        )
        self.assertEqual(calculated_streams, expected_streams)

        # Test with total_streams = 7
        total_streams = 7
        expected_streams = [4, 2, 1]  # Rounded distribution
        calculated_streams = self.benchmark._calculate_streams_per_pipeline(
            pipeline_benchmark_specs, total_streams
        )
        self.assertEqual(calculated_streams, expected_streams)

    def test_cancel_benchmark(self):
        self.benchmark.cancel()
        self.assertTrue(self.benchmark.runner.is_cancelled())

    def test_live_stream_output_mode_raises_error(self):
        """Test that live_stream output mode raises ValueError for density tests."""
        with self.assertRaises(ValueError) as context:
            self.benchmark.run(
                self.pipeline_benchmark_specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(
                    output_mode=InternalOutputMode.LIVE_STREAM
                ),
                job_id=self.job_id,
            )

        self.assertIn(
            "Density tests do not support output_mode='live_stream'",
            str(context.exception),
        )

    @patch("benchmark.PipelineManager")
    def test_run_with_file_output_mode(self, mock_pipeline_manager_cls):
        """Test benchmark run with file output mode."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = PipelineCommand(
            command="",
            video_output_paths={
                "/pipelines/pipeline-test1/variants/variant-1": "/output/file.mp4"
            },
            live_stream_urls={},
            metadata_file_paths={},
            streams_per_pipeline={},
        )
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                # Iter 1: n_streams=1, exponential phase
                PipelineResult(
                    total_fps=30, per_stream_fps=30, num_streams=1, exit_code=0
                ),
                # Iter 2: n_streams=2, drops below floor, switch to binary search
                PipelineResult(
                    total_fps=40, per_stream_fps=20, num_streams=2, exit_code=0
                ),
                # Iter 3: n_streams=1 (binary search midpoint)
                PipelineResult(
                    total_fps=30, per_stream_fps=30, num_streams=1, exit_code=0
                ),
                # Iter 4: n_streams=2 (binary search continues)
                PipelineResult(
                    total_fps=40, per_stream_fps=20, num_streams=2, exit_code=0
                ),
            ]

            result = self.benchmark.run(
                self.pipeline_benchmark_specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(
                    output_mode=InternalOutputMode.FILE,
                    max_runtime=0,
                    metadata_mode=InternalMetadataMode.DISABLED,
                ),
                job_id=self.job_id,
            )

            self.assertIsInstance(result, BenchmarkResult)

    @patch("benchmark.PipelineManager")
    def test_run_with_disabled_output_and_max_runtime(self, mock_pipeline_manager_cls):
        """Test benchmark run with disabled output and max_runtime > 0."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = PipelineCommand(
            command="",
            video_output_paths={},
            live_stream_urls={},
            metadata_file_paths={},
            streams_per_pipeline={},
        )
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                # Iter 1: n_streams=1, exponential phase
                PipelineResult(
                    total_fps=30, per_stream_fps=30, num_streams=1, exit_code=0
                ),
                # Iter 2: n_streams=2, drops below floor, switch to binary search
                PipelineResult(
                    total_fps=40, per_stream_fps=20, num_streams=2, exit_code=0
                ),
                # Iter 3: n_streams=1 (binary search midpoint)
                PipelineResult(
                    total_fps=30, per_stream_fps=30, num_streams=1, exit_code=0
                ),
                # Iter 4: n_streams=2 (binary search continues)
                PipelineResult(
                    total_fps=40, per_stream_fps=20, num_streams=2, exit_code=0
                ),
            ]

            result = self.benchmark.run(
                self.pipeline_benchmark_specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(
                    output_mode=InternalOutputMode.DISABLED,
                    max_runtime=60,
                    metadata_mode=InternalMetadataMode.DISABLED,
                ),
                job_id=self.job_id,
            )

            self.assertIsInstance(result, BenchmarkResult)

    @patch("benchmark.PipelineManager")
    def test_run_with_inline_graph(self, mock_pipeline_manager_cls):
        """Test benchmark run with inline graph pipeline source."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = PipelineCommand(
            command="",
            video_output_paths={},
            live_stream_urls={},
            metadata_file_paths={},
            streams_per_pipeline={},
        )
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        # Create specs with inline graph format (synthetic ID)
        inline_specs = [
            create_internal_density_spec(
                pipeline_id="__graph-1234567890abcdef",
                pipeline_name="__graph-1234567890abcdef",
                stream_rate=100,
            ),
        ]

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                # First run - above fps_floor
                PipelineResult(
                    total_fps=60, per_stream_fps=60, num_streams=1, exit_code=0
                ),
                # Second run - drops below fps_floor
                PipelineResult(
                    total_fps=50, per_stream_fps=25, num_streams=2, exit_code=0
                ),
                # Binary search midpoint
                PipelineResult(
                    total_fps=60, per_stream_fps=60, num_streams=1, exit_code=0
                ),
                # Continue binary search
                PipelineResult(
                    total_fps=50, per_stream_fps=25, num_streams=2, exit_code=0
                ),
            ]

            result = self.benchmark.run(
                inline_specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(),
                job_id=self.job_id,
            )

            self.assertIsInstance(result, BenchmarkResult)
            # Check that pipeline ID starts with __graph- prefix for inline graphs
            self.assertTrue(result.streams_per_pipeline[0].id.startswith("__graph-"))

    @patch("benchmark.PipelineManager")
    def test_result_pipeline_ids_use_variant_path_format(
        self, mock_pipeline_manager_cls
    ):
        """Test that result pipeline IDs use the correct variant path format."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = PipelineCommand(
            command="",
            video_output_paths={},
            live_stream_urls={},
            metadata_file_paths={},
            streams_per_pipeline={},
        )
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                # Single iteration that meets fps_floor then exits
                PipelineResult(
                    total_fps=60, per_stream_fps=60, num_streams=1, exit_code=0
                ),
                PipelineResult(
                    total_fps=50, per_stream_fps=25, num_streams=2, exit_code=0
                ),
                PipelineResult(
                    total_fps=60, per_stream_fps=60, num_streams=1, exit_code=0
                ),
                PipelineResult(
                    total_fps=50, per_stream_fps=25, num_streams=2, exit_code=0
                ),
            ]

            result = self.benchmark.run(
                self.pipeline_benchmark_specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(),
                job_id=self.job_id,
            )

            # Check that all pipeline IDs use the variant path format
            for stream_spec in result.streams_per_pipeline:
                self.assertIsInstance(stream_spec, InternalPipelineStreamSpec)
                self.assertTrue(
                    stream_spec.id.startswith("/pipelines/"),
                    f"Expected pipeline ID to start with '/pipelines/', got: {stream_spec.id}",
                )
                self.assertIn(
                    "/variants/",
                    stream_spec.id,
                    f"Expected pipeline ID to contain '/variants/', got: {stream_spec.id}",
                )

    @patch("benchmark.PipelineManager")
    def test_mixed_variant_and_inline_specs(self, mock_pipeline_manager_cls):
        """Test benchmark with mixed variant reference and inline graph specs."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = PipelineCommand(
            command="",
            video_output_paths={},
            live_stream_urls={},
            metadata_file_paths={},
            streams_per_pipeline={},
        )
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        # Mix of variant reference format and inline graph format
        mixed_specs = [
            create_internal_density_spec(
                pipeline_id="/pipelines/pipeline-1/variants/variant-1",
                pipeline_name="Pipeline 1",
                stream_rate=50,
            ),
            create_internal_density_spec(
                pipeline_id="__graph-abcdef1234567890",
                pipeline_name="__graph-abcdef1234567890",
                stream_rate=50,
            ),
        ]

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                PipelineResult(
                    total_fps=60, per_stream_fps=60, num_streams=1, exit_code=0
                ),
                PipelineResult(
                    total_fps=50, per_stream_fps=25, num_streams=2, exit_code=0
                ),
                PipelineResult(
                    total_fps=60, per_stream_fps=60, num_streams=1, exit_code=0
                ),
                PipelineResult(
                    total_fps=50, per_stream_fps=25, num_streams=2, exit_code=0
                ),
            ]

            result = self.benchmark.run(
                mixed_specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(),
                job_id=self.job_id,
            )

            self.assertIsInstance(result, BenchmarkResult)
            self.assertEqual(len(result.streams_per_pipeline), 2)

            # First should be variant path format
            self.assertTrue(result.streams_per_pipeline[0].id.startswith("/pipelines/"))
            # Second should be inline graph format
            self.assertTrue(result.streams_per_pipeline[1].id.startswith("__graph-"))


class TestBenchmarkLatencyTracerMetrics(unittest.TestCase):
    """Verify that BenchmarkResult carries the best-config tracer sample."""

    def setUp(self):
        self.fps_floor = 30
        self.job_id = "test-job-latency"
        self.specs = [
            create_internal_density_spec(
                pipeline_id="/pipelines/p/variants/cpu",
                pipeline_name="p",
                stream_rate=100,
            ),
        ]

    @staticmethod
    def _sample(value: float) -> LatencyTracerSample:
        """Build a sentinel LatencyTracerSample identifiable by `value`."""
        return LatencyTracerSample(
            interval_ms=value,
            avg_ms=value,
            min_ms=value,
            max_ms=value,
            latency_ms=value,
        )

    @patch("benchmark.PipelineManager")
    def test_best_config_tracer_snapshot_is_returned_not_last_iteration(
        self, mock_pipeline_manager_cls
    ):
        """
        The tracer metrics on BenchmarkResult must come from the best
        (highest fps-passing) iteration, not from the final iteration
        that decided to stop the search by dropping below fps_floor.
        """
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = PipelineCommand(
            command="",
            video_output_paths={},
            live_stream_urls={},
            metadata_file_paths={},
            streams_per_pipeline={},
        )
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        benchmark = Benchmark(enable_latency_metrics=True)

        # Iteration sequence produced by the search on a single pipeline
        # with fps_floor=30: n_streams=1, 2, 4, 3, 4. Best = iter #4
        # (n_streams=3 at 31 fps).
        fps_plan = [
            (1, 30),  # iter 1: best=1
            (2, 40),  # iter 2: best=2
            (4, 25),  # iter 3: drop below floor → switch to binary
            (3, 31),  # iter 4: best=3  <-- tracer snapshot must come from here
            (4, 25),  # iter 5: final iteration, below floor
        ]

        run_outputs = [
            PipelineResult(
                total_fps=fps * n,
                per_stream_fps=fps,
                num_streams=n,
                exit_code=0,
            )
            for n, fps in fps_plan
        ]

        # Each iteration leaves a distinct sample on the runner. The
        # benchmark snapshots the map at iteration end (before the next
        # run resets it). Sentinel value = iteration index (1-based).
        per_iteration_samples = [
            {"stream_a": self._sample(float(idx + 1))} for idx in range(len(fps_plan))
        ]

        call_index = {"i": 0}

        def fake_run(*args, **kwargs):
            """Mimic PipelineRunner: set the tracer map, then return the result."""
            i = call_index["i"]
            benchmark.runner.latency_tracer_metrics = per_iteration_samples[i]
            call_index["i"] = i + 1
            return run_outputs[i]

        with patch.object(benchmark.runner, "run", side_effect=fake_run):
            result = benchmark.run(
                self.specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(),
                job_id=self.job_id,
            )

        # Best config landed at iteration #4 (index 3) with n_streams=3.
        self.assertEqual(result.n_streams, 3)
        self.assertIsNotNone(result.latency_tracer_metrics)
        assert result.latency_tracer_metrics is not None
        self.assertEqual(
            result.latency_tracer_metrics["stream_a"].avg_ms,
            4.0,
            "Expected tracer sample from iteration 4 (best config), "
            "got a sample from a different iteration.",
        )

    @patch("benchmark.PipelineManager")
    def test_tracer_snapshot_is_decoupled_from_runner_map(
        self, mock_pipeline_manager_cls
    ):
        """
        After the benchmark returns, mutating the runner's tracer map
        must not affect the snapshot stored on BenchmarkResult.
        """
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = PipelineCommand(
            command="",
            video_output_paths={},
            live_stream_urls={},
            metadata_file_paths={},
            streams_per_pipeline={},
        )
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        benchmark = Benchmark(enable_latency_metrics=True)

        # Single-pipeline 5-iteration plan identical to the test above.
        fps_plan = [(1, 30), (2, 40), (4, 25), (3, 31), (4, 25)]
        run_outputs = [
            PipelineResult(
                total_fps=fps * n,
                per_stream_fps=fps,
                num_streams=n,
                exit_code=0,
            )
            for n, fps in fps_plan
        ]
        call_index = {"i": 0}

        def fake_run(*args, **kwargs):
            i = call_index["i"]
            benchmark.runner.latency_tracer_metrics = {
                "stream_a": self._sample(float(i + 1))
            }
            call_index["i"] = i + 1
            return run_outputs[i]

        with patch.object(benchmark.runner, "run", side_effect=fake_run):
            result = benchmark.run(
                self.specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(),
                job_id=self.job_id,
            )

        assert result.latency_tracer_metrics is not None
        # Overwrite the runner's map post-facto — the snapshot must stand.
        benchmark.runner.latency_tracer_metrics = {"stream_a": self._sample(99.0)}
        self.assertEqual(result.latency_tracer_metrics["stream_a"].avg_ms, 4.0)

    @patch("benchmark.PipelineManager")
    def test_tracer_disabled_leaves_result_metrics_none(
        self, mock_pipeline_manager_cls
    ):
        """When the tracer is off, BenchmarkResult.latency_tracer_metrics stays None."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = PipelineCommand(
            command="",
            video_output_paths={},
            live_stream_urls={},
            metadata_file_paths={},
            streams_per_pipeline={},
        )
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        benchmark = Benchmark(enable_latency_metrics=False)

        with patch.object(benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                PipelineResult(
                    total_fps=30, per_stream_fps=30, num_streams=1, exit_code=0
                ),
                PipelineResult(
                    total_fps=40, per_stream_fps=20, num_streams=2, exit_code=0
                ),
                PipelineResult(
                    total_fps=30, per_stream_fps=30, num_streams=1, exit_code=0
                ),
                PipelineResult(
                    total_fps=40, per_stream_fps=20, num_streams=2, exit_code=0
                ),
            ]

            result = benchmark.run(
                self.specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(),
                job_id=self.job_id,
            )

        self.assertIsNone(result.latency_tracer_metrics)


if __name__ == "__main__":
    unittest.main()
