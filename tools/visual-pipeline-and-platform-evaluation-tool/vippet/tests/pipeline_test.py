import os
import tempfile
import unittest
from pathlib import Path

from gstpipeline import GstPipeline, PipelineLoader


class TestGstPipeline(unittest.TestCase):
    def setUp(self):
        test_pipeline_description = (
            "videotestsrc "
            " num-buffers=5 "
            " pattern=snow ! "
            "videoconvert ! "
            "gvafpscounter ! "
            "fakesink"
        )
        self.pipeline = GstPipeline(pipeline_description=test_pipeline_description)

    # TODO: Implement test for GstPipeline as part of ITEP-80181
    def test_evaluate_method(self):
        pipeline_description = self.pipeline.evaluate(
            regular_channels=0, inference_channels=1
        )
        self.assertFalse(pipeline_description.startswith("gst-launch-1.0 -q "))


class TestPipelineLoader(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def test_list_pipelines(self):
        os.mkdir(Path(self.test_dir.name) / "pipeline1")
        os.mkdir(Path(self.test_dir.name) / "pipeline2")
        os.mkdir(Path(self.test_dir.name) / "__pycache__")

        pipelines = PipelineLoader.list(self.test_dir.name)
        self.assertIsInstance(pipelines, list)
        self.assertEqual(len(pipelines), 2)
        for pipeline_name in pipelines:
            self.assertNotIn("/", pipeline_name)
        self.assertIn("pipeline1", pipelines)
        self.assertIn("pipeline2", pipelines)

    def test_config(self):
        os.mkdir(Path(self.test_dir.name) / "pipeline1")
        config_path = Path(self.test_dir.name) / "pipeline1" / "config.yaml"
        config_path.write_text("key: value")
        config = PipelineLoader.config("pipeline1", self.test_dir.name)
        self.assertIsInstance(config, dict)
        self.assertEqual(config, {"key": "value"})

    def test_config_file_not_found(self):
        with self.assertRaises(ValueError):
            PipelineLoader.config("non_existent_pipeline", self.test_dir.name)

    def test_load(self):
        test_pipeline_description = (
            "videotestsrc "
            " num-buffers=5 "
            " pattern=snow ! "
            "videoconvert ! "
            "gvafpscounter ! "
            "fakesink"
        )

        pipeline = PipelineLoader.load(pipeline_description=test_pipeline_description)
        self.assertIsInstance(pipeline, GstPipeline)
        self.assertEqual(pipeline._pipeline_description, test_pipeline_description)


if __name__ == "__main__":
    unittest.main()
