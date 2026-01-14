import tempfile
import unittest
from pathlib import Path

from pipelines.loader import PipelineLoader


class TestPipelineLoader(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def test_list_pipelines(self):
        # Create .yaml files instead of directories
        (Path(self.test_dir.name) / "pipeline1.yaml").write_text("key: value")
        (Path(self.test_dir.name) / "pipeline2.yaml").write_text("key: value")
        (Path(self.test_dir.name) / "not_a_yaml.txt").write_text("text")

        pipelines = PipelineLoader.list(self.test_dir.name)
        self.assertIsInstance(pipelines, list)
        self.assertEqual(len(pipelines), 2)
        # Verify that returned items are Path objects
        for pipeline_path in pipelines:
            self.assertIsInstance(pipeline_path, Path)
            self.assertTrue(str(pipeline_path).endswith(".yaml"))

    def test_config(self):
        config_path = Path(self.test_dir.name) / "test_config.yaml"
        config_path.write_text("key: value")
        config = PipelineLoader.config(config_path)
        self.assertIsInstance(config, dict)
        self.assertEqual(config, {"key": "value"})

    def test_config_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            PipelineLoader.config(Path("non_existent_file.yaml"))


if __name__ == "__main__":
    unittest.main()
