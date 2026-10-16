# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api import main
from src.api.models import ModelHub
from src.core.model_manager import ModelManager
from src.plugins.modelscope_plugin import ModelScopePlugin


def test_modelscope_is_a_registered_hub():
    assert ModelHub("modelscope") is ModelHub.MODELSCOPE
    plugin = ModelScopePlugin()
    assert plugin.can_handle("iic/example", "modelscope")
    assert not plugin.can_handle("iic/example", "huggingface")
    assert plugin.plugin_supported_hubs() == ["modelscope"]


def test_download_uses_modelscope_revision_and_records_exact_directory():
    snapshot = Mock()
    with tempfile.TemporaryDirectory() as base:
        expected = Path(base) / "modelscope" / "iic_example"
        snapshot.return_value = str(expected)
        with patch("src.plugins.modelscope_plugin.snapshot_download", snapshot):
            (expected).mkdir(parents=True)
            (expected / "configuration.json").write_text("{}", encoding="utf-8")
            registered = []
            result = ModelScopePlugin().download(
                "iic/example", base, revision="v2.0.4", _model_download_dir=registered
            )
        snapshot.assert_called_once_with(
            "iic/example", revision="v2.0.4", local_dir=str(expected)
        )
        assert result["source"] == "modelscope"
        assert registered == [str(expected)]


@pytest.mark.parametrize("model", ["../escape", "/absolute", "owner/../escape", "owner\\escape"])
def test_download_rejects_unsafe_model_names(model):
    with pytest.raises(ValueError):
        ModelScopePlugin().download(model, "/tmp/models")


def test_api_schedules_modelscope_download_and_exposes_result(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "models_dir", str(tmp_path))
    monkeypatch.setattr(main, "model_manager", ModelManager(main.plugin_registry, str(tmp_path)))

    def snapshot(model_id, *, revision, local_dir):
        Path(local_dir, "configuration.json").write_text("{}", encoding="utf-8")
        return local_dir

    with patch("src.plugins.modelscope_plugin.snapshot_download", side_effect=snapshot):
        with TestClient(main.app) as client:
            response = client.post(
                "/models/download?download_path=funasr",
                json={"models": [{"name": "iic/example", "hub": "modelscope", "revision": "v2.0.4"}]},
            )
            assert response.status_code == 200, response.text
            job_id = response.json()["job_ids"][0]
            for _ in range(50):
                job = client.get(f"/jobs/{job_id}").json()
                if job["status"] not in {"queued", "downloading"}:
                    break
                time.sleep(0.01)
            assert job["status"] == "completed", job
            assert job["result"]["source"] == "modelscope"
            assert (tmp_path / "funasr" / "modelscope" / "iic_example" / "configuration.json").exists()
