import os
import tempfile
import unittest
from pathlib import Path

from pipelines.loader import PipelineLoader


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


if __name__ == "__main__":
    unittest.main()
