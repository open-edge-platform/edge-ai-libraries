import io
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

import api.api_schemas as schemas
from api.routes.models import _aggregate_status, router as models_router
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

    # ------------------------------------------------------------------
    # GET /models — error branch
    # ------------------------------------------------------------------

    def test_get_models_returns_500_when_manager_raises(self):
        """list_models raising should map to a 500 MessageResponse."""
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.list_models.side_effect = RuntimeError("boom")
            mock_manager_cls.return_value = mock_manager_instance

            response = self.client.get("/models")

            self.assertEqual(response.status_code, 500)
            self.assertIn("Unexpected error", response.json()["message"])


class TestModelsUploadAPI(unittest.TestCase):
    """Tests for POST /models/upload route layer.

    The route is a thin adapter: it streams the upload to a temp file,
    calls ``ModelManager.upload_model`` and translates the
    ``(model, status, message)`` tuple into the right HTTP envelope.
    """

    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(models_router, prefix="/models")
        cls.client = TestClient(app)

    @staticmethod
    def _make_uploaded_model() -> InternalSupportedModel:
        """Build a minimal InternalSupportedModel for a freshly uploaded model."""
        return InternalSupportedModel(
            name="my-detector",
            display_name="my-detector",
            category=InternalModelCategory.DETECTION,
            source=InternalModelSource.CUSTOM,
            precisions=[
                InternalModelPrecision(precision="", model_path="/models/output/x")
            ],
            variants=[
                InternalModelVariant(
                    name="my-detector",
                    display_name="my-detector",
                    precision="",
                    installed=True,
                )
            ],
            install_status=InternalModelInstallStatus.INSTALLED,
            used_by_pipelines=[],
            default=False,
            unsupported_devices=None,
            download_request=None,
        )

    def _post_upload(
        self,
        *,
        model_name: str = "my-detector",
        category: str = "detection",
        file_bytes: bytes = b"fake-zip-bytes",
        file_name: str = "my-detector.zip",
    ):
        """Helper to POST a multipart upload with the standard form fields."""
        return self.client.post(
            "/models/upload",
            data={"model_name": model_name, "category": category},
            files={"file": (file_name, io.BytesIO(file_bytes), "application/zip")},
        )

    def test_upload_model_success_returns_201(self):
        """Happy path: ModelManager returns a model + 201, route mirrors it."""
        model = self._make_uploaded_model()
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_cls.write_upload_to_tempfile.return_value = "/tmp/upload.zip"
            mock_manager_instance = MagicMock()
            mock_manager_instance.upload_model.return_value = (
                model,
                201,
                "Model uploaded successfully",
            )
            mock_manager_cls.return_value = mock_manager_instance

            response = self._post_upload()

            self.assertEqual(response.status_code, 201)
            body = response.json()
            self.assertEqual(body["model"]["name"], "my-detector")
            self.assertEqual(body["model"]["source"], "custom")
            self.assertEqual(body["model"]["install_status"], "installed")

            # The route must always delete the temp file, even on success.
            mock_manager_cls.cleanup_tempfile.assert_called_once_with("/tmp/upload.zip")
            # Manager was driven with the form fields verbatim.
            spec = mock_manager_instance.upload_model.call_args.args[0]
            self.assertEqual(spec.model_name, "my-detector")
            self.assertEqual(spec.category, InternalModelCategory.DETECTION)
            self.assertEqual(spec.file_path, "/tmp/upload.zip")

    def test_upload_model_manager_rejects_with_409(self):
        """When the manager returns ``(None, 409, msg)`` the route returns 409."""
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_cls.write_upload_to_tempfile.return_value = "/tmp/upload.zip"
            mock_manager_instance = MagicMock()
            mock_manager_instance.upload_model.return_value = (
                None,
                409,
                "Model already exists",
            )
            mock_manager_cls.return_value = mock_manager_instance

            response = self._post_upload()

            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["message"], "Model already exists")
            mock_manager_cls.cleanup_tempfile.assert_called_once_with("/tmp/upload.zip")

    def test_upload_model_manager_rejects_with_502(self):
        """Upstream model-download error surfaces as 502."""
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_cls.write_upload_to_tempfile.return_value = "/tmp/upload.zip"
            mock_manager_instance = MagicMock()
            mock_manager_instance.upload_model.return_value = (
                None,
                502,
                "Upload failed: connection refused",
            )
            mock_manager_cls.return_value = mock_manager_instance

            response = self._post_upload()

            self.assertEqual(response.status_code, 502)
            self.assertIn("connection refused", response.json()["message"])

    def test_upload_model_returns_500_on_unexpected_error(self):
        """An unexpected exception inside the route maps to 500 + cleanup."""
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_cls.write_upload_to_tempfile.return_value = "/tmp/upload.zip"
            mock_manager_instance = MagicMock()
            mock_manager_instance.upload_model.side_effect = RuntimeError("nope")
            mock_manager_cls.return_value = mock_manager_instance

            response = self._post_upload()

            self.assertEqual(response.status_code, 500)
            self.assertIn("Unexpected error", response.json()["message"])
            # Tempfile must still be cleaned up via the ``finally`` block.
            mock_manager_cls.cleanup_tempfile.assert_called_once_with("/tmp/upload.zip")

    def test_upload_model_forwards_original_filename(self):
        """The ``InternalModelUploadSpec`` carries the client-provided filename."""
        model = self._make_uploaded_model()
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_cls.write_upload_to_tempfile.return_value = "/tmp/upload.zip"
            mock_manager_instance = MagicMock()
            mock_manager_instance.upload_model.return_value = (model, 201, "ok")
            mock_manager_cls.return_value = mock_manager_instance

            response = self._post_upload(file_name="archive.zip")
            self.assertEqual(response.status_code, 201)
            spec = mock_manager_instance.upload_model.call_args.args[0]
            self.assertEqual(spec.original_filename, "archive.zip")

    def test_upload_model_missing_form_field_returns_422(self):
        """FastAPI validation rejects requests without ``model_name``."""
        response = self.client.post(
            "/models/upload",
            data={"category": "detection"},
            files={
                "file": ("a.zip", io.BytesIO(b"x"), "application/zip"),
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_upload_model_invalid_category_returns_422(self):
        """Unknown category values are rejected by the Enum validator."""
        response = self.client.post(
            "/models/upload",
            data={"model_name": "x", "category": "not-a-category"},
            files={
                "file": ("a.zip", io.BytesIO(b"x"), "application/zip"),
            },
        )
        self.assertEqual(response.status_code, 422)


class TestModelsDownloadAPI(unittest.TestCase):
    """Tests for POST /models/download (batch download endpoint).

    The route delegates per-model decisions to ``ModelManager.start_download``
    and aggregates the per-model HTTP-like statuses into a single envelope
    HTTP status via ``_aggregate_status``.
    """

    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(models_router, prefix="/models")
        cls.client = TestClient(app)

    def test_download_single_accepted_returns_202(self):
        """One model accepted -> envelope status 202 + jobs map entry."""
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.start_download.return_value = (
                "job-1",
                202,
                "Download started (job job-1)",
            )
            mock_manager_cls.return_value = mock_manager_instance

            response = self.client.post("/models/download", json={"names": ["yolo11n"]})

            self.assertEqual(response.status_code, 202)
            jobs = response.json()["jobs"]
            self.assertEqual(jobs["yolo11n"]["job_id"], "job-1")
            self.assertEqual(jobs["yolo11n"]["status_code"], 202)
            self.assertEqual(jobs["yolo11n"]["name"], "yolo11n")

    def test_download_mixed_results_returns_207(self):
        """Some accepted + some rejected -> 207 Multi-Status."""

        def fake_start(name: str):
            if name == "yolo11n":
                return ("job-1", 202, "Download started")
            return (None, 409, f"Model '{name}' is already installed")

        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.start_download.side_effect = fake_start
            mock_manager_cls.return_value = mock_manager_instance

            response = self.client.post(
                "/models/download",
                json={"names": ["yolo11n", "yolov8n"]},
            )

            self.assertEqual(response.status_code, 207)
            jobs = response.json()["jobs"]
            self.assertEqual(jobs["yolo11n"]["status_code"], 202)
            self.assertEqual(jobs["yolov8n"]["status_code"], 409)
            self.assertIsNone(jobs["yolov8n"]["job_id"])

    def test_download_all_rejected_same_code_returns_that_code(self):
        """All entries fail with the same client error code -> that code."""
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.start_download.return_value = (
                None,
                404,
                "unknown",
            )
            mock_manager_cls.return_value = mock_manager_instance

            response = self.client.post("/models/download", json={"names": ["a", "b"]})

            self.assertEqual(response.status_code, 404)

    def test_download_all_rejected_mixed_codes_picks_400(self):
        """Mixed rejected codes: precedence is 400 > 404 > 409."""

        def fake_start(name: str):
            return {
                "a": (None, 409, "x"),
                "b": (None, 404, "y"),
                "c": (None, 400, "z"),
            }[name]

        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.start_download.side_effect = fake_start
            mock_manager_cls.return_value = mock_manager_instance

            response = self.client.post(
                "/models/download", json={"names": ["a", "b", "c"]}
            )

            self.assertEqual(response.status_code, 400)

    def test_download_returns_500_when_manager_raises(self):
        """An unexpected error inside ``start_download`` maps to 500."""
        with patch("api.routes.models.ModelManager") as mock_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.start_download.side_effect = RuntimeError("boom")
            mock_manager_cls.return_value = mock_manager_instance

            response = self.client.post("/models/download", json={"names": ["yolo11n"]})

            self.assertEqual(response.status_code, 500)
            self.assertIn("Unexpected error", response.json()["message"])

    def test_download_empty_names_rejected_by_validator(self):
        """``names=[]`` is rejected by the Pydantic ``min_length=1`` rule."""
        response = self.client.post("/models/download", json={"names": []})
        self.assertEqual(response.status_code, 422)

    def test_download_duplicate_names_rejected_by_validator(self):
        """Duplicate names are rejected (the per-name response map must be unambiguous)."""
        response = self.client.post("/models/download", json={"names": ["a", "a"]})
        self.assertEqual(response.status_code, 422)


class TestAggregateStatus(unittest.TestCase):
    """Direct unit tests for ``_aggregate_status`` precedence rules."""

    @staticmethod
    def _item(code: int) -> schemas.ModelDownloadJobItem:
        return schemas.ModelDownloadJobItem(
            name="x", job_id=None, status_code=code, message=""
        )

    def test_all_accepted_is_202(self):
        items = {"a": self._item(202), "b": self._item(202)}
        self.assertEqual(_aggregate_status(items), 202)

    def test_mixed_accept_and_reject_is_207(self):
        items = {"a": self._item(202), "b": self._item(409)}
        self.assertEqual(_aggregate_status(items), 207)

    def test_all_rejected_picks_400_first(self):
        items = {
            "a": self._item(409),
            "b": self._item(404),
            "c": self._item(400),
        }
        self.assertEqual(_aggregate_status(items), 400)

    def test_all_rejected_picks_404_when_no_400(self):
        items = {"a": self._item(409), "b": self._item(404)}
        self.assertEqual(_aggregate_status(items), 404)

    def test_all_rejected_409_only(self):
        items = {"a": self._item(409), "b": self._item(409)}
        self.assertEqual(_aggregate_status(items), 409)

    def test_unknown_codes_fall_back_to_first(self):
        """Codes outside the documented set fall back to the first value."""
        items = {"a": self._item(418), "b": self._item(500)}
        self.assertEqual(_aggregate_status(items), 418)

    def test_empty_mapping_returns_202(self):
        """Defensive: empty mapping should not crash (validator guards real route)."""
        self.assertEqual(_aggregate_status({}), 202)


if __name__ == "__main__":
    unittest.main()
