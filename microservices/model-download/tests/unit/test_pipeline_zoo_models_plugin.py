# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile
from pathlib import Path

import pytest

from src.plugins.pipeline_zoo_models_plugin import PipelineZooModelsPlugin


class TestPipelineZooModelsPlugin:
    @pytest.fixture
    def plugin(self):
        return PipelineZooModelsPlugin()

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_plugin_properties(self, plugin):
        assert plugin.plugin_name == "pipeline-zoo-models"
        assert plugin.plugin_type == "downloader"

    @pytest.mark.parametrize(
        "hub,expected",
        [
            ("pipeline-zoo-models", True),
            ("pipeline_zoo_models", True),
            ("pipeline-zoo", True),
            ("PIPELINE-ZOO-MODELS", True),
            ("ultralytics", False),
        ],
    )
    def test_can_handle(self, plugin, hub, expected):
        assert plugin.can_handle("model_a", hub) is expected

    def test_can_handle_does_not_trigger_download(self, plugin, monkeypatch):
        # can_handle must never invoke the repo download path.
        def _fail(*args, **kwargs):
            raise AssertionError("can_handle must not fetch the repo")

        monkeypatch.setattr(plugin, "_ensure_repo_downloaded", _fail)

        assert plugin.can_handle("dbnet", "other") is False
        assert plugin.can_handle("all", "other") is False

    def test_download_success(self, plugin, temp_dir, monkeypatch):
        fake_repo_dir = Path(temp_dir) / "pipeline-zoo-models-main"
        source_model_dir = os.path.join(str(fake_repo_dir), "storage", "dbnet")
        os.makedirs(source_model_dir, exist_ok=True)
        Path(source_model_dir, "model.xml").write_text("<xml/>", encoding="utf-8")

        monkeypatch.setattr(plugin, "_ensure_repo_downloaded", lambda: fake_repo_dir)

        result = plugin.download("dbnet", temp_dir)

        target_model_dir = Path(temp_dir) / "pipeline-zoo-models" / "dbnet"
        assert target_model_dir.is_dir()
        assert (target_model_dir / "model.xml").is_file()
        assert result["success"] is True
        assert result["source"] == "pipeline-zoo-models"

    def test_download_missing_model(self, plugin, temp_dir, monkeypatch):
        fake_repo_dir = Path(temp_dir) / "pipeline-zoo-models-main"
        os.makedirs(os.path.join(str(fake_repo_dir), "storage"), exist_ok=True)

        monkeypatch.setattr(plugin, "_ensure_repo_downloaded", lambda: fake_repo_dir)

        with pytest.raises(RuntimeError, match="not found"):
            plugin.download("missing-model", temp_dir)

    def test_download_all_models(self, plugin, temp_dir, monkeypatch):
        fake_repo_dir = Path(temp_dir) / "pipeline-zoo-models-main"
        for model_name in ["dbnet", "yolov5m-320"]:
            source_model_dir = os.path.join(str(fake_repo_dir), "storage", model_name)
            os.makedirs(source_model_dir, exist_ok=True)
            Path(source_model_dir, "model.xml").write_text("<xml/>", encoding="utf-8")

        monkeypatch.setattr(plugin, "_ensure_repo_downloaded", lambda: fake_repo_dir)

        result = plugin.download("all", temp_dir)

        assert (Path(temp_dir) / "pipeline-zoo-models" / "dbnet" / "model.xml").is_file()
        assert (Path(temp_dir) / "pipeline-zoo-models" / "yolov5m-320" / "model.xml").is_file()
        assert result["success"] is True
