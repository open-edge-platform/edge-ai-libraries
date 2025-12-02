import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api.routes.models import router as models_router


class TestModelsAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test client once for all tests."""
        app = FastAPI()
        app.include_router(models_router, prefix="/models")
        cls.client = TestClient(app)

    @staticmethod
    def _make_model(
        name,
        display_name,
        model_type,
        precision=None,
        model_path_full=None,
        model_proc_full=None,
    ):
        """Helper method to create a mock model with real string attributes."""
        m = MagicMock()
        m.name = name
        m.display_name = display_name
        m.model_type = model_type
        m.precision = precision if precision is not None else None
        m.model_path_full = (
            model_path_full if model_path_full is not None else "/fake/path/model.xml"
        )
        m.model_proc_full = (
            model_proc_full
            if model_proc_full is not None
            else "/fake/path/model_proc.json"
        )
        return m

    def test_get_models_returns_models_with_precision(self):
        """Test GET /models returns models with precision extracted from display_name."""
        mock_models = [
            self._make_model(
                "resnet-50-tf_INT8",
                "ResNet-50 TF (INT8)",
                "classification",
                "INT8",
                "/fake/path/resnet.xml",
                "/fake/path/resnet_proc.json",
            ),
            self._make_model(
                "yolov10m",
                "YOLO v10m 640x640 (FP16)",
                "detection",
                "FP16",
                "/fake/path/yolo.xml",
                "/fake/path/yolo_proc.json",
            ),
        ]
        with patch(
            "api.routes.models.get_supported_models_manager"
        ) as mock_get_manager:
            mock_manager_instance = mock_get_manager.return_value
            mock_manager_instance.get_all_installed_models.return_value = mock_models
            response = self.client.get("/models")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 2)

            # Check first model
            self.assertEqual(data[0]["name"], "resnet-50-tf_INT8")
            self.assertEqual(data[0]["display_name"], "ResNet-50 TF (INT8)")
            self.assertEqual(data[0]["category"], "classification")
            self.assertEqual(data[0]["precision"], "INT8")

            # Check second model
            self.assertEqual(data[1]["name"], "yolov10m")
            self.assertEqual(data[1]["display_name"], "YOLO v10m 640x640 (FP16)")
            self.assertEqual(data[1]["category"], "detection")
            self.assertEqual(data[1]["precision"], "FP16")

    def test_get_models_returns_models_without_precision(self):
        """Test GET /models returns models without precision when not in display_name."""
        mock_models = [
            self._make_model(
                "mobilenet",
                "MobileNetV2",
                "classification",
                None,
                "/fake/path/mobilenet.xml",
                "/fake/path/mobilenet_proc.json",
            ),
        ]
        with patch(
            "api.routes.models.get_supported_models_manager"
        ) as mock_get_manager:
            mock_manager_instance = mock_get_manager.return_value
            mock_manager_instance.get_all_installed_models.return_value = mock_models
            response = self.client.get("/models")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data[0]["name"], "mobilenet")
            self.assertIsNone(data[0]["precision"])

    def test_get_models_empty_list(self):
        """Test GET /models returns empty list when no models available."""
        with patch(
            "api.routes.models.get_supported_models_manager"
        ) as mock_get_manager:
            mock_manager_instance = mock_get_manager.return_value
            mock_manager_instance.get_all_installed_models.return_value = []
            response = self.client.get("/models")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data, [])

    def test_get_models_with_unknown_category(self):
        """Test GET /models returns category=None for unknown model_type."""
        mock_models = [
            self._make_model(
                "weird-model",
                "Weird Model",
                "not_a_category",
                "FP32",
                "/fake/path/weird.xml",
                "/fake/path/weird_proc.json",
            ),
        ]
        with patch(
            "api.routes.models.get_supported_models_manager"
        ) as mock_get_manager:
            mock_manager_instance = mock_get_manager.return_value
            mock_manager_instance.get_all_installed_models.return_value = mock_models
            response = self.client.get("/models")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["name"], "weird-model")
            self.assertIsNone(data[0]["category"])
            self.assertEqual(data[0]["precision"], "FP32")


if __name__ == "__main__":
    unittest.main()
