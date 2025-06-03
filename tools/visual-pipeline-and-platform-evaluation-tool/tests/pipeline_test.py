import unittest
from pathlib import Path

from pipeline import GstPipeline, SmartNVRPipeline


class TestGstPipeline(unittest.TestCase):
    def setUp(self):
        self.pipeline = GstPipeline()

    def test_pipeline_property(self):
        with self.assertRaises(ValueError):
            self.pipeline.pipeline()

    def test_diagram_property(self):
        with self.assertRaises(ValueError):
            self.pipeline.diagram()

    def test_bounding_boxes_property(self):
        with self.assertRaises(ValueError):
            self.pipeline.bounding_boxes()

    def test_evaluate_method(self):
        with self.assertRaises(NotImplementedError):
            self.pipeline.evaluate(**{
                "constants": {},
                "parameters": {},
                "regular_channels": 1,
                "inference_channels": 1,
            })


class TestSmartNVRPipeline(unittest.TestCase):
    def setUp(self):
        self.pipeline = SmartNVRPipeline()
        self.constants = {
            "VIDEO_OUTPUT_PATH": "output.mp4",
            "VIDEO_PATH": "input.mp4",
            "OBJECT_DETECTION_MODEL_PATH": "model.xml",
            "OBJECT_DETECTION_MODEL_PROC": "model_proc.json",
        }
        self.regular_channels = 1
        self.inference_channels = 1

    def common_checks(self, result):
        # Check if the result is a string
        self.assertIsInstance(result, str)

        # Check that gst-launch-1.0 command is present
        self.assertTrue(result.startswith("gst-launch-1.0"))

        # Check that output is set
        self.assertIn("location=output.mp4", result)

        # Check that there are enough sinks
        for i in range(self.regular_channels + self.inference_channels):
            self.assertIn(f"sink_{i}", result)

        # Check that the number of inference channels is correct
        self.assertEqual(result.count("gvadetect"), self.inference_channels)
        self.assertEqual(result.count("gvatrack"), self.inference_channels)

    def test_evaluate_cpu(self):
        result = self.pipeline.evaluate(
            constants=self.constants,
            parameters={
                "object_detection_device": "CPU",
                "batch_size": 0,
                "inference_interval": 1,
                "nireq": 0,
            },
            regular_channels=self.regular_channels,
            inference_channels=self.inference_channels,
            elements=[
                ("va", "vacompositor", "..."),
                ("va", "vah264enc", "..."),
                ("va", "vah264dec", "..."),
                ("va", "vapostproc", "..."),
            ],
        )

        # Common checks
        self.common_checks(result)

        # Check that model proc is used
        self.assertIn("model-proc=model_proc.json", result)

        # Check that opencv is used for pre-processing
        self.assertIn("pre-process-backend=opencv", result)

    def test_evaluate_gpu(self):
        result = self.pipeline.evaluate(
            constants=self.constants,
            parameters={
                "object_detection_device": "GPU.1",
                "batch_size": 0,
                "inference_interval": 1,
                "nireq": 0,
            },
            regular_channels=self.regular_channels,
            inference_channels=self.inference_channels,
            elements=[
                ("va", "vacompositor", "..."),
                ("va", "vah264enc", "..."),
                ("va", "vah264dec", "..."),
                ("va", "vapostproc", "..."),
            ],
        )

        # Common checks
        self.common_checks(result)

        # Check that model proc is used
        self.assertIn("model-proc=model_proc.json", result)

        # Check that va-surface-sharing is used for pre-processing
        self.assertIn("pre-process-backend=va-surface-sharing", result)

        # Check that the right vaapi elements are used
        self.assertIn("varenderD129compositor", result)

    def test_evaluate_no_model_proc(self):
        result = self.pipeline.evaluate(
            constants={
                "VIDEO_OUTPUT_PATH": "output.mp4",
                "VIDEO_PATH": "input.mp4",
                "OBJECT_DETECTION_MODEL_PATH": "model.xml",
                "OBJECT_DETECTION_MODEL_PROC": None,
            },
            parameters={
                "object_detection_device": "CPU",
                "batch_size": 0,
                "inference_interval": 1,
                "nireq": 0,
            },
            regular_channels=self.regular_channels,
            inference_channels=self.inference_channels,
            elements=[
                ("va", "vacompositor", "..."),
                ("va", "vah264enc", "..."),
                ("va", "vah264dec", "..."),
                ("va", "vapostproc", "..."),
            ],
        )

        # Common checks
        self.common_checks(result)

        # Check that no model proc is used
        self.assertNotIn("model-proc=", result)


if __name__ == "__main__":
    unittest.main()
