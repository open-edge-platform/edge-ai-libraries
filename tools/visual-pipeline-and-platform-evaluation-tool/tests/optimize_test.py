import unittest
from unittest.mock import MagicMock, patch

from optimize import OptimizationResult, PipelineOptimizer
from pipeline import GstPipeline


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


class TestPipelineOptimizer(unittest.TestCase):
    def setUp(self):
        self.constants = {"NUM_BUFFERS": "100"}
        self.param_grid = {"pattern": ["snow", "ball"]}
        self.pipeline = TestPipeline()

    @patch("optimize.run_pipeline_and_extract_metrics")
    def test_optimize(self, mock_run_metrics):
        mock_run_metrics.return_value = [
            {
                "params": {"pattern": "snow"},
                "exit_code": 0,
                "total_fps": 100.0,
                "per_stream_fps": 5.0,
            },
            {
                "params": {"pattern": "ball"},
                "exit_code": 1,
                "total_fps": 50.0,
                "per_stream_fps": 2.5,
            },
        ]
        optimizer = PipelineOptimizer(
            pipeline=self.pipeline,
            constants=self.constants,
            param_grid=self.param_grid,
            channels=2,
        )
        optimizer.optimize()
        self.assertEqual(len(optimizer.results), 2)
        self.assertEqual(optimizer.results[0].params["pattern"], "snow")
        self.assertEqual(optimizer.results[1].exit_code, 1)


if __name__ == "__main__":
    unittest.main()
