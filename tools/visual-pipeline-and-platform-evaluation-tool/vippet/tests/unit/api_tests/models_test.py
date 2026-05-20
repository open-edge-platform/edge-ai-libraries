import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api.routes.models import router as models_router
from internal_types import (
    InternalModelCategory,
    InternalModelInstallStatus,
    InternalModelPrecision,
    InternalModelSource,
    InternalModelVariant,
    InternalSupportedModel,
)


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
        category,
        precision=None,
        model_path_full="/fake/path/model.xml",
        source=InternalModelSource.PIPELINE_ZOO_MODELS,
        install_status=InternalModelInstallStatus.INSTALLED,
    ):
        """Helper building an :class:`InternalSupportedModel` instance.

        Tests only assert on the API shape, so we drive ``ModelManager``
        via its ``list_models`` return value rather than mocking the
        lower-level ``SupportedModelsManager``.
        """
        precisions = (
            [InternalModelPrecision(precision=precision, model_path=model_path_full)]
            if precision is not None
            else []
        )
        variants = (
            [
                InternalModelVariant(
                    name=name,
                    display_name=(
                        f"{display_name} ({precision})" if precision else display_name
                    ),
                    precision=precision or "",
                )
            ]
            if precision is not None
            else []
        )
        return InternalSupportedModel(
            name=name,
            display_name=display_name,
            category=(
                InternalModelCategory(category)
                if category in {c.value for c in InternalModelCategory}
                else None
            ),
            source=source,
            precisions=precisions,
            variants=variants,
            install_status=install_status,
            used_by_pipelines=[],
            default=False,
            unsupported_devices=None,
            download_request=None,
        )

    def test_get_models_returns_models_with_variants(self):
        """Test GET /models returns models with variants list populated."""
        mock_models = [
            self._make_model(
                "resnet-50-tf_INT8",
                "ResNet-50 TF",
                "classification",
                "INT8",
                "/fake/path/resnet.xml",
            ),
            self._make_model(
                "yolov10m",
                "YOLO v10m 640x640",
                "detection",
                "FP16",
                "/fake/path/yolo.xml",
            ),
        ]
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.list_models.return_value = mock_models
            mock_manager_cls.return_value = mock_manager_instance

            response = self.client.get("/models")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 2)

            # Check first model
            self.assertEqual(data[0]["name"], "resnet-50-tf_INT8")
            self.assertEqual(data[0]["display_name"], "ResNet-50 TF")
            self.assertEqual(data[0]["category"], "classification")
            self.assertEqual(data[0]["install_status"], "installed")
            self.assertEqual(data[0]["source"], "pipeline-zoo-models")
            self.assertEqual(
                data[0]["variants"],
                [
                    {
                        "name": "resnet-50-tf_INT8",
                        "display_name": "ResNet-50 TF (INT8)",
                        "precision": "INT8",
                        "installed": False,
                    }
                ],
            )
            # Filesystem paths must not leak through the API.
            self.assertNotIn("precisions", data[0])

            # Check second model
            self.assertEqual(data[1]["name"], "yolov10m")
            self.assertEqual(data[1]["display_name"], "YOLO v10m 640x640")
            self.assertEqual(data[1]["category"], "detection")
            self.assertEqual(
                data[1]["variants"],
                [
                    {
                        "name": "yolov10m",
                        "display_name": "YOLO v10m 640x640 (FP16)",
                        "precision": "FP16",
                        "installed": False,
                    }
                ],
            )

    def test_get_models_returns_models_without_variants(self):
        """Test GET /models returns models with empty variants when none configured."""
        mock_models = [
            self._make_model(
                "mobilenet",
                "MobileNetV2",
                "classification",
                None,
                "/fake/path/mobilenet.xml",
                install_status=InternalModelInstallStatus.NOT_INSTALLED,
            ),
        ]
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.list_models.return_value = mock_models
            mock_manager_cls.return_value = mock_manager_instance

            response = self.client.get("/models")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data[0]["name"], "mobilenet")
            self.assertEqual(data[0]["variants"], [])
            self.assertEqual(data[0]["install_status"], "not_installed")

    def test_get_models_empty_list(self):
        """Test GET /models returns empty list when no models available."""
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.list_models.return_value = []
            mock_manager_cls.return_value = mock_manager_instance

            response = self.client.get("/models")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data, [])

    def test_get_models_with_unknown_category(self):
        """Test GET /models returns category=None for unknown model category."""
        mock_models = [
            self._make_model(
                "weird-model",
                "Weird Model",
                "not_a_category",
                "FP32",
                "/fake/path/weird.xml",
            ),
        ]
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.list_models.return_value = mock_models
            mock_manager_cls.return_value = mock_manager_instance

            response = self.client.get("/models")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["name"], "weird-model")
            self.assertIsNone(data[0]["category"])
            self.assertEqual(
                data[0]["variants"],
                [
                    {
                        "name": "weird-model",
                        "display_name": "Weird Model (FP32)",
                        "precision": "FP32",
                        "installed": False,
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
