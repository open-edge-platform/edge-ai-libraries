# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.timeseries import (
    WIND_TURBINE_UDF_PACKAGE,
    _validate_udf_package,
    router,
)


class TestUdfPackageValidation(unittest.TestCase):
    def _create_package(self, config: dict, files: dict[str, bytes]) -> str:
        temp_file = tempfile.NamedTemporaryFile(suffix=".tar", delete=False)
        temp_file.close()
        staging_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, staging_dir, ignore_errors=True)
        with tarfile.open(temp_file.name, "w") as archive:
            config_path = staging_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            archive.add(config_path, arcname="config.json")
            for filename, content in files.items():
                file_path = staging_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(content)
                archive.add(file_path, arcname=filename)
        self.addCleanup(Path(temp_file.name).unlink, missing_ok=True)
        return temp_file.name

    def test_valid_package_returns_udf_name_and_configuration(self):
        config = {
            "udfs": {
                "name": "windturbine_anomaly_detector",
                "models": "windturbine_anomaly_detector.pkl",
                "device": "cpu",
            }
        }
        package = self._create_package(
            config,
            {
                "models/windturbine_anomaly_detector.pkl": b"model",
                "udfs/windturbine_anomaly_detector.py": b"udf",
            },
        )

        name, result_config = _validate_udf_package(package, device="cpu")

        self.assertEqual(name, "windturbine_anomaly_detector")
        self.assertEqual(result_config, config)

    def test_package_rejects_config_model_missing_from_archive(self):
        package = self._create_package(
            {
                "udfs": {
                    "name": "detector",
                    "models": "detector.pkl",
                    "device": "cpu",
                }
            },
            {"udfs/detector.py": b"udf"},
        )

        with self.assertRaisesRegex(ValueError, "model file in models"):
            _validate_udf_package(package)

    def test_package_rejects_udf_name_without_matching_filename(self):
        package = self._create_package(
            {
                "udfs": {
                    "name": "detector",
                    "models": "model.pkl",
                    "device": "cpu",
                }
            },
            {"models/model.pkl": b"model", "udfs/other.py": b"udf"},
        )

        with self.assertRaisesRegex(ValueError, "name in config.json"):
            _validate_udf_package(package)

    def test_package_without_config_derives_udf_and_model_names(self):
        package = self._create_package(
            {},
            {
                "models/windturbine_anomaly_detector.pkl": b"model",
                "udfs/windturbine_anomaly_detector.py": b"udf",
            },
        )

        name, config = _validate_udf_package(package, device="cpu")

        self.assertEqual(name, "windturbine_anomaly_detector")
        self.assertEqual(
            config,
            {
                "udfs": {
                    "name": "windturbine_anomaly_detector",
                    "models": "windturbine_anomaly_detector.pkl",
                    "device": "cpu",
                }
            },
        )


class TestUdfDeploymentAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(router, prefix="/timeseries")
        cls.client = TestClient(app)

    def test_deploy_uploads_package_then_applies_configuration(self):
        requests: list[tuple[str, dict]] = []
        package_file = tempfile.NamedTemporaryFile(suffix=".tar", delete=False)
        package_file.write(b"archive")
        package_file.close()
        self.addCleanup(Path(package_file.name).unlink, missing_ok=True)

        class FakeResponse:
            status_code = 200

        class FakeAsyncClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def post(self, url, **kwargs):
                requests.append((url, kwargs))
                return FakeResponse()

        with (
            patch(
                "api.routes.timeseries._write_upload_to_tempfile",
                return_value=package_file.name,
            ),
            patch(
                "api.routes.timeseries._validate_udf_package",
                return_value=(
                    "detector",
                    {"udfs": {"name": "detector", "models": "detector.pkl"}},
                ),
            ),
            patch("api.routes.timeseries.httpx.AsyncClient", FakeAsyncClient),
        ):
            response = self.client.post(
                "/timeseries/udfs/deploy",
                data={"source": "upload"},
                files={"file": ("detector.tar", b"archive", "application/x-tar")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["udf_name"], "detector")
        self.assertEqual(
            [url.rsplit("/", 1)[-1] for url, _ in requests],
            [
                "package",
                "config",
            ],
        )
        self.assertIn("files", requests[0][1])
        self.assertEqual(requests[1][1]["json"]["udfs"]["name"], "detector")

    def test_model_download_uses_wind_turbine_package(self):
        with patch(
            "api.routes.timeseries._download_udf_package", return_value="/tmp/test.tar"
        ) as download:
            with patch(
                "api.routes.timeseries._validate_udf_package",
                side_effect=ValueError("stop after download"),
            ):
                response = self.client.post(
                    "/timeseries/udfs/deploy",
                    data={"source": "model-download", "device": "cpu"},
                )

        self.assertEqual(response.status_code, 400)
        download.assert_called_once_with(WIND_TURBINE_UDF_PACKAGE)
