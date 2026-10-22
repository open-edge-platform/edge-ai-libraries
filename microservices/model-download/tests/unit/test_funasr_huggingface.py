# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api import main
from src.api.models import ModelHub
from src.core.model_manager import ModelManager
from src.plugins import PLUGINS


FUNASR_SNAPSHOTS = [
    ("funasr/paraformer-zh", "d7811ee3ac581fbcfdeb37c98c6ba674028433dc"),
    ("funasr/fsmn-vad", "df20e6b30c653645fa4ff125cacfcabd1020a669"),
    ("funasr/ct-punc", "d0e55e2b8722a78b63705ff443d09c4f86e5d750"),
]


def test_modelscope_is_not_a_registered_hub():
    assert "modelscope" not in PLUGINS
    with pytest.raises(ValueError):
        ModelHub("modelscope")


def test_api_downloads_funasr_and_companions_through_huggingface(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "models_dir", str(tmp_path))
    monkeypatch.setattr(main, "model_manager", ModelManager(main.plugin_registry, str(tmp_path)))

    def snapshot(*, repo_id, token, local_dir, revision):
        assert (repo_id, revision) in FUNASR_SNAPSHOTS
        Path(local_dir, "config.yaml").write_text("model: example\n", encoding="utf-8")
        Path(local_dir, "model.pt").touch()
        return local_dir

    with patch("src.plugins.huggingface_plugin.HuggingFacePlugin._check_access"), \
         patch("src.plugins.huggingface_plugin.snapshot_download", side_effect=snapshot) as download:
        with TestClient(main.app) as client:
            response = client.post(
                "/models/download?download_path=funasr",
                json={"models": [
                    {"name": name, "hub": "huggingface", "revision": revision}
                    for name, revision in FUNASR_SNAPSHOTS
                ]},
            )
            assert response.status_code == 200, response.text
            job_ids = response.json()["job_ids"]
            assert len(job_ids) == 3
            for job_id in job_ids:
                for _ in range(100):
                    job = client.get(f"/jobs/{job_id}").json()
                    if job["status"] not in {"queued", "downloading"}:
                        break
                    time.sleep(0.01)
                assert job["status"] == "completed", job
                assert job["result"]["source"] == "huggingface"
            assert download.call_count == 3
            for name, _ in FUNASR_SNAPSHOTS:
                assert (tmp_path / "funasr" / "huggingface" / name.replace("/", "_") / "model.pt").is_file()


def test_api_rejects_removed_modelscope_hub():
    with TestClient(main.app) as client:
        response = client.post(
            "/models/download",
            json={"models": [{"name": "iic/example", "hub": "modelscope"}]},
        )
    assert response.status_code == 422
