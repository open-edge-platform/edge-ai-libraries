# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for ``vippet.api.routes.images``.

The router is exercised via ``fastapi.TestClient`` and ``ImagesManager``
is mocked end-to-end, so the tests verify the HTTP contract (status
codes, request body parsing, response envelope) without touching the
filesystem. The few tests that go through the real upload path provide
a lightweight stub manager so we can assert temp-file streaming and
cleanup behaviour as well.
"""

import io
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routes.images as images_route
from api.routes.images import router as images_router


def _make_set_obj(
    name: str = "alpha",
    image_count: int = 5,
    extension: str = "png",
) -> MagicMock:
    obj = MagicMock()
    obj.name = name
    obj.source_archive = f"{name}.zip"
    obj.image_count = image_count
    obj.extension = extension
    obj.width = 1280
    obj.height = 720
    obj.uploaded_at = "2026-04-28T10:00:00Z"
    return obj


def _make_image_info(
    filename: str = "alpha_001.png",
    extension: str = "png",
    size_bytes: int = 12345,
) -> MagicMock:
    info = MagicMock()
    info.filename = filename
    info.extension = extension
    info.size_bytes = size_bytes
    info.width = 1280
    info.height = 720
    return info


class _BaseImagesAPITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(images_router, prefix="/images")
        cls.client = TestClient(app)


# --------------------------------------------------------------------------- #
# GET /images
# --------------------------------------------------------------------------- #


class TestGetImageSets(_BaseImagesAPITest):
    def test_returns_list_of_sets(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.get_all_image_sets.return_value = {
                "alpha": _make_set_obj("alpha", 5, "png"),
                "beta": _make_set_obj("beta", 7, "jpg"),
            }
            mock_cls.return_value = instance

            response = self.client.get("/images")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["name"], "alpha")
        self.assertEqual(data[0]["image_count"], 5)
        self.assertEqual(data[0]["extension"], "png")
        self.assertEqual(data[0]["width"], 1280)
        self.assertEqual(data[0]["height"], 720)
        self.assertEqual(data[0]["source_archive"], "alpha.zip")
        self.assertEqual(data[0]["uploaded_at"], "2026-04-28T10:00:00Z")

    def test_empty_list(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.get_all_image_sets.return_value = {}
            mock_cls.return_value = instance

            response = self.client.get("/images")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_unexpected_error_returns_500(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.get_all_image_sets.side_effect = RuntimeError("boom")
            mock_cls.return_value = instance

            response = self.client.get("/images")
        self.assertEqual(response.status_code, 500)
        self.assertIn("message", response.json())


# --------------------------------------------------------------------------- #
# GET /images/check-image-set-exists
# --------------------------------------------------------------------------- #


class TestCheckImageSetExists(_BaseImagesAPITest):
    def test_exists_true(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.image_set_exists.return_value = True
            mock_cls.return_value = instance
            response = self.client.get(
                "/images/check-image-set-exists", params={"name": "alpha"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"exists": True, "name": "alpha"})

    def test_exists_false(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.image_set_exists.return_value = False
            mock_cls.return_value = instance
            response = self.client.get(
                "/images/check-image-set-exists", params={"name": "missing"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"exists": False, "name": "missing"})

    def test_missing_query_param_is_422(self) -> None:
        response = self.client.get("/images/check-image-set-exists")
        self.assertEqual(response.status_code, 422)


# --------------------------------------------------------------------------- #
# POST /images/upload (pre-write validation)
# --------------------------------------------------------------------------- #


class TestUploadValidationRejections(_BaseImagesAPITest):
    """
    Cases where the route returns 422 before writing to disk. The
    manager is mocked so its filesystem side effects are never invoked.
    """

    def _post(self, filename: str, content: bytes = b"data") -> httpx.Response:
        files = {"file": (filename, io.BytesIO(content), "application/octet-stream")}
        return self.client.post("/images/upload", files=files)

    def test_unsupported_archive_extension(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.derive_trunk.return_value = None
            mock_cls.return_value = instance
            response = self._post("file.7z")
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "unsupported_archive_format")
        self.assertEqual(body["found"], "file.7z")
        self.assertIsInstance(body["allowed"], list)

    def test_invalid_archive_name(self) -> None:
        # The filename has a supported extension but sanitises to empty.
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.derive_trunk.return_value = None
            mock_cls.return_value = instance
            response = self._post("!!!.zip")
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "invalid_archive_name")
        self.assertEqual(body["found"], "!!!.zip")

    def test_image_set_already_exists_pre_check(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.derive_trunk.return_value = "dorota"
            instance.image_set_exists.return_value = True
            mock_cls.return_value = instance
            response = self._post("dorota.zip")
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "image_set_already_exists")
        self.assertEqual(body["found"], "dorota")


# --------------------------------------------------------------------------- #
# POST /images/upload (streaming + manager interaction)
# --------------------------------------------------------------------------- #


class TestUploadStreaming(_BaseImagesAPITest):
    def setUp(self) -> None:
        # The route writes the incoming archive to a temp file under
        # ``UPLOADED_IMAGES_DIR``. On CI that path (``/images/...``)
        # does not exist, so point the route at a per-test temp dir.
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-upload-test-")
        self._uploads_patch = patch.object(
            images_route, "UPLOADED_IMAGES_DIR", self._tmpdir
        )
        self._uploads_patch.start()

    def tearDown(self) -> None:
        self._uploads_patch.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _post(self, filename: str, content: bytes) -> httpx.Response:
        files = {"file": (filename, io.BytesIO(content), "application/zip")}
        return self.client.post("/images/upload", files=files)

    def test_archive_too_large_mid_stream(self) -> None:
        with patch.object(images_route, "UPLOAD_MAX_SIZE_BYTES", 16):
            with patch("api.routes.images.ImagesManager") as mock_cls:
                instance = MagicMock()
                instance.derive_trunk.return_value = "huge"
                instance.image_set_exists.return_value = False
                mock_cls.return_value = instance

                response = self._post("huge.zip", b"X" * 1024)

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "archive_too_large")
        self.assertGreater(body["found"], 16)
        self.assertEqual(body["allowed"], [16])

    def test_successful_upload_returns_201_and_set(self) -> None:
        captured_paths: list[str] = []

        def fake_register(temp_path: str, original: str):
            # Confirm the temp file actually exists when the manager is
            # called, so we know the route streamed bytes to disk first.
            captured_paths.append(temp_path)
            self.assertTrue(os.path.isfile(temp_path))
            return _make_set_obj("dorota", 40, "jpg")

        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.derive_trunk.return_value = "dorota"
            instance.image_set_exists.return_value = False
            instance.register_uploaded_archive.side_effect = fake_register
            mock_cls.return_value = instance

            response = self._post("dorota.zip", b"PK\x03\x04" + b"x" * 64)

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["name"], "dorota")
        self.assertEqual(body["image_count"], 40)
        self.assertEqual(body["extension"], "jpg")

        # Temp file must be cleaned up after the response is built.
        self.assertEqual(len(captured_paths), 1)
        self.assertFalse(os.path.isfile(captured_paths[0]))

    def test_manager_validation_error_mapped_to_422(self) -> None:
        from images import ImageUploadError

        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.derive_trunk.return_value = "bad"
            instance.image_set_exists.return_value = False
            instance.register_uploaded_archive.side_effect = ImageUploadError(
                "archive_mixed_image_extensions",
                "Mixed extensions found.",
                found=["jpg", "png"],
                allowed=None,
            )
            mock_cls.return_value = instance

            response = self._post("bad.zip", b"x" * 32)

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "archive_mixed_image_extensions")
        self.assertEqual(body["found"], ["jpg", "png"])
        self.assertEqual(body["detail"], "Mixed extensions found.")

    def test_manager_runtime_error_mapped_to_500(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.derive_trunk.return_value = "io"
            instance.image_set_exists.return_value = False
            instance.register_uploaded_archive.side_effect = RuntimeError("disk full")
            mock_cls.return_value = instance

            response = self._post("io.zip", b"x" * 32)

        self.assertEqual(response.status_code, 500)
        self.assertIn("disk full", response.json()["message"])

    def test_unexpected_exception_mapped_to_500(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.derive_trunk.return_value = "boom"
            instance.image_set_exists.return_value = False
            instance.register_uploaded_archive.side_effect = ValueError("???")
            mock_cls.return_value = instance

            response = self._post("boom.zip", b"x" * 32)

        self.assertEqual(response.status_code, 500)


# --------------------------------------------------------------------------- #
# GET /images/{name}
# --------------------------------------------------------------------------- #


class TestListImagesInSet(_BaseImagesAPITest):
    def test_returns_listing(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.get_images_in_set.return_value = [
                _make_image_info("alpha_01.png"),
                _make_image_info("alpha_02.png"),
            ]
            mock_cls.return_value = instance
            response = self.client.get("/images/alpha")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["filename"], "alpha_01.png")
        self.assertEqual(data[0]["extension"], "png")
        self.assertEqual(data[0]["width"], 1280)
        self.assertEqual(data[0]["height"], 720)
        self.assertEqual(data[0]["size_bytes"], 12345)

    def test_set_not_found_returns_404(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.get_images_in_set.return_value = None
            mock_cls.return_value = instance
            response = self.client.get("/images/missing")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"])

    def test_unexpected_error_returns_500(self) -> None:
        with patch("api.routes.images.ImagesManager") as mock_cls:
            instance = MagicMock()
            instance.get_images_in_set.side_effect = RuntimeError("oops")
            mock_cls.return_value = instance
            response = self.client.get("/images/x")
        self.assertEqual(response.status_code, 500)


if __name__ == "__main__":
    unittest.main()
