import unittest
from unittest.mock import patch

from benchmark import Benchmark, BenchmarkResult
from gstpipeline import GstPipeline
from pipeline_runner import PipelineRunResult


class TestPipeline(GstPipeline):
    def __init__(self, pipeline_description):
        super().__init__(pipeline_description=pipeline_description)

    def evaluate(self, regular_channels, inference_channels):
        return " ".join(
            [self._pipeline_description] * (inference_channels + regular_channels)
        )


class TestBenchmark(unittest.TestCase):
    def setUp(self):
        test_pipeline_description = (
            "videotestsrc "
            " num-buffers=5 "
            " pattern=snow ! "
            "videoconvert ! "
            "gvafpscounter ! "
            "fakesink"
        )
        self.pipeline_cls = TestPipeline(pipeline_description=test_pipeline_description)
        self.fps_floor = 30.0
        self.rate = 50
        self.benchmark = Benchmark()

    def test_run_successful_scaling(self):
        expected_result = BenchmarkResult(
            n_streams=3,
            ai_streams=2,
            non_ai_streams=1,
            per_stream_fps=31.0,
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

            result = self.benchmark.run(self.pipeline_cls, self.fps_floor, self.rate)

            self.assertEqual(result, expected_result)

    def test_zero_total_fps(self):
        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [
                # First call with 1 stream
                PipelineRunResult(total_fps=0, per_stream_fps=30, num_streams=1),
            ]
            with self.assertRaises(
                RuntimeError, msg="Pipeline returned zero or invalid FPS metrics."
            ):
                _ = self.benchmark.run(self.pipeline_cls, self.fps_floor, self.rate)

    def test_pipeline_returns_none(self):
        with patch.object(self.benchmark.runner, "run") as mock_runner:
            mock_runner.side_effect = [None]

            with self.assertRaises(
                RuntimeError, msg="Pipeline runner returned invalid results."
            ):
                _ = self.benchmark.run(self.pipeline_cls, self.fps_floor, self.rate)


if __name__ == "__main__":
    unittest.main()
