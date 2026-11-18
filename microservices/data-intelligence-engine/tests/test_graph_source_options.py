# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A graph source's knowledge settings are checked when it is created."""

import pytest

from core.file_asset_library import FileAssetLibrary

from . import dbhub


def _library():
    return FileAssetLibrary(name="lib", databasehub=dbhub.with_graph(dbhub.object_hub()))


def test_a_graph_source_with_an_unknown_format_is_refused():
    library = _library()

    with pytest.raises(ValueError, match="Unsupported knowledge format"):
        library.create_source("g", dbhub.GRAPH_DATABASE, "space", {"asset_types": ["pdf"]})

    assert all(source.source_type != "graph" for source in library.sources.values())


def test_a_document_format_source_needs_extractor_access():
    with pytest.raises(ValueError, match="external_extractor"):
        _library().create_source("g", dbhub.GRAPH_DATABASE, "space", {"asset_types": ["okf", "document"]})


def test_extractor_access_is_kept_but_reported_masked():
    library = _library()
    options = {
        "asset_types": ["okf", "document"],
        "external_extractor": {"url": "http://okf-extractor:8080", "api_key": "secret"},
    }

    source = library.create_source("g", dbhub.GRAPH_DATABASE, "space", options)

    assert source.configuration["external_extractor"]["api_key"] == "secret"
    reported = next(s for s in library.to_out().sources if s.id == source.source_id)
    assert reported.operator_options["external_extractor"]["api_key"] == "***"


def test_a_graph_source_without_options_builds_from_okf():
    source = _library().create_source("g", dbhub.GRAPH_DATABASE, "space", {})

    assert source.source_type == "graph"
