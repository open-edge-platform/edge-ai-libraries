import unittest
from unittest.mock import patch

from api.api_schemas import ExecutionConfig, OutputMode
from benchmark import (
    Benchmark,
    BenchmarkResult,
    PipelineDensitySpec,
    PipelinePerformanceSpec,
)
from pipeline_runner import PipelineRunResult


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
        # Return tuple with 3 elements: command, video_output_paths, live_stream_urls
        mock_build_command.return_value = ("", {}, {})
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
                execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
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
                execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
            )

    @patch("benchmark.pipeline_manager.build_pipeline_command")
    def test_zero_total_fps(self, mock_build_command):
        # Return tuple with 3 elements
        mock_build_command.return_value = ("", {}, {})
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
                    execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
                )

    @patch("benchmark.pipeline_manager.build_pipeline_command")
    def test_pipeline_returns_none(self, mock_build_command):
        # Return tuple with 3 elements
        mock_build_command.return_value = ("", {}, {})
        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [None]

            with self.assertRaises(
                RuntimeError, msg="Pipeline runner returned invalid results."
            ):
                _ = self.benchmark.run(
                    self.pipeline_benchmark_specs,
                    fps_floor=self.fps_floor,
                    execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
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

    def test_live_stream_output_mode_raises_error(self):
        """Test that live_stream output mode raises ValueError for density tests."""
        with self.assertRaises(ValueError) as context:
            self.benchmark.run(
                self.pipeline_benchmark_specs,
                fps_floor=self.fps_floor,
                execution_config=ExecutionConfig(output_mode=OutputMode.LIVE_STREAM),
            )

        self.assertIn(
            "Density tests do not support output_mode='live_stream'",
            str(context.exception),
        )

    @patch("benchmark.pipeline_manager.build_pipeline_command")
    def test_run_with_file_output_mode(self, mock_build_command):
        """Test benchmark run with file output mode."""
        mock_build_command.return_value = (
            "",
            {"pipeline-test1": ["/output/file.mp4"]},
            {},
        )

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            # The benchmark algorithm:
            # 1. n_streams=1, fps=30 >= floor=30 -> best_config=(1,...), scale up to n_streams=2
            # 2. n_streams=2, fps=20 < 30 -> switch to binary search, higher_bound=2, lower_bound=1, n_streams=1
            # 3. n_streams=1, fps=30 >= 30 -> best_config=(1,...), lower_bound=2
            # 4. lower_bound(2) > higher_bound(1) -> exit loop
            # So we need exactly 3 results, but the last iteration sets lower_bound=2 which > higher_bound=1
            # Actually after step 3: lower_bound becomes n_streams+1 = 2, higher_bound stays 1
            # Since 2 > 1, loop exits. So 3 results should be enough but let's trace again:

            # Actually the issue is the binary search logic. Let me trace more carefully:
            # Initial: n_streams=1, exponential=True, lower_bound=1, higher_bound=-1
            # Iter 1: n_streams=1, fps=30 >= 30 -> best_config=(1,...), n_streams=2
            # Iter 2: n_streams=2, fps=20 < 30 -> exponential=False, higher_bound=2, lower_bound=max(1,1)=1, n_streams=(1+2)//2=1
            # Iter 3: n_streams=1, fps=30 >= 30 -> best_config=(1,...), lower_bound=2
            # Check: lower_bound(2) > higher_bound(2)? No, 2 > 2 is False
            # Wait, after iter 2: higher_bound=2. After iter 3: lower_bound=n_streams+1=2
            # Check: 2 > 2? False. So n_streams=(2+2)//2=2
            # Iter 4: n_streams=2 (need another result)

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
                execution_config=ExecutionConfig(
                    output_mode=OutputMode.FILE, max_runtime=0
                ),
            )

            self.assertIsInstance(result, BenchmarkResult)

    @patch("benchmark.pipeline_manager.build_pipeline_command")
    def test_run_with_disabled_output_and_max_runtime(self, mock_build_command):
        """Test benchmark run with disabled output and max_runtime > 0."""
        mock_build_command.return_value = ("", {}, {})

        with patch.object(self.benchmark.runner, "run") as mock_runner:
            # Same logic as above - need 4 results for the benchmark to complete
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
                execution_config=ExecutionConfig(
                    output_mode=OutputMode.DISABLED, max_runtime=60
                ),
            )

            self.assertIsInstance(result, BenchmarkResult)


if __name__ == "__main__":
    unittest.main()
