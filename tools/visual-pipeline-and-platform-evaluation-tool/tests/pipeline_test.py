import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gstpipeline import GstPipeline, PipelineLoader


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
                    "elements": [],
                }
            )


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
        os.mkdir(Path(self.test_dir.name) / "pipeline1")
        config_path = Path(self.test_dir.name) / "pipeline1" / "config.yaml"
        config_path.write_text(
            """
            metadata:
                classname: MockPipeline
            """
        )

        class MockPipeline(GstPipeline):
            def __init__(self):
                pass

        with patch("importlib.import_module") as mock_import:
            mock_import.return_value.MockPipeline = MockPipeline
            pipeline, config = PipelineLoader.load("pipeline1", self.test_dir.name)
            self.assertIsInstance(pipeline, MockPipeline)
            self.assertEqual(config, {"metadata": {"classname": "MockPipeline"}})


if __name__ == "__main__":
    unittest.main()
