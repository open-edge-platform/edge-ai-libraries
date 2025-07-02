import os
from pathlib import Path
import tempfile
import unittest
from models import ModelManager


class TestModelManager(unittest.TestCase):
    def setUp(self):
        self.manager = ModelManager()
        self.allowed_devices = ["CPU", "GPU", "NPU"]
        self.allowed_precisions = [
            "FP32",
            "FP16",
            "INT8",
            "FP16-INT8",
            "FP32-INT8",
            "UNKNOWN",
        ]
        self.allowed_tasks = ["CLASSIFICATION", "DETECTION", "UNKNOWN"]
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def test_discover_models(self):
        # Mock model with precision and no proc
        (Path(self.test_dir.name) / "model1").mkdir(exist_ok=True)
        (Path(self.test_dir.name) / "model1" / "FP32").mkdir(exist_ok=True)
        (Path(self.test_dir.name) / "model1" / "FP32" / "model1.xml").touch()
        (Path(self.test_dir.name) / "model1" / "FP32" / "model1.bin").touch()

        # Mock model without precision and proc
        (Path(self.test_dir.name) / "model2").mkdir(exist_ok=True)
        (Path(self.test_dir.name) / "model2" / "model2.xml").touch()
        (Path(self.test_dir.name) / "model2" / "model2.bin").touch()
        (Path(self.test_dir.name) / "model2" / "model2.json").touch()

        # Mock a known model
        (Path(self.test_dir.name) / "efficientnet-b0_INT8").mkdir(exist_ok=True)
        (Path(self.test_dir.name) / "efficientnet-b0_INT8" / "FP16").mkdir(
            exist_ok=True
        )
        (
            Path(self.test_dir.name)
            / "efficientnet-b0_INT8"
            / "FP16"
            / "known_model.xml"
        ).touch()
        (
            Path(self.test_dir.name)
            / "efficientnet-b0_INT8"
            / "FP16"
            / "known_model.bin"
        ).touch()
        (Path(self.test_dir.name) / "efficientnet-b0_INT8" / "known_model.json").touch()

        # Mock folder with no model
        (Path(self.test_dir.name) / "empty_folder").mkdir(exist_ok=True)
        (Path(self.test_dir.name) / "empty_folder" / "not_a_model.txt").touch()

        # Discover models
        self.manager.discover_models(self.test_dir.name)

        # Assert that models were discovered
        self.assertEqual(len(self.manager.models), 3, "No models were discovered")

        for model in self.manager.models:
            self.assertTrue(model.name)
            self.assertIn(model.precision, self.allowed_precisions)
            self.assertTrue(model.bin.exists(), f"Bin {model.bin} does not exist")
            self.assertTrue(model.xml.exists(), f"Xml {model.xml} does not exist")
            if model.proc:
                self.assertTrue(
                    model.proc.exists(), f"Proc {model.proc} does not exist"
                )
            for device in model.devices:
                self.assertIn(device, self.allowed_devices)
            self.assertIn(model.task, self.allowed_tasks)


if __name__ == "__main__":
    unittest.main()
