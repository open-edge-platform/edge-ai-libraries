# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Knowledge: assets to OKF bundles (extract) and bundles to a graph (build).
Writing the graph to a database is the GraphIndexer's job (test_graph_indexer).

Documents are chunks in vector sources; what a graph source holds is a bundle's
concepts, each citing the chunks it was drawn from, so graph retrieval can walk
from concept to concept and back to text.
"""

import json
from types import SimpleNamespace

import pytest

from core.knowledge import Knowledge, KnowledgeGraph, okf_nodes_to_graph, redact_operator_options
from core.knowledge.okf import OKFNode


def _okf_asset(asset_id="okf-1"):
    return SimpleNamespace(asset_id=asset_id, asset_kind="okf", origin="file:///w/bundle")


def _concepts():
    act = OKFNode(ctype="Act", title="ACT-01", okf_file_path="/act/act-01.md",
                  source_chunk_ids=["c1", "c2"], summaries=[("A pickpocketing incident.", "")],
                  links=[("defendant/周文斌", "committed_by")])
    person = OKFNode(ctype="Defendant", title="周文斌", okf_file_path="/defendant/周文斌.md")
    return [act, person]


# --- build: OKF bundles to a graph ---------------------------------------------


def test_concepts_become_vertices_and_links_edges():
    graph = Knowledge().build([_okf_asset()], {"okf-1": _concepts()})

    assert set(graph.vertices) == {"act/act-01", "defendant/周文斌"}
    assert graph.vertices["act/act-01"]["label"] == "Act"
    assert ("act/act-01", "committed_by", "defendant/周文斌") in graph.edges


def test_a_concept_vertex_carries_its_provenance_for_graph_search():
    vertex = Knowledge().build([_okf_asset()], {"okf-1": _concepts()}).vertices["act/act-01"]

    properties = vertex["properties"]
    assert properties["_node_type"] == "OKFConcept"
    content = json.loads(properties["_node_content"])
    assert json.loads(content["source_chunk_ids"]) == ["c1", "c2"]
    assert content["n_sources"] == 2
    assert content["gloss"].startswith("A pickpocketing")


def test_only_okf_assets_can_be_built():
    document = SimpleNamespace(asset_id="doc-1", asset_kind="document", origin="file:///w/a.pdf")

    with pytest.raises(ValueError, match="Only OKF assets"):
        Knowledge().build([document])


def test_the_request_shape_is_lists_of_vertices_and_edges():
    request = okf_nodes_to_graph(_concepts()).as_request()

    assert {vertex["id"] for vertex in request["vertices"]} == {"act/act-01", "defendant/周文斌"}
    assert request["edges"][0]["label"] == "committed_by"


# --- merging across a batch ---------------------------------------------------


def test_one_concept_defined_by_two_bundles_is_one_vertex():
    graph = Knowledge().build(
        [_okf_asset("okf-1"), _okf_asset("okf-2")], {"okf-1": _concepts(), "okf-2": _concepts()}
    )

    assert len(graph.vertices) == 2
    assert len(graph.edges) == 1


def test_the_same_relation_stated_twice_is_one_edge():
    graph = KnowledgeGraph()
    graph.add_edge("a", "RUNS_ON", "b")
    graph.add_edge("a", "RUNS_ON", "b")

    assert len(graph.edges) == 1


def test_a_second_mention_fills_gaps_without_overwriting():
    graph = KnowledgeGraph()
    graph.add_vertex("e1", "Concept", {"name": "Xeon"})
    graph.add_vertex("e1", "Concept", {"name": "XEON", "vendor": "Intel"})

    properties = graph.vertices["e1"]["properties"]
    assert properties["name"] == "Xeon", "first spelling wins"
    assert properties["vendor"] == "Intel", "new facts are still learned"


# --- formats: chosen by the source's asset_types --------------------------------


EXTRACTOR = {"url": "http://okf-extractor:8080", "api_key": "secret", "timeout": 60}


def _document(asset_id="doc-1"):
    return SimpleNamespace(asset_id=asset_id, asset_kind="document", origin="file:///w/a.pdf")


def test_okf_is_the_default_format():
    knowledge = Knowledge()

    assert knowledge.formats == ("okf",) and knowledge.extractor is None
    assert knowledge.accepts(_okf_asset()) and not knowledge.accepts(_document())


def test_asset_types_select_the_formats():
    assert Knowledge({"asset_types": ["okf"]}).formats == ("okf",)
    both = Knowledge({"asset_types": ["OKF", "document"], "external_extractor": EXTRACTOR})
    assert both.formats == ("okf", "document")
    assert both.accepts(_okf_asset()) and both.accepts(_document())


@pytest.mark.parametrize("options, message", [
    ({"asset_types": ["pdf"]}, "Unsupported knowledge format"),
    ({"asset_types": "okf"}, "must be a list"),
    ({"asset_types": ["document"], "external_extractor": EXTRACTOR}, 'needs "okf" too'),
    ({"asset_types": ["okf", "document"]}, "external_extractor must be an object"),
    ({"asset_types": ["okf", "document"], "external_extractor": {"url": "okf-extractor"}}, "http\\(s\\) URL"),
    ({"asset_types": ["okf", "document"], "external_extractor": {**EXTRACTOR, "timeout": 0}}, "positive"),
    ({"asset_types": ["okf", "document"], "external_extractor": {**EXTRACTOR, "token": "x"}}, "Unknown external_extractor"),
    ({"asset_types": ["okf"], "external_extractor": EXTRACTOR}, 'only used when asset_types includes "document"'),
])
def test_unusable_settings_are_refused(options, message):
    with pytest.raises(ValueError, match=message):
        Knowledge(options)


@pytest.mark.parametrize("options", [
    EXTRACTOR,
    {"asset_types": ["okf", "document"], **EXTRACTOR},
    {"url": "http://extractor", "trigger": {"mode": "auto", "debounce_seconds": 15}},
    {"options": {"language": "zh"}},
    {"debounce_seconds": 15},
    {"cron": "0 2 * * *", "timezone": "UTC"},
])
def test_misnested_extractor_settings_are_not_silently_treated_as_okf_only(options):
    with pytest.raises(ValueError, match="operator_options.external_extractor") as error:
        Knowledge(options)
    assert "secret" not in str(error.value)
    assert "asset_types" in str(error.value)


def test_the_extractor_is_configured_from_the_source():
    config = Knowledge({"asset_types": ["okf", "document"], "external_extractor": {**EXTRACTOR, "url": "https://x/"}}).extractor.config

    assert (config.url, config.api_key, config.timeout) == ("https://x", "secret", 60.0)


def test_extractor_credentials_are_masked_when_reported():
    options = {"asset_types": ["okf", "document"], "external_extractor": EXTRACTOR}

    reported = redact_operator_options(options)

    assert reported["external_extractor"]["api_key"] == "***"
    assert reported["external_extractor"]["url"] == EXTRACTOR["url"]
    assert options["external_extractor"]["api_key"] == "secret"     # stored value untouched


# --- extract: documents to OKF bundles ------------------------------------------


def test_extract_delegates_the_whole_task_to_the_configured_service(tmp_path, monkeypatch):
    knowledge = Knowledge({"asset_types": ["okf", "document"], "external_extractor": EXTRACTOR})
    documents = [_document("doc-1"), _document("doc-2")]
    calls = []

    def extract(assets, output_dir):
        calls.append((assets, output_dir))
        return [tmp_path / "bundle"]

    monkeypatch.setattr(knowledge.extractor, "extract", extract)
    assert knowledge.extract(documents, output_dir=tmp_path) == [tmp_path / "bundle"]
    assert calls == [(documents, tmp_path)]


def test_extract_needs_the_document_format():
    with pytest.raises(ValueError, match="does not take documents"):
        Knowledge().extract([_document()])


def test_okf_assets_are_already_bundles():
    with pytest.raises(ValueError, match="already bundles"):
        Knowledge().extract([_okf_asset()])
