import unittest

from pipelines.smartnvr.pipeline import SmartNVRPipeline

class TestSmartNVRPipeline(unittest.TestCase):
    def setUp(self):
        self.pipeline = SmartNVRPipeline()
        self.constants = {
            "VIDEO_OUTPUT_PATH": "output.mp4",
            "VIDEO_PATH": "input.mp4",
            "OBJECT_DETECTION_MODEL_PATH": "detection_model.xml",
            "OBJECT_DETECTION_MODEL_PROC": "detection_model_proc.json",
            "OBJECT_CLASSIFICATION_MODEL_PATH": "classification_model.xml",
            "OBJECT_CLASSIFICATION_MODEL_PROC": "classification_model_proc.json",
        }
        self.regular_channels = 1
        self.inference_channels = 1

    def common_checks(self, result):
        # Check if the result is a string
        self.assertIsInstance(result, str)

        # Check that gst-launch-1.0 command is present
        self.assertTrue(result.startswith("gst-launch-1.0"))

        # Check that the number of inference channels is correct
        self.assertEqual(result.count("gvadetect"), self.inference_channels)
        self.assertEqual(result.count("gvatrack"), self.inference_channels)

    def output_present_check(self, result):
        # Check that output is set
        self.assertIn("location=output.mp4", result)

    def output_absent_check(self, result):
        # Check that output is not set
        self.assertNotIn("location=output.mp4", result)

    def sink_count_check(self, result):
        # Check that there are enough sinks
        for i in range(self.regular_channels + self.inference_channels):
            self.assertIn(f"sink_{i}", result)

    def sink_absent_check(self, result):
        # Check that there are no sinks
        for i in range(self.regular_channels + self.inference_channels):
            self.assertNotIn(f"sink_{i}", result)

    def gvaclassify_count_check(self, result, expected_count):
        # Check that the number of gvaclassify elements is as expected
        self.assertEqual(result.count("gvaclassify"), expected_count)

    def test_evaluate_no_overlay(self):
        result = self.pipeline.evaluate(
            constants=self.constants,
            parameters={
                "object_detection_device": "CPU",
                "object_detection_batch_size": 0,
                "object_detection_inference_interval": 1,
                "object_detection_nireq": 0,
                "object_classification_device": "CPU",
                "object_classification_batch_size": 0,
                "object_classification_inference_interval": 1,
                "object_classification_nireq": 0,
                "object_classification_reclassify_interval": 1,
                "pipeline_watermark_enabled": False,
                "live_preview_enabled": False,
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
        self.output_present_check(result)
        self.sink_count_check(result)
        self.gvaclassify_count_check(result, self.inference_channels)

        # Check gvawatermark is not present
        self.assertNotIn("gvawatermark", result)

    def test_evaluate_classification_disabled_by_device(self):
        result = self.pipeline.evaluate(
            constants=self.constants,
            parameters={
                "object_detection_device": "CPU",
                "object_detection_batch_size": 0,
                "object_detection_inference_interval": 1,
                "object_detection_nireq": 0,
                "object_classification_device": "Disabled",
                "object_classification_batch_size": 0,
                "object_classification_inference_interval": 1,
                "object_classification_nireq": 0,
                "object_classification_reclassify_interval": 1,
                "pipeline_watermark_enabled": True,
                "live_preview_enabled": False,
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
        self.output_present_check(result)
        self.sink_count_check(result)
        self.gvaclassify_count_check(result, 0)

    def test_evaluate_classification_disabled_by_model(self):
        result = self.pipeline.evaluate(
            constants={
                "VIDEO_OUTPUT_PATH": "output.mp4",
                "VIDEO_PATH": "input.mp4",
                "OBJECT_DETECTION_MODEL_PATH": "detection_model.xml",
                "OBJECT_DETECTION_MODEL_PROC": "detection_model_proc.json",
                "OBJECT_CLASSIFICATION_MODEL_PATH": "Disabled",
                "OBJECT_CLASSIFICATION_MODEL_PROC": "Disabled",
            },
            parameters={
                "object_detection_device": "CPU",
                "object_detection_batch_size": 0,
                "object_detection_inference_interval": 1,
                "object_detection_nireq": 0,
                "object_classification_device": "CPU",
                "object_classification_batch_size": 0,
                "object_classification_inference_interval": 1,
                "object_classification_nireq": 0,
                "object_classification_reclassify_interval": 1,
                "pipeline_watermark_enabled": True,
                "live_preview_enabled": False,
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
        self.output_present_check(result)
        self.sink_count_check(result)
        self.gvaclassify_count_check(result, 0)

    def test_evaluate_cpu(self):
        result = self.pipeline.evaluate(
            constants=self.constants,
            parameters={
                "object_detection_device": "CPU",
                "object_detection_batch_size": 0,
                "object_detection_inference_interval": 1,
                "object_detection_nireq": 0,
                "object_classification_device": "CPU",
                "object_classification_batch_size": 0,
                "object_classification_inference_interval": 1,
                "object_classification_nireq": 0,
                "object_classification_reclassify_interval": 1,
                "pipeline_watermark_enabled": True,
                "live_preview_enabled": False,
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
        self.output_present_check(result)
        self.sink_count_check(result)
        self.gvaclassify_count_check(result, self.inference_channels)

        # Check that model proc is used
        self.assertIn("model-proc=detection_model_proc.json", result)
        self.assertIn("model-proc=classification_model_proc.json", result)

        # Check that opencv is used for pre-processing
        self.assertIn("pre-process-backend=opencv", result)

    def test_evaluate_gpu(self):
        result = self.pipeline.evaluate(
            constants=self.constants,
            parameters={
                "object_detection_device": "GPU.1",
                "object_detection_batch_size": 0,
                "object_detection_inference_interval": 1,
                "object_detection_nireq": 0,
                "object_classification_device": "GPU.1",
                "object_classification_batch_size": 0,
                "object_classification_inference_interval": 1,
                "object_classification_nireq": 0,
                "object_classification_reclassify_interval": 1,
                "pipeline_watermark_enabled": True,
                "live_preview_enabled": False,
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
        self.output_present_check(result)
        self.sink_count_check(result)
        self.gvaclassify_count_check(result, self.inference_channels)

        # Check that model proc is used
        self.assertIn("model-proc=detection_model_proc.json", result)
        self.assertIn("model-proc=classification_model_proc.json", result)

        # Check that va-surface-sharing is used for pre-processing
        self.assertIn("pre-process-backend=va-surface-sharing", result)

        # Check that the right vaapi elements are used
        self.assertIn("varenderD129compositor", result)

    def test_evaluate_no_model_proc(self):
        result = self.pipeline.evaluate(
            constants={
                "VIDEO_OUTPUT_PATH": "output.mp4",
                "VIDEO_PATH": "input.mp4",
                "OBJECT_DETECTION_MODEL_PATH": "detection_model.xml",
                "OBJECT_DETECTION_MODEL_PROC": None,
                "OBJECT_CLASSIFICATION_MODEL_PATH": "classification_model.xml",
                "OBJECT_CLASSIFICATION_MODEL_PROC": None,
            },
            parameters={
                "object_detection_device": "CPU",
                "object_detection_batch_size": 0,
                "object_detection_inference_interval": 1,
                "object_detection_nireq": 0,
                "object_classification_device": "CPU",
                "object_classification_batch_size": 0,
                "object_classification_inference_interval": 1,
                "object_classification_nireq": 0,
                "object_classification_reclassify_interval": 1,
                "pipeline_watermark_enabled": True,
                "live_preview_enabled": False,
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
        self.output_present_check(result)
        self.sink_count_check(result)
        self.gvaclassify_count_check(result, self.inference_channels)

        # Check that no model proc is used
        self.assertNotIn("model-proc=", result)


if __name__ == "__main__":
    unittest.main()
