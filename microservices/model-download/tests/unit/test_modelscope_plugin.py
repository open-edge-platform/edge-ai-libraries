# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

import pytest

from src.plugins.modelscope_plugin import ModelScopePlugin


def test_modelscope_handles_only_its_hub():
    plugin = ModelScopePlugin()
    assert plugin.can_handle("iic/example", "ModelScope")
    assert not plugin.can_handle("iic/example", "huggingface")
    assert plugin.plugin_supported_hubs() == ["modelscope"]


def test_download_preserves_revision_and_registers_directory(tmp_path):
    expected = tmp_path / "modelscope" / "iic_example"
    expected.mkdir(parents=True)
    (expected / "config.yaml").write_text("model: example\n")
    registered = []
    with patch("src.plugins.modelscope_plugin.snapshot_download", return_value=str(expected)) as snapshot:
        result = ModelScopePlugin().download(
            "iic/example", str(tmp_path), revision="v2.0.4", _model_download_dir=registered,
        )
    snapshot.assert_called_once_with("iic/example", revision="v2.0.4", local_dir=str(expected))
    assert registered == [str(expected)]
    assert result["success"] is True
    assert result["download_path"] == str(expected)


@pytest.mark.parametrize("model", ["../escape", "/absolute", "owner/../escape", "owner\\escape", "owner/.."])
def test_download_rejects_unsafe_model_names(model, tmp_path):
    with pytest.raises(ValueError, match="owner/model"):
        ModelScopePlugin().download(model, str(tmp_path))


def test_download_rejects_symlink_destination(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    base = tmp_path / "models"
    base.mkdir()
    (base / "modelscope").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="inside the output directory"):
        ModelScopePlugin().download("iic/example", str(base))


def test_empty_snapshot_fails(tmp_path):
    expected = tmp_path / "modelscope" / "iic_example"
    with patch("src.plugins.modelscope_plugin.snapshot_download", return_value=str(expected)):
        with pytest.raises(RuntimeError, match="snapshot is empty"):
            ModelScopePlugin().download("iic/example", str(tmp_path))


def test_download_failure_propagates(tmp_path):
    with patch("src.plugins.modelscope_plugin.snapshot_download", side_effect=RuntimeError("download failed")):
        with pytest.raises(RuntimeError, match="download failed"):
            ModelScopePlugin().download("iic/example", str(tmp_path))


def test_unexpected_snapshot_directory_fails(tmp_path):
    with patch("src.plugins.modelscope_plugin.snapshot_download", return_value=str(tmp_path)):
        with pytest.raises(RuntimeError, match="unexpected snapshot directory"):
            ModelScopePlugin().download("iic/example", str(tmp_path))
