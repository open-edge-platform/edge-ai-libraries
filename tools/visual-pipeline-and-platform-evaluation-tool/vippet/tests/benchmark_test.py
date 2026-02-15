import unittest
from unittest.mock import patch, MagicMock

from api.api_schemas import (
    PipelineStreamSpec,
    PipelineGraph,
    Node,
    Edge,
)
from benchmark import (
    Benchmark,
    BenchmarkResult,
)
from graph import Graph
from internal_types import (
    InternalExecutionConfig,
    InternalOutputMode,
    InternalPipelineDensitySpec,
)
from pipeline_runner import PipelineRunResult


def create_simple_graph() -> Graph:
    """Helper to create a simple test pipeline Graph object."""
    pipeline_graph = PipelineGraph(
        nodes=[
            Node(id="0", type="filesrc", data={"location": "/videos/test.mp4"}),
            Node(id="1", type="fakesink", data={}),
        ],
        edges=[
            Edge(id="0", source="0", target="1"),
        ],
    )
    return Graph.from_dict(pipeline_graph.model_dump())


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
) -> InternalExecutionConfig:
    """Helper to create InternalExecutionConfig for testing."""
    return InternalExecutionConfig(
        output_mode=output_mode,
        max_runtime=max_runtime,
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
        # Return tuple with 3 elements: command, video_output_paths, live_stream_urls
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = ("", {}, {})
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        # Expected result uses PipelineStreamSpec with variant path format
        expected_result = BenchmarkResult(
            n_streams=3,
            streams_per_pipeline=[
                PipelineStreamSpec(
                    id="/pipelines/pipeline-test1/variants/variant-1",
                    streams=2,
                ),
                PipelineStreamSpec(
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
                PipelineRunResult(
                    total_fps=30,
                    per_stream_fps=30,
                    num_streams=1,
                ),
                # Second call with 2 streams
                PipelineRunResult(
                    total_fps=80,
                    per_stream_fps=40,
                    num_streams=2,
                ),
                # Third call with 4 streams
                PipelineRunResult(
                    total_fps=100,
                    per_stream_fps=25,
                    num_streams=4,
                ),
                # Fourth call with 3 streams
                PipelineRunResult(
                    total_fps=93,
                    per_stream_fps=31,
                    num_streams=3,
                ),
                # Fifth call with 3 streams
                PipelineRunResult(
                    total_fps=93,
                    per_stream_fps=31,
                    num_streams=3,
                ),
                # Sixth call with 4 streams
                PipelineRunResult(
                    total_fps=100,
                    per_stream_fps=25,
                    num_streams=4,
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
        # Return tuple with 3 elements
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = ("", {}, {})
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                # First call with 1 stream
                PipelineRunResult(total_fps=0, per_stream_fps=30, num_streams=1),
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

    @patch("benchmark.PipelineManager")
    def test_pipeline_returns_none(self, mock_pipeline_manager_cls):
        # Return tuple with 3 elements
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = ("", {}, {})
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [None]

            with self.assertRaises(
                RuntimeError, msg="Pipeline runner returned invalid results."
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
        mock_manager_instance.build_pipeline_command.return_value = (
            "",
            {"/pipelines/pipeline-test1/variants/variant-1": ["/output/file.mp4"]},
            {},
        )
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                # Iter 1: n_streams=1, exponential phase
                PipelineRunResult(total_fps=30, per_stream_fps=30, num_streams=1),
                # Iter 2: n_streams=2, drops below floor, switch to binary search
                PipelineRunResult(total_fps=40, per_stream_fps=20, num_streams=2),
                # Iter 3: n_streams=1 (binary search midpoint)
                PipelineRunResult(total_fps=30, per_stream_fps=30, num_streams=1),
                # Iter 4: n_streams=2 (binary search continues)
                PipelineRunResult(total_fps=40, per_stream_fps=20, num_streams=2),
            ]

            result = self.benchmark.run(
                self.pipeline_benchmark_specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(
                    output_mode=InternalOutputMode.FILE, max_runtime=0
                ),
                job_id=self.job_id,
            )

            self.assertIsInstance(result, BenchmarkResult)

    @patch("benchmark.PipelineManager")
    def test_run_with_disabled_output_and_max_runtime(self, mock_pipeline_manager_cls):
        """Test benchmark run with disabled output and max_runtime > 0."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = ("", {}, {})
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                # Iter 1: n_streams=1, exponential phase
                PipelineRunResult(total_fps=30, per_stream_fps=30, num_streams=1),
                # Iter 2: n_streams=2, drops below floor, switch to binary search
                PipelineRunResult(total_fps=40, per_stream_fps=20, num_streams=2),
                # Iter 3: n_streams=1 (binary search midpoint)
                PipelineRunResult(total_fps=30, per_stream_fps=30, num_streams=1),
                # Iter 4: n_streams=2 (binary search continues)
                PipelineRunResult(total_fps=40, per_stream_fps=20, num_streams=2),
            ]

            result = self.benchmark.run(
                self.pipeline_benchmark_specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(
                    output_mode=InternalOutputMode.DISABLED, max_runtime=60
                ),
                job_id=self.job_id,
            )

            self.assertIsInstance(result, BenchmarkResult)

    @patch("benchmark.PipelineManager")
    def test_run_with_inline_graph(self, mock_pipeline_manager_cls):
        """Test benchmark run with inline graph pipeline source."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.build_pipeline_command.return_value = ("", {}, {})
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
                PipelineRunResult(total_fps=60, per_stream_fps=60, num_streams=1),
                # Second run - drops below fps_floor
                PipelineRunResult(total_fps=50, per_stream_fps=25, num_streams=2),
                # Binary search midpoint
                PipelineRunResult(total_fps=60, per_stream_fps=60, num_streams=1),
                # Continue binary search
                PipelineRunResult(total_fps=50, per_stream_fps=25, num_streams=2),
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
        mock_manager_instance.build_pipeline_command.return_value = ("", {}, {})
        mock_pipeline_manager_cls.return_value = mock_manager_instance

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                # Single iteration that meets fps_floor then exits
                PipelineRunResult(total_fps=60, per_stream_fps=60, num_streams=1),
                PipelineRunResult(total_fps=50, per_stream_fps=25, num_streams=2),
                PipelineRunResult(total_fps=60, per_stream_fps=60, num_streams=1),
                PipelineRunResult(total_fps=50, per_stream_fps=25, num_streams=2),
            ]

            result = self.benchmark.run(
                self.pipeline_benchmark_specs,
                fps_floor=self.fps_floor,
                execution_config=create_internal_execution_config(),
                job_id=self.job_id,
            )

            # Check that all pipeline IDs use the variant path format
            for stream_spec in result.streams_per_pipeline:
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
        mock_manager_instance.build_pipeline_command.return_value = ("", {}, {})
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
                PipelineRunResult(total_fps=60, per_stream_fps=60, num_streams=1),
                PipelineRunResult(total_fps=50, per_stream_fps=25, num_streams=2),
                PipelineRunResult(total_fps=60, per_stream_fps=60, num_streams=1),
                PipelineRunResult(total_fps=50, per_stream_fps=25, num_streams=2),
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


if __name__ == "__main__":
    unittest.main()
