import unittest

from pipelines.simplevs.pipeline import SimpleVideoStructurizationPipeline


class TestSimpleVideoStructurizationPipeline(unittest.TestCase):
    def setUp(self):
        self.pipeline = SimpleVideoStructurizationPipeline()
        self.constants = {
            "VIDEO_OUTPUT_PATH": "output.mp4",
            "VIDEO_PATH": "input.mp4",
            "OBJECT_DETECTION_MODEL_PATH": "detection_model.xml",
            "OBJECT_DETECTION_MODEL_PROC": "detection_model_proc.json",
            "OBJECT_CLASSIFICATION_MODEL_PATH": "classification_model.xml",
            "OBJECT_CLASSIFICATION_MODEL_PROC": "classification_model_proc.json",
        }
        self.inference_channels = 1

    def common_checks(self, result):
        # Check if the result is a string
        self.assertIsInstance(result, str)

        # Check that gst-launch-1.0 command is present
        self.assertTrue(result.startswith("gst-launch-1.0"))

        # Check that input is set
        self.assertIn("location=input.mp4", result)

        # Check that the number of inference channels is correct
        self.assertEqual(result.count("gvadetect"), self.inference_channels)
        self.assertEqual(result.count("gvaclassify"), self.inference_channels)

    def output_present_check(self, result):
        # Check that output is set
        self.assertIn("location=output.mp4", result)

    def output_absent_check(self, result):
        # Check that output is not set
        self.assertNotIn("location=output.mp4", result)

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
                "pipeline_video_enabled": True,
                "live_preview_enabled": False,
            },
            regular_channels=0,
            inference_channels=self.inference_channels,
            elements=[
                ("va", "decodebin3", "..."),
                ("va", "vah264enc", "..."),
                ("va", "vah264dec", "..."),
                ("va", "vapostproc", "..."),
            ],
        )

        # Common checks
        self.common_checks(result)

        # Check that model proc is used
        self.assertIn("model-proc=detection_model_proc.json", result)
        self.assertIn("model-proc=classification_model_proc.json", result)

        # Check that the decoder element is correctly used
        self.assertIn("decodebin3", result)

        # Check that opencv is used for pre-processing
        self.assertIn("pre-process-backend=opencv", result)

        # Check that output is set
        self.output_present_check(result)

    def test_evaluate_gpu(self):
        result = self.pipeline.evaluate(
            constants=self.constants,
            parameters={
                "object_detection_device": "GPU",
                "object_detection_batch_size": 0,
                "object_detection_inference_interval": 1,
                "object_detection_nireq": 0,
                "object_classification_device": "GPU",
                "object_classification_batch_size": 0,
                "object_classification_inference_interval": 1,
                "object_classification_nireq": 0,
                "object_classification_reclassify_interval": 1,
                "pipeline_watermark_enabled": True,
                "pipeline_video_enabled": True,
                "live_preview_enabled": False,
            },
            regular_channels=0,
            inference_channels=self.inference_channels,
            elements=[
                ("va", "decodebin3", "..."),
                ("va", "vah264enc", "..."),
                ("va", "vah264dec", "..."),
                ("va", "vapostproc", "..."),
            ],
        )

        # Common checks
        self.common_checks(result)

        # Check that model proc is used
        self.assertIn("model-proc=detection_model_proc.json", result)
        self.assertIn("model-proc=classification_model_proc.json", result)

        # Check that the decoder element is correctly used
        self.assertIn("decodebin3 ! vapostproc ! video/x-raw\\(memory:VAMemory\\)", result)

        # Check that va-surface-sharing is used for pre-processing
        self.assertIn("pre-process-backend=va-surface-sharing", result)

        # Check that output is set
        self.output_present_check(result)

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
                "object_detection_device": "GPU",
                "object_detection_batch_size": 0,
                "object_detection_inference_interval": 1,
                "object_detection_nireq": 0,
                "object_classification_device": "GPU",
                "object_classification_batch_size": 0,
                "object_classification_inference_interval": 1,
                "object_classification_nireq": 0,
                "object_classification_reclassify_interval": 1,
                "pipeline_watermark_enabled": True,
                "pipeline_video_enabled": True,
                "live_preview_enabled": False,
            },
            regular_channels=0,
            inference_channels=self.inference_channels,
            elements=[
                ("va", "decodebin3", "..."),
                ("va", "vah264enc", "..."),
                ("va", "vah264dec", "..."),
                ("va", "vapostproc", "..."),
            ],
        )

        # Common checks
        self.common_checks(result)

        # Check that no model proc is used
        self.assertNotIn("model-proc=", result)

        # Check that output is set
        self.output_present_check(result)

    def test_evaluate_no_overlay(self):
        result = self.pipeline.evaluate(
            constants=self.constants,
            parameters={
                "object_detection_device": "GPU",
                "object_detection_batch_size": 0,
                "object_detection_inference_interval": 1,
                "object_detection_nireq": 0,
                "object_classification_device": "GPU",
                "object_classification_batch_size": 0,
                "object_classification_inference_interval": 1,
                "object_classification_nireq": 0,
                "object_classification_reclassify_interval": 1,
                "pipeline_watermark_enabled": False,
                "pipeline_video_enabled": True,
                "live_preview_enabled": False,
            },
            regular_channels=0,
            inference_channels=self.inference_channels,
            elements=[
                ("va", "decodebin3", "..."),
                ("va", "vah264enc", "..."),
            ],
        )

        # Common checks
        self.common_checks(result)

        # Check gvawatermark is not present
        self.assertNotIn("gvawatermark", result)

        # Check that output is set
        self.output_present_check(result)

    def test_evaluate_no_overlay_no_video(self):
        result = self.pipeline.evaluate(
            constants=self.constants,
            parameters={
                "object_detection_device": "GPU",
                "object_detection_batch_size": 0,
                "object_detection_inference_interval": 1,
                "object_detection_nireq": 0,
                "object_classification_device": "GPU",
                "object_classification_batch_size": 0,
                "object_classification_inference_interval": 1,
                "object_classification_nireq": 0,
                "object_classification_reclassify_interval": 1,
                "pipeline_watermark_enabled": False,
                "pipeline_video_enabled": False,
                "live_preview_enabled": False,
            },
            regular_channels=0,
            inference_channels=self.inference_channels,
            elements=[
                ("va", "decodebin3", "..."),
                ("va", "vah264enc", "..."),
            ],
        )

        # Common checks
        self.common_checks(result)

        # Check gvawatermark is not present
        self.assertNotIn("gvawatermark", result)

        # Check that output is not set
        self.output_absent_check(result)

    def test_evaluate_no_overlay_when_video_disabled(self):
        result = self.pipeline.evaluate(
            constants=self.constants,
            parameters={
                "object_detection_device": "GPU",
                "object_detection_batch_size": 0,
                "object_detection_inference_interval": 1,
                "object_detection_nireq": 0,
                "object_classification_device": "GPU",
                "object_classification_batch_size": 0,
                "object_classification_inference_interval": 1,
                "object_classification_nireq": 0,
                "object_classification_reclassify_interval": 1,
                "pipeline_watermark_enabled": True,
                "pipeline_video_enabled": False,
                "live_preview_enabled": False,
            },
            regular_channels=0,
            inference_channels=self.inference_channels,
            elements=[
                ("va", "decodebin3", "..."),
                ("va", "vah264enc", "..."),
            ],
        )

        # Common checks
        self.common_checks(result)

        # Check gvawatermark is not present even when watermark is enabled
        # because video is disabled
        self.assertNotIn("gvawatermark", result)

        # Check that output is not set
        self.output_absent_check(result)

if __name__ == "__main__":
    unittest.main()
