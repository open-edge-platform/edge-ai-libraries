import unittest
from unittest.mock import patch

from benchmark import (
    Benchmark,
    BenchmarkResult,
    PipelineDensitySpec,
    PipelinePerformanceSpec,
)
from pipeline_runner import PipelineRunResult
from api.api_schemas import VideoOutputConfig


class TestBenchmark(unittest.TestCase):
    def setUp(self):
        self.fps_floor = 30
        self.pipeline_benchmark_specs = [
            PipelineDensitySpec(id="pipeline-test1", stream_rate=50),
            PipelineDensitySpec(id="pipeline-test2", stream_rate=50),
        ]
        self.benchmark = Benchmark()

    @patch("benchmark.pipeline_manager.build_pipeline_command")
    def test_run_successful_scaling(self, mock_build_command):
        mock_build_command.return_value = ("", {})  # No actual command needed for test
        expected_result = BenchmarkResult(
            n_streams=3,
            streams_per_pipeline=[
                PipelinePerformanceSpec(
                    id="pipeline-test1",
                    streams=2,
                ),
                PipelinePerformanceSpec(
                    id="pipeline-test2",
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
                # Fourth call with 3 streams
                PipelineRunResult(
                    total_fps=93,
                    per_stream_fps=31,
                    num_streams=3,
                ),
                # Fifth call with 4 streams
                PipelineRunResult(
                    total_fps=100,
                    per_stream_fps=25,
                    num_streams=4,
                ),
            ]

            result = self.benchmark.run(
                self.pipeline_benchmark_specs,
                fps_floor=self.fps_floor,
                video_config=VideoOutputConfig(enabled=False),
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
                video_config=VideoOutputConfig(enabled=False),
            )

    @patch("benchmark.pipeline_manager.build_pipeline_command")
    def test_zero_total_fps(self, mock_build_command):
        mock_build_command.return_value = ("", {})  # No actual command needed for test
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
                    video_config=VideoOutputConfig(enabled=False),
                )

    @patch("benchmark.pipeline_manager.build_pipeline_command")
    def test_pipeline_returns_none(self, mock_build_command):
        mock_build_command.return_value = ("", {})  # No actual command needed for test
        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [None]

            with self.assertRaises(
                RuntimeError, msg="Pipeline runner returned invalid results."
            ):
                _ = self.benchmark.run(
                    self.pipeline_benchmark_specs,
                    fps_floor=self.fps_floor,
                    video_config=VideoOutputConfig(enabled=False),
                )

    def test_calculate_streams_per_pipeline(self):
        pipeline_benchmark_specs = [
            PipelineDensitySpec(id="pipeline-1", stream_rate=50),
            PipelineDensitySpec(id="pipeline-2", stream_rate=30),
            PipelineDensitySpec(id="pipeline-3", stream_rate=20),
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


if __name__ == "__main__":
    unittest.main()
