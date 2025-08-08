import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))
from benchmark import Benchmark
from gstpipeline import GstPipeline

class TestPipeline(GstPipeline):
    def __init__(self):
        super().__init__()
        self._pipeline = (
            "videotestsrc "
            " num-buffers={NUM_BUFFERS} "
            " pattern={pattern} ! "
            "videoconvert ! "
            "gvafpscounter ! "
            "fakesink"
        )

    def evaluate(self, constants, parameters, inference_channels, regular_channels):
        return "gst-launch-1.0 -q " + " ".join(
            [self._pipeline.format(**parameters, **constants)]
            * (inference_channels + regular_channels)
        )


class TestBenchmark(unittest.TestCase):
    def setUp(self):
        self.video_path = "test_video.mp4"
        self.pipeline_cls = TestPipeline
        self.fps_floor = 30.0
        self.rate = 50
        self.parameters = {"object_detection_device": "cpu"}
        self.constants = {"const1": "value1"}
        self.elements = [("element1", "type1", "name1")]
        self.benchmark = Benchmark(
            video_path=self.video_path,
            pipeline_cls=self.pipeline_cls,
            fps_floor=self.fps_floor,
            rate=self.rate,
            parameters=self.parameters,
            constants=self.constants,
            elements=self.elements,
        )
    def test_run_successful_scaling(self):
        with patch.object(Benchmark, "_run_pipeline_and_extract_metrics") as mock_run:
            mock_run.side_effect = [
                # First call with 1 stream
                [
                    {
                        "params": {},
                        "exit_code": 0,
                        "total_fps": 30,
                        "per_stream_fps": 30,
                        "num_streams": 1,
                    }
                ],
                # Second call with 2 streams
                [
                    {
                        "params": {},
                        "exit_code": 0,
                        "total_fps": 168,
                        "per_stream_fps": 28,
                        "num_streams": 6,
                    }
                ],
                # Third call with 3 streams
                [
                    {
                        "params": {},
                        "exit_code": 0,
                        "total_fps": 155,
                        "per_stream_fps": 31,
                        "num_streams": 5,
                    }
                ],
                []
            ]
            result = self.benchmark.run()
            self.assertEqual(result, (5, 3, 2, 31))

    def test_zero_total_fps(self):
        with patch.object(Benchmark, "_run_pipeline_and_extract_metrics") as mock_run:
            mock_run.side_effect = [
                # First call with 1 stream
                [
                    {
                        "params": {},
                        "exit_code": 0,
                        "total_fps": 0,
                        "per_stream_fps": 30,
                        "num_streams": 1,
                    }
                ],
                []
            ]
            result = self.benchmark.run()
            self.assertEqual(result, (0, 0, 0, 0.0))

    def test_invalid_fps(self):
        with patch.object(Benchmark, "_run_pipeline_and_extract_metrics") as mock_run:
            mock_run.side_effect = [
                # First call with 1 stream
                [
                    {
                        "params": {},
                        "exit_code": 0,
                        "total_fps": 0,
                        "per_stream_fps": "NaN",
                        "num_streams": 1,
                    }
                ],
                []
            ]
            result = self.benchmark.run()
            self.assertEqual(result, (0, 0, 0, 0.0))

    def test_decrementing_below_one(self):
        with patch.object(Benchmark, "_run_pipeline_and_extract_metrics") as mock_run:
            mock_run.side_effect = [
                # First call with 1 stream
                [
                    {
                        "params": {},
                        "exit_code": 0,
                        "total_fps": 60,
                        "per_stream_fps": 60,
                        "num_streams": 1,
                    }
                ],
                # Second call with 2 streams
                [
                    {
                        "params": {},
                        "exit_code": 0,
                        "total_fps": 10,
                        "per_stream_fps": 2,
                        "num_streams": 6,
                    }
                ],
                # Third call with 3 streams
                [
                    {
                        "params": {},
                        "exit_code": 0,
                        "total_fps": 8,
                        "per_stream_fps": 2,
                        "num_streams": 5,
                    }
                ],
                []
            ]
            result = self.benchmark.run()
            self.assertEqual(result, (0, 0, 0, 0.0))
    
    def test_pipeline_crash(self):
        with patch.object(Benchmark, "_run_pipeline_and_extract_metrics") as mock_run:
            mock_run.side_effect = [
                # First call with 1 stream
                [
                    {
                        "params": {},
                        "exit_code": 1,
                        "total_fps": 30,
                        "per_stream_fps": 30,
                        "num_streams": 1,
                    }
                ],
                []
            ]
            result = self.benchmark.run()
            self.assertEqual(result, (0, 0, 0, 0.0))
    
    def test_pipeline_returns_none(self):
        with patch.object(Benchmark, "_run_pipeline_and_extract_metrics") as mock_run:
            mock_run.side_effect = [
                [None]
            ]
            result = self.benchmark.run()
            self.assertEqual(result, (0, 0, 0, 0.0))

    def test_pipeline_low_fps(self):
        with patch.object(Benchmark, "_run_pipeline_and_extract_metrics") as mock_run:
            mock_run.side_effect = [
                [
                    {
                        "params": {},
                        "exit_code": 0,
                        "total_fps": 8,
                        "per_stream_fps": 8,
                        "num_streams": 1,
                    }
                ]
            ]
            result = self.benchmark.run()
            self.assertEqual(result, (0, 0, 0, 0.0))

if __name__ == "__main__":
    unittest.main()
