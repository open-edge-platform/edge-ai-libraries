import unittest

from pipeline import GstPipeline
from pipelines.smartnvr.pipeline import SmartNVRPipeline


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
            self.pipeline.evaluate(
                **{
                    "constants": {},
                    "parameters": {},
                    "regular_channels": 1,
                    "inference_channels": 1,
                }
            )


if __name__ == "__main__":
    unittest.main()
