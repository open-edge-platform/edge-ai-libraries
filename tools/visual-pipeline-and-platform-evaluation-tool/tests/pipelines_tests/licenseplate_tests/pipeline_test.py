import unittest

from pipelines.licenseplate.pipeline import LicensePlateDetectionPipeline


class TestTransportation2Pipeline(unittest.TestCase):
    def setUp(self):
        self.pipeline = LicensePlateDetectionPipeline()

    def common_checks(self, result):
        # Check if the result is a string
        self.assertIsInstance(result, str)

        # Check that gst-launch-1.0 command is present
        self.assertTrue(result.startswith("gst-launch-1.0"))

        # Check that expected elements are present in the pipeline
        for element in [
            "gvadetect",
            "gvaclassify",
        ]:
            self.assertIn(element, result)

    def test_evaluate(self):
        result = self.pipeline.evaluate(
            constants={},
            parameters={},
            elements=[],
        )

        # Common checks
        self.common_checks(result)


if __name__ == "__main__":
    unittest.main()
