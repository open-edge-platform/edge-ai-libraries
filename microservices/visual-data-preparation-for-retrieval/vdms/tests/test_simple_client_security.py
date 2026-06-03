# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib
import uuid

import pytest

from src.core.embedding.simple_client import SimpleVDMSClient


def test_load_metadata_json_allows_cwd_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text('{"key": "value"}', encoding="utf-8")

    metadata = SimpleVDMSClient._load_metadata_json(metadata_file)

    assert metadata["key"] == "value"


def test_load_metadata_json_rejects_untrusted_path(tmp_path):
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text('{"key": "value"}', encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported metadata path location"):
        SimpleVDMSClient._load_metadata_json(metadata_file)


def test_load_metadata_json_allows_tmp_dataprep():
    tmp_dataprep = pathlib.Path("/tmp/dataprep")
    tmp_dataprep.mkdir(parents=True, exist_ok=True)
    metadata_file = tmp_dataprep / f"metadata-{uuid.uuid4().hex}.json"
    metadata_file.write_text('{"num": 1}', encoding="utf-8")

    try:
        metadata = SimpleVDMSClient._load_metadata_json(metadata_file)
        assert metadata["num"] == 1
    finally:
        if metadata_file.exists():
            metadata_file.unlink()
