# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""GenAI returns ranked (original index, score) pairs, limited by its config."""

import sys
from types import SimpleNamespace

import pytest
from llama_index.core.instrumentation.events.rerank import ReRankEndEvent
from llama_index.core.schema import NodeWithScore, TextNode

from core.postprocessor import RerankProcessor
from inference import ov_adapter


@pytest.fixture
def pipeline(monkeypatch):
    instances = []

    class Pipeline:
        Config = SimpleNamespace

        def __init__(self, path, device, config, **kwargs):
            self.top_n = config.top_n
            self.calls = []
            instances.append(self)

        def rerank(self, query, texts):
            self.calls.append((query, texts))
            # The best document was recalled last. GenAI sorts first, then
            # truncates using the configuration captured at construction.
            return [(2, 0.98), (0, 0.85), (1, 0.12)][:self.top_n]

    monkeypatch.setitem(sys.modules, "openvino_genai", SimpleNamespace(TextRerankPipeline=Pipeline))
    return instances


def candidates():
    return [NodeWithScore(node=TextNode(id_=str(i), text=text), score=score)
            for i, (text, score) in enumerate([("first", 0.99), ("second", 0.97), ("best", 0.95)])]


@pytest.mark.parametrize("keep_scores", [False, True])
def test_genai_maps_ranked_indices_without_mutating_recall(pipeline, monkeypatch, keep_scores):
    events = []
    monkeypatch.setattr(ov_adapter, "dispatcher", SimpleNamespace(event=events.append))
    adapter = ov_adapter.OpenVINOGenAIReranking("local-bge", top_n=2, keep_retrieval_score=keep_scores)
    nodes = candidates()
    before = [node.model_dump() for node in nodes]

    result = adapter.postprocess_nodes(nodes, query_str="query")

    assert [(node.node.node_id, node.score) for node in result] == [("2", 0.98), ("0", 0.85)]
    assert [node.model_dump() for node in nodes] == before
    assert result[0] is not nodes[2]
    assert result[0].node is not nodes[2].node
    if keep_scores:
        assert [node.node.metadata["retrieval_score"] for node in result] == [0.95, 0.99]
    else:
        assert all("retrieval_score" not in node.node.metadata for node in result)
    assert pipeline[0].calls == [("query", ["first", "second", "best"])]
    end = next(event for event in events if isinstance(event, ReRankEndEvent))
    assert [(node.node.node_id, node.score) for node in end.nodes] == [("2", 0.98), ("0", 0.85)]


def test_genai_cached_pipeline_honors_increasing_and_decreasing_request_top_n(pipeline):
    adapter = ov_adapter.OpenVINOGenAIReranking("local-bge", top_n=1)
    processor = RerankProcessor(adapter, top_n=1)
    nodes = candidates()

    for top_n in (1, 3, 2, 5, 1):
        result = processor.run(nodes, query_str="query", top_n=top_n)
        assert [node.node.node_id for node in result] == ["2", "0", "1"][:top_n]
        assert [node.score for node in result] == [0.98, 0.85, 0.12][:top_n]

    assert len(pipeline) == 1
    assert len(pipeline[0].calls) == 5


def test_genai_empty_candidates_skip_inference(pipeline):
    adapter = ov_adapter.OpenVINOGenAIReranking("local-bge", top_n=2)
    assert adapter.postprocess_nodes([], query_str="query") == []
    assert pipeline[0].calls == []


def test_factory_pads_candidates_to_the_model_limit(tmp_path, monkeypatch):
    """Variable-length candidates need fixed-length input within the position limit."""
    import config
    from core import postprocessor

    model = tmp_path / "bge-reranker"
    model.mkdir()
    (model / "openvino_model.xml").write_text("")
    (model / "openvino_model.bin").write_text("")
    (model / "tokenizer_config.json").write_text('{"model_max_length": 8192}')
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    seen = {}

    class Fake:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(ov_adapter, "OpenVINOGenAIReranking", Fake)
    postprocessor._build(config.LOCAL_OPENVINO, 3, "bge-reranker", "CPU", "")
    assert seen["pad_to_max_length"] is True
    assert seen["padding_side"] == "right"
    assert seen["max_length"] == config.EMBEDDING_MAX_LENGTH
