"""Functional tests for exporting a pipeline variant as a standalone app."""

import hashlib
import io
import json
import zipfile

import pytest
import requests

from helpers.config import BASE_URL
from helpers.pipeline_case_helpers import skip_if_pipeline_models_missing

EXPORTABLE_PIPELINE_ID = "defect-detection"
UNSUPPORTED_PIPELINE_ID = "goods-detection"


def _export_url(pipeline_id: str, variant_id: str) -> str:
    return f"{BASE_URL}/pipelines/{pipeline_id}/variants/{variant_id}/export-app"


@pytest.mark.smoke
def test_export_defect_detection_cpu_variant_as_app(
    http_client: requests.Session,
) -> None:
    skip_if_pipeline_models_missing(http_client, EXPORTABLE_PIPELINE_ID)

    response = http_client.post(_export_url(EXPORTABLE_PIPELINE_ID, "cpu"), timeout=300)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "defect-detection-cpu-app.zip" in response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        root = "defect-detection-cpu-app"
        names = set(archive.namelist())
        for path in (
            "compose.yml",
            "README.md",
            "pipelines.json",
            "manifest.json",
            "start_app.sh",
            "run.sh",
            "status.sh",
            "stop.sh",
            "stop_app.sh",
            "scripts/common.sh",
            "output/",
        ):
            assert f"{root}/{path}" in names, path

        launch_strings = json.loads(archive.read(f"{root}/pipelines.json"))
        assert set(launch_strings) == {"fakesink", "file", "rtsp"}

        manifest = json.loads(archive.read(f"{root}/manifest.json"))
        assert manifest["pipeline"]["id"] == EXPORTABLE_PIPELINE_ID
        assert manifest["variant"]["id"] == "cpu"
        assert manifest["devices"] == ["CPU"]
        assert any(asset["path"].endswith(".xml") for asset in manifest["assets"])
        for asset in manifest["assets"]:
            data = archive.read(f"{root}/{asset['path']}")
            assert len(data) == asset["size"], asset["path"]
            assert hashlib.sha256(data).hexdigest() == asset["sha256"], asset["path"]


@pytest.mark.smoke
def test_export_unsupported_pipeline_as_app_returns_400(
    http_client: requests.Session,
) -> None:
    response = http_client.post(_export_url(UNSUPPORTED_PIPELINE_ID, "cpu"), timeout=60)

    assert response.status_code == 400, response.text
    assert response.json()["message"]


@pytest.mark.smoke
def test_export_unknown_variant_as_app_returns_404(
    http_client: requests.Session,
) -> None:
    response = http_client.post(
        _export_url(EXPORTABLE_PIPELINE_ID, "no-such-variant"), timeout=60
    )

    assert response.status_code == 404, response.text
