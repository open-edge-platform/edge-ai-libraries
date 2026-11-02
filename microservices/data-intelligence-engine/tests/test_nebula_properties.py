# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Free-form graph properties fit Nebula's fixed Props__ schema."""

import json

import pytest

nebula = pytest.importorskip("databasehub.adapters.nebula")


def test_structural_asset_properties_are_packed_into_node_content():
    fitted = nebula._fit_properties(
        {"origin": "inline:46ac", "file_name": "notes.txt", "media_type": "", "block_count": 1}
    )

    assert set(fitted) <= set(nebula._PROPS_COLUMNS)
    assert fitted["file_name"] == "notes.txt"
    assert json.loads(fitted["_node_content"]) == {"origin": "inline:46ac", "media_type": "", "block_count": 1}


def test_an_okf_concept_is_written_unchanged():
    content = json.dumps({"title": "Edge AI", "source_chunk_ids": "[]"})
    properties = {"ref_doc_id": "concept/edge-ai", "_node_content": content, "_node_type": "OKFConcept"}

    assert nebula._fit_properties(properties) == properties


def test_extras_merge_into_existing_node_content_without_overwriting_it():
    fitted = nebula._fit_properties({"_node_content": json.dumps({"title": "kept"}), "title": "extra", "page": 3})

    assert json.loads(fitted["_node_content"]) == {"title": "kept", "page": 3}


def test_values_are_cast_to_their_column_type():
    fitted = nebula._fit_properties({"file_size": "42", "file_path": 7, "doc_id": None})

    assert fitted == {"file_size": 42, "file_path": "7"}
