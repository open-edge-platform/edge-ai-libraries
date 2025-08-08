import unittest
from unittest.mock import patch

from optimize import PipelineOptimizer
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


class TestPipelineOptimizer(unittest.TestCase):
    def setUp(self):
        self.constants = {"NUM_BUFFERS": "100"}
        self.param_grid = {"pattern": ["snow", "ball"]}
        self.pipeline = TestPipeline()

    @patch("optimize.run_pipeline_and_extract_metrics")
    def test_optimize(self, mock_run_metrics):
        metrics_list = [
            {
                "params": {"pattern": "snow"},
                "exit_code": 0,
                "total_fps": 100.0,
                "per_stream_fps": 5.0,
                "num_streams": 20,
            },
            {
                "params": {"pattern": "ball"},
                "exit_code": 1,
                "total_fps": 50.0,
                "per_stream_fps": 2.5,
                "num_streams": 20,
            },
        ]

        # Proper generator: yields nothing, returns metrics_list
        def fake_generator(*args, **kwargs):
            if False:
                yield  # This makes it a generator
            return metrics_list
        mock_run_metrics.side_effect = fake_generator

        optimizer = PipelineOptimizer(
            pipeline=self.pipeline,
            constants=self.constants,
            param_grid=self.param_grid,
            channels=2,
        )
        optimizer.run_without_live_preview()
        self.assertEqual(len(optimizer.results), 2)
        self.assertEqual(optimizer.results[0].params["pattern"], "snow")
        self.assertEqual(optimizer.results[1].exit_code, 1)


if __name__ == "__main__":
    unittest.main()
