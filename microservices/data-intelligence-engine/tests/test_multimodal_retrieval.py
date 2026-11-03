# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Source resolution and response contracts for LlamaIndex media retrieval."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from llama_index.core.schema import NodeWithScore, TextNode

from api import retrieval as api
from core.multimodal import retrieval as mm
from schemas import RetrieveRequest, RetrievedChunk


class FakeProjection:
    def __init__(self, target, via_block_kinds=False):
        configuration = (
            {"block_kinds": [target]} if via_block_kinds else {"target_media": target}
        )
        self.source = SimpleNamespace(
            source_id=f"{target}-source",
            configuration=configuration,
            profile={
                "profile_hash": f"{target}-profile",
                "encoder_kind": "multimodal",
                "supported_roles": {
                    "image": ["image", "doc_image"],
                    "video": ["short_video", "l1_segment"],
                    "audio": ["l2_transcript"],
                }[target],
            },
        )
        self.kind = "vector"
        self.collection = SimpleNamespace(name=f"{target}-collection")
        self.target = target
        self.requests = []
        self.scores = [0.9]

    def retrieve(self, request):
        self.requests.append(request)
        return [NodeWithScore(
            node=TextNode(
                id_=self.target if index == 0 else f"{self.target}-{index}",
                text=f"{self.target} text",
            ),
            score=score,
        ) for index, score in enumerate(self.scores)]


def _library(name, targets, via_block_kinds=False):
    pools = []
    projections = {}
    for target in targets:
        projection = FakeProjection(
            target,
            via_block_kinds=via_block_kinds and target == "video",
        )
        projections[target] = projection
        pools.append(SimpleNamespace(
            asset_pool_id=f"{target}-pool",
            projections=(projection,),
            serving=(projection,),
        ))
    library = SimpleNamespace(
        name=name,
        _select_asset_pools=lambda _: pools,
    )
    return library, projections


def _register(monkeypatch, libraries):
    monkeypatch.setattr(api.registry, "require", lambda reference: libraries[reference])


def _stub_media_scorer(monkeypatch, scorer):
    from core import postprocessor
    from inference import ov_adapter

    class _BatchScorer:
        """The adapter scores a whole request in one call; stubs stay per-pair."""

        def score_batch(self, query, documents):
            return [scorer.score(query, document) for document in documents]

    monkeypatch.setattr(postprocessor, "_VL_CACHE", {})
    monkeypatch.setattr(
        ov_adapter, "OpenVINOVLReranking",
        lambda path, device: _BatchScorer(),
    )


def test_multitarget_results_use_their_own_projections(monkeypatch):
    library, projections = _library("test-library", ["image", "audio"])
    _register(monkeypatch, {"test-library": library})

    result = asyncio.run(api.retrieve(RetrieveRequest(
        query="find it",
        libraries=["test-library"],
        target_media=["image", "audio"],
    )))

    assert [hit.id for hit in result.retrieved_chunks] == ["image", "audio"]
    assert result.chunks == result.retrieved_chunks
    assert projections["image"].requests[0].query == "find it"
    assert projections["audio"].requests[0].query == "find it"
    assert result.chunks[1].text == "audio text"


def test_block_kinds_bound_source_also_uses_projection_retrieve(monkeypatch):
    library, projections = _library("my-library", ["video"], via_block_kinds=True)
    _register(monkeypatch, {"my-library": library})

    result = asyncio.run(api.retrieve(RetrieveRequest(
        query="a person sitting",
        libraries=["my-library"],
        target_media=["video"],
        top_k=1,
    )))

    assert len(projections["video"].requests) == 1
    assert result.retrieved_chunks[0].id == "video"
    metadata = result.retrieved_chunks[0].metadata
    assert metadata["vector_source_id"] == "video-source"
    assert metadata["asset_pool_id"] == "video-pool"


def test_video_and_image_can_use_distinct_requested_libraries(monkeypatch):
    video_library, _ = _library("my-library", ["video"], via_block_kinds=True)
    image_library, _ = _library("multimedia-poc", ["image"])
    _register(monkeypatch, {
        "my-library": video_library,
        "multimedia-poc": image_library,
    })

    result = asyncio.run(api.retrieve(RetrieveRequest(
        query="cat",
        libraries=["my-library", "multimedia-poc"],
        target_media=["video", "image"],
    )))

    assert [hit.id for hit in result.chunks] == ["video", "image"]
    assert result.retrieved_chunks == result.chunks


def test_pool_ids_can_select_different_pools_across_libraries(monkeypatch):
    video_library, _ = _library("video-library", ["video"])
    audio_library, _ = _library("audio-library", ["audio"])
    _register(monkeypatch, {
        "video-library": video_library,
        "audio-library": audio_library,
    })
    result = asyncio.run(api.retrieve(RetrieveRequest(
        query="find it", libraries=["video-library", "audio-library"],
        asset_pool_ids=["video-pool", "audio-pool"],
        target_media=["video", "audio"],
    )))
    assert [hit.id for hit in result.chunks] == ["video", "audio"]
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.retrieve(RetrieveRequest(
            query="find it", libraries=["video-library", "audio-library"],
            asset_pool_ids=["unknown-pool"],
        )))
    assert error.value.status_code == 404


def test_http_contract_has_flat_hits_without_cross_modality_sorting(monkeypatch):
    from main import app

    library, projections = _library("test-library", ["audio", "image"])
    projections["audio"].scores = [0.2, 0.1]
    projections["image"].scores = [0.9, 0.8]
    _register(monkeypatch, {"test-library": library})
    response = TestClient(app).post("/v1/retrieve", json={
        "query": "find it",
        "libraries": ["test-library"],
        "target_media": ["audio", "image"],
        "top_k": 2,
    })

    assert response.status_code == 200
    data = response.json()
    assert "results_by_modality" not in data
    assert data["retrieved_chunks"] == data["chunks"]
    assert [hit["id"] for hit in data["chunks"]] == ["audio", "image", "audio-1", "image-1"]
    assert [hit["metadata"]["rank"] for hit in data["chunks"]] == [1, 2, 3, 4]
    assert [hit["score"] for hit in data["chunks"]] == [0.2, 0.9, 0.1, 0.8]
    assert set(data["chunks"][0]) == {"id", "text", "score", "metadata"}


def test_media_rerank_uses_top_k_candidates_then_returns_top_n(monkeypatch):
    library, projections = _library("test-library", ["audio"])
    projections["audio"].scores = [0.9, 0.8, 0.7, 0.6]
    _register(monkeypatch, {"test-library": library})
    from core.multimodal import reranking as media_reranker

    class Scorer:
        def score(self, query, document):
            return {"audio": 0.1, "audio-1": 0.99}[document["text"]]

    # FakeProjection exposes the candidate id in the text for this test.
    original = projections["audio"].retrieve
    def retrieve(request):
        hits = original(request)
        for hit in hits:
            hit.node.text = hit.node.node_id
        return hits
    projections["audio"].retrieve = retrieve
    _stub_media_scorer(monkeypatch, Scorer())

    result = asyncio.run(api.retrieve(RetrieveRequest(
        query="find it", libraries=["test-library"], target_media=["audio"],
        top_k=2, postprocess={},
    )))
    # Retrieval depth stays at top_k -- only those candidates enter reranking.
    assert projections["audio"].requests[0].top_k == 2
    assert [hit.id for hit in result.chunks] == ["audio-1", "audio"]
    assert [hit.id for hit in result.retrieved_chunks] == ["audio", "audio-1"]
    best = result.chunks[0]
    assert result.retrieved_chunks[1].score == 0.8
    assert best.score == 0.99
    assert set(best.model_dump()) == {"id", "text", "score", "metadata"}


def test_media_top_k_controls_depth_and_top_n_limits_output(monkeypatch):
    library, projections = _library("test-library", ["audio"])
    projections["audio"].scores = [0.9, 0.8, 0.7, 0.6]
    _register(monkeypatch, {"test-library": library})
    from core.multimodal import reranking as media_reranker

    class Scorer:
        def score(self, query, document):
            return 0.5

    _stub_media_scorer(monkeypatch, Scorer())
    result = asyncio.run(api.retrieve(RetrieveRequest(
        query="find it", libraries=["test-library"], target_media=["audio"],
        top_k=3, postprocess={"top_n": 2},
    )))
    assert projections["audio"].requests[0].top_k == 3
    assert len(result.retrieved_chunks) == 3
    assert len(result.chunks) == 2
    assert [hit.id for hit in result.chunks] == ["audio", "audio-1"]


def test_projection_value_error_fails_the_whole_request(monkeypatch):
    library, projections = _library("test-library", ["image", "audio"])
    _register(monkeypatch, {"test-library": library})

    def broken(request):
        raise ValueError("collection dimension mismatch")

    projections["image"].retrieve = broken
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.retrieve(RetrieveRequest(
            query="find it", libraries=["test-library"], target_media=["image", "audio"],
        )))
    assert error.value.status_code == 503
    assert "dimension mismatch" in error.value.detail
    assert projections["audio"].requests == []


def test_target_requires_a_serving_multimodal_vector_with_matching_role():
    library, projections = _library("test-library", ["image"])
    projection = projections["image"]
    assert mm.targeted_projections(library, "image")
    projection.kind = "graph"
    assert mm.targeted_projections(library, "image") == []
    projection.kind = "vector"
    projection.source.profile["encoder_kind"] = "text"
    assert mm.targeted_projections(library, "image") == []
    projection.source.profile["encoder_kind"] = "multimodal"
    projection.source.profile["supported_roles"] = ["l2_transcript"]
    assert mm.targeted_projections(library, "image") == []
    projection.source.profile["supported_roles"] = ["image"]
    projection.source.configuration["block_roles"] = ["l2_transcript"]
    assert mm.targeted_projections(library, "image") == []


def test_failed_media_model_degrades_the_whole_request_without_mixing_scores(monkeypatch):
    library, projections = _library("test-library", ["audio", "image"])
    projections["audio"].scores = [0.9, 0.8]
    projections["image"].scores = [0.7, 0.6]
    _register(monkeypatch, {"test-library": library})
    from core.multimodal import reranking as media_reranker

    class Scorer:
        def score(self, query, document):
            raise RuntimeError("model unavailable")

    _stub_media_scorer(monkeypatch, Scorer())
    monkeypatch.setattr(media_reranker, "_document", lambda hit, target, library: {"text": hit.text})
    result = asyncio.run(api.retrieve(RetrieveRequest(
        query="find it", libraries=["test-library"], target_media=["audio", "image"],
        top_k=2, postprocess={"top_n": 1},
    )))
    assert [hit.id for hit in result.retrieved_chunks] == ["audio", "image", "audio-1", "image-1"]
    assert [hit.id for hit in result.chunks] == ["audio", "image", "audio-1", "image-1"]
    assert [hit.score for hit in result.chunks] == [0.9, 0.7, 0.8, 0.6]
    assert [hit.metadata["rank"] for hit in result.chunks] == [1, 2, 3, 4]
    assert all(projections[target].requests[0].top_k == 2 for target in ("audio", "image"))


def test_media_rerank_orders_globally_across_targets(monkeypatch):
    library, projections = _library("test-library", ["audio", "image"])
    projections["audio"].scores = [0.9, 0.8]
    projections["image"].scores = [0.7, 0.6]
    _register(monkeypatch, {"test-library": library})
    from core.multimodal import reranking as media_reranker

    # FakeProjection exposes the candidate id in the text for this test; media
    # document assembly is covered by its own test.
    for target in ("audio", "image"):
        original = projections[target].retrieve
        def retrieve(request, original=original):
            hits = original(request)
            for hit in hits:
                hit.node.text = hit.node.node_id
            return hits
        projections[target].retrieve = retrieve
    monkeypatch.setattr(
        media_reranker, "_document", lambda hit, target, library: {"text": hit.text}
    )
    scores = {"audio": 0.50, "audio-1": 0.95, "image": 0.90, "image-1": 0.10}

    class Scorer:
        def score(self, query, document):
            return scores[document["text"]]

    _stub_media_scorer(monkeypatch, Scorer())

    result = asyncio.run(api.retrieve(RetrieveRequest(
        query="find it", libraries=["test-library"], target_media=["audio", "image"],
        top_k=3, postprocess={},
    )))
    # Global order: audio-1 (0.95), image (0.90), audio (0.50); image-1 is cut.
    assert [hit.id for hit in result.retrieved_chunks] == ["audio", "image", "audio-1", "image-1"]
    assert [hit.id for hit in result.chunks] == ["audio-1", "image", "audio"]
    assert [hit.metadata["rank"] for hit in result.chunks] == [1, 2, 3]
    assert [hit.score for hit in result.chunks] == [0.95, 0.90, 0.50]
    assert [hit.score for hit in result.retrieved_chunks] == [0.9, 0.7, 0.8, 0.6]


def test_media_model_defaults_are_independent_of_text(monkeypatch):
    from core.multimodal import reranking as media_reranker
    from schemas import PostprocessOptions

    seen = {}
    class Adapter:
        def __init__(self, path, device):
            seen.update(path=path, device=device)

    from inference import ov_adapter
    monkeypatch.setattr(ov_adapter, "OpenVINOVLReranking", Adapter)
    monkeypatch.setattr(media_reranker.config, "MEDIA_RERANK_MODEL_ID", "Qwen/Qwen3-VL-Reranker-2B")
    monkeypatch.setattr(media_reranker.config, "MEDIA_RERANK_MODEL_PATH", "/tmp/qwen-reranker-ov")
    monkeypatch.setattr(media_reranker.config, "MEDIA_RERANK_DEVICE", "CPU")
    monkeypatch.setattr(media_reranker.config, "RERANK_MODEL_ID", "BAAI/bge-reranker-large")
    from core import postprocessor
    monkeypatch.setattr(postprocessor, "_VL_CACHE", {})
    media_reranker.build_media_reranker(PostprocessOptions(), lambda index, node: {}, 1)
    assert seen == {"path": "/tmp/qwen-reranker-ov", "device": "CPU"}


def test_image_reranker_reads_authorized_bytes_and_preserves_recall_hit(monkeypatch):
    from io import BytesIO
    from PIL import Image
    from core.multimodal import reranking as media_reranker
    from schemas import PostprocessOptions

    image = BytesIO()
    Image.new("RGB", (2, 2), "red").save(image, format="PNG")
    reads = []
    library = SimpleNamespace(blob_reader=lambda: lambda key, source: (
        reads.append((key, source)) or image.getvalue()
    ))
    hits = [RetrievedChunk(
        id="red", text="caption", score=0.4,
        metadata={"media_key": "blobs/red.png", "source_id": "source-1"},
    )]

    class Scorer:
        def score(self, query, document):
            assert query == "red object"
            assert document["image"].getpixel((0, 0)) == (255, 0, 0)
            return 0.95

    _stub_media_scorer(monkeypatch, Scorer())
    ranked, status = media_reranker.rerank_media(
        "red object", [("image", hits, library)], PostprocessOptions(), 1,
    )
    assert status == "ok"
    assert reads == [("blobs/red.png", "source-1")]
    assert hits[0].score == 0.4
    assert ranked[0].score == 0.95


def test_media_reranker_failure_after_a_score_leaves_candidates_unchanged(monkeypatch):
    from core.multimodal import reranking as media_reranker
    from schemas import PostprocessOptions

    hits = [
        RetrievedChunk(id="first", text="first", score=0.8, metadata={"tag": "a"}),
        RetrievedChunk(id="second", text="second", score=0.7, metadata={"tag": "b"}),
    ]
    before = [hit.model_dump() for hit in hits]

    class Scorer:
        def score(self, query, document):
            if document["text"] == "second":
                raise RuntimeError("inference failed")
            return 0.99

    _stub_media_scorer(monkeypatch, Scorer())
    ranked, status = media_reranker.rerank_media(
        "query", [("audio", hits, SimpleNamespace())], PostprocessOptions(), 2,
    )
    assert ranked is None and status == "degraded"
    assert [hit.model_dump() for hit in hits] == before


def test_media_reranker_rejects_nonfinite_score(monkeypatch):
    from core.multimodal import reranking as media_reranker
    from schemas import PostprocessOptions

    class Scorer:
        def score(self, query, document):
            return float("nan")

    _stub_media_scorer(monkeypatch, Scorer())
    hits = [RetrievedChunk(id="one", text="one", score=0.8)]
    ranked, status = media_reranker.rerank_media(
        "query", [("audio", hits, SimpleNamespace())], PostprocessOptions(), 1,
    )
    assert ranked is None and status == "degraded"
    assert hits[0].score == 0.8


def test_all_unreadable_media_returns_empty_without_loading_model(monkeypatch):
    from core.multimodal import reranking as media_reranker
    from schemas import PostprocessOptions

    def unexpected(*args, **kwargs):
        raise AssertionError("model must not be loaded")

    monkeypatch.setattr(media_reranker, "build_media_reranker", unexpected)
    hits = [RetrievedChunk(id="missing", text="caption", score=0.8)]
    ranked, status = media_reranker.rerank_media(
        "query", [("image", hits, SimpleNamespace())], PostprocessOptions(), 1,
    )
    assert ranked == [] and status == "ok"


def test_media_reranker_keeps_library_context_with_duplicate_ids(monkeypatch):
    from core.multimodal import reranking as media_reranker
    from schemas import PostprocessOptions

    monkeypatch.setattr(
        media_reranker, "_document",
        lambda hit, target, library: {"text": library.name},
    )

    class Scorer:
        def score(self, query, document):
            return {"first": 0.1, "second": 0.9}[document["text"]]

    _stub_media_scorer(monkeypatch, Scorer())
    groups = [
        ("audio", [RetrievedChunk(id="same", text="first hit", score=0.8)], SimpleNamespace(name="first")),
        ("audio", [RetrievedChunk(id="same", text="second hit", score=0.7)], SimpleNamespace(name="second")),
    ]
    ranked, status = media_reranker.rerank_media("query", groups, PostprocessOptions(), 2)
    assert status == "ok"
    assert [hit.text for hit in ranked] == ["second hit", "first hit"]
    assert [hit.score for hit in ranked] == [0.9, 0.1]


def test_media_reranker_shared_scorer_is_serialized_across_requests(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import time

    from core.multimodal import reranking as media_reranker
    from schemas import PostprocessOptions

    gate = threading.Barrier(2)
    active_lock = threading.Lock()
    active = 0
    max_active = 0

    class Scorer:
        def score(self, query, document):
            nonlocal active, max_active
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.01)
            with active_lock:
                active -= 1
            return float(document["text"][-1])

    _stub_media_scorer(monkeypatch, Scorer())

    def request(library_name, top_n):
        hits = [
            RetrievedChunk(id=f"{library_name}-{i}", text=f"{library_name}-{i}", score=0.5)
            for i in range(2)
        ]
        gate.wait()
        return media_reranker.rerank_media(
            "query", [("audio", hits, SimpleNamespace(name=library_name))],
            PostprocessOptions(top_n=top_n), top_n,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(request, "a", 1)
        second = pool.submit(request, "b", 2)
        ranked_a, status_a = first.result()
        ranked_b, status_b = second.result()

    assert (status_a, status_b) == ("ok", "ok")
    assert [hit.id for hit in ranked_a] == ["a-1"]
    assert [hit.id for hit in ranked_b] == ["b-1", "b-0"]
    assert max_active == 1


def test_media_request_accepts_text_backend_for_transcript_and_rejects_bad_top_n(monkeypatch):
    library, projections = _library("test-library", ["audio"])
    _register(monkeypatch, {"test-library": library})
    seen = []
    def postprocess(query, chunks, processor_type, top_n, model):
        seen.append(model.backend)
        return chunks[:top_n]
    monkeypatch.setattr(api, "postprocess_chunks", postprocess)
    result = asyncio.run(api.retrieve(RetrieveRequest(
        query="find it", libraries=["test-library"], target_media=["audio"],
        postprocess={"reranker_model": {"backend": "llamaindex_openvino"}},
    )))
    assert [hit.id for hit in result.chunks] == ["audio"]
    assert seen == ["llamaindex_openvino"]
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.retrieve(RetrieveRequest(
            query="find it", libraries=["test-library"],
            target_media=["audio"], postprocess={"top_n": 0},
        )))
    assert error.value.status_code == 400


def test_media_asset_store_failure_is_reported(monkeypatch):
    library, _ = _library("test-library", ["audio", "image"])
    _register(monkeypatch, {"test-library": library})
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.retrieve(RetrieveRequest(
            query="find it", libraries=["test-library"],
            target_media=["image", "audio"], postprocess={},
        )))
    assert error.value.status_code == 503
    assert "cannot be read" in error.value.detail


def test_multiple_sources_are_searched_and_missing_target_is_rejected(monkeypatch):
    library, _ = _library("test-library", ["image", "image"])
    pools = library._select_asset_pools([])
    pools[1].asset_pool_id = "second-image-pool"
    _register(monkeypatch, {"test-library": library})
    result = asyncio.run(api.retrieve(RetrieveRequest(
        query="find it", libraries=["test-library"], target_media=["image"],
    )))
    assert len(result.chunks) == 2
    assert {hit.metadata["pool_id"] for hit in result.chunks} == {"image-pool", "second-image-pool"}

    with pytest.raises(HTTPException) as missing:
        asyncio.run(api.retrieve(RetrieveRequest(
            query="find it", libraries=["test-library"], target_media=["audio"],
        )))
    assert missing.value.status_code == 503
    assert "search unavailable" in missing.value.detail


def test_missing_default_target_does_not_discard_available_modality(monkeypatch):
    from main import app

    library, projections = _library("video-only", ["video"])
    _register(monkeypatch, {"video-only": library})

    response = TestClient(app).post("/v1/retrieve", json={
        "query": "a person sitting", "libraries": ["video-only"],
        "target_media": ["image", "video"], "allow_missing_targets": True,
    })
    assert response.status_code == 200
    assert [hit["id"] for hit in response.json()["chunks"]] == ["video"]
    assert [hit["id"] for hit in response.json()["retrieved_chunks"]] == ["video"]
    assert "results_by_modality" not in response.json()
    assert len(projections["video"].requests) == 1

    with pytest.raises(HTTPException) as all_missing:
        asyncio.run(api.retrieve(RetrieveRequest(
            query="a person sitting", libraries=["video-only"],
            target_media=["image"], allow_missing_targets=True,
        )))
    assert all_missing.value.status_code == 503


def test_unknown_library_is_not_inferred_from_milvus(monkeypatch):
    def missing(_reference):
        raise ValueError("library not found")

    monkeypatch.setattr(api.registry, "require", missing)
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.retrieve(RetrieveRequest(
            query="find it", libraries=["other"], target_media=["video"],
        )))
    assert error.value.status_code == 404


@pytest.mark.parametrize("score", [None, float("nan"), float("inf"), float("-inf")])
def test_invalid_score_fails_the_whole_request(monkeypatch, score):
    library, projections = _library("test-library", ["video", "image"])
    _register(monkeypatch, {"test-library": library})
    projections["video"].scores = [score]

    with pytest.raises(HTTPException) as error:
        asyncio.run(api.retrieve(RetrieveRequest(
            query="video query", libraries=["test-library"], target_media=["video", "image"],
        )))
    assert error.value.status_code == 503
    assert "invalid retrieval score" in error.value.detail
    assert projections["image"].requests == []
