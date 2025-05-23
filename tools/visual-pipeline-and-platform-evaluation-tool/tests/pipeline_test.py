import unittest
from pathlib import Path

from pipeline import (
    SmartNVRPipeline,
)


class TestSmartNVRPipeline(unittest.TestCase):
    def setUp(self):
        self.pipeline = SmartNVRPipeline()
        self.constants = {
            "VIDEO_OUTPUT_PATH": "output.mp4",
            "VIDEO_PATH": "input.mp4",
            "OBJECT_DETECTION_MODEL_PATH": "model.xml",
            "OBJECT_DETECTION_MODEL_PROC": "model_proc.json",
        }

    def test_evaluate_cpu(self):
        regular_channels = 3
        inference_channels = 11

        result = self.pipeline.evaluate(
            constants=self.constants,
            parameters={
                "object_detection_device": "CPU",
                "batch_size": 0,
                "inference_interval": 1,
                "nireq": 0,
            },
            regular_channels=regular_channels,
            inference_channels=inference_channels,
            elements=[
                ("va", "vacompositor", "..."),
                ("va", "vah264enc", "..."),
                ("va", "vah264dec", "..."),
                ("va", "vapostproc", "..."),
            ],
        )

        # Check if the result is a string
        self.assertIsInstance(result, str)

        # Check that gst-launch-1.0 command is present
        self.assertTrue(result.startswith("gst-launch-1.0"))

        # Check that output is set
        self.assertIn("location=output.mp4", result)

        # Check that there are enough sinks
        for i in range(regular_channels + inference_channels):
            self.assertIn(f"sink_{i}", result)

        # Check that opencv is used for pre-processing
        self.assertIn("pre-process-backend=opencv", result)

        # Check that the number of inference channels is correct
        self.assertEqual(result.count("gvadetect"), inference_channels)
        self.assertEqual(result.count("gvatrack"), inference_channels)


if __name__ == "__main__":
    unittest.main()
