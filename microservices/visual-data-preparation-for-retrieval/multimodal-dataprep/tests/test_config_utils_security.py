# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib
import uuid

import pytest

from src.core.utils.config_utils import read_config


def test_read_config_allows_files_under_current_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "config.yaml"
    config_file.write_text("frame_interval: 10\n", encoding="utf-8")

    config = read_config(config_file, type="yaml")

    assert config["frame_interval"] == 10


def test_read_config_rejects_untrusted_absolute_path(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("frame_interval: 10\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported config path location"):
        read_config(config_file, type="yaml")


def test_read_config_allows_files_under_tmp_dataprep():
    tmp_dataprep = pathlib.Path("/tmp/dataprep")
    tmp_dataprep.mkdir(parents=True, exist_ok=True)
    config_file = tmp_dataprep / f"config-{uuid.uuid4().hex}.json"
    config_file.write_text('{"frame_interval": 11}', encoding="utf-8")

    try:
        config = read_config(config_file, type="json")
        assert config["frame_interval"] == 11
    finally:
        if config_file.exists():
            config_file.unlink()
