# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Verify: no target_media -> text path AND all media projections are searched."""

import asyncio
from types import SimpleNamespace

from llama_index.core.schema import NodeWithScore, TextNode

from api import retrieval as api
from schemas import RetrieveRequest


class FakeMediaProjection:
    def __init__(self, target):
        self.source = SimpleNamespace(
            source_id=f"{target}-source",
            configuration={"target_media": target},
            profile={
                "profile_hash": f"{target}-profile",
                "encoder_kind": "multimodal",
                "supported_roles": {
                    "image": ["image", "doc_image"],
                    "video": ["short_video", "l1_segment"],
                    "audio": ["l2_transcript"],
                }[target],
            },
            enabled=True,
        )
        self.kind = "vector"
        self.target = target
        self.requests = []

    def retrieve(self, request):
        self.requests.append(request)
        return [NodeWithScore(
            node=TextNode(id_=self.target, text=f"{self.target} text"), score=0.9,
        )]


class FakeTextProjection:
    def __init__(self):
        self.source = SimpleNamespace(
            source_id="text-source",
            configuration={},
            profile={"profile_hash": "text-profile"},
            enabled=True,
        )
        self.kind = "vector"
        self.queries = []

    def retrieve(self, request):
        self.queries.append(request.query)
        return []


def _setup(monkeypatch, targets):
    text_projection = FakeTextProjection()
    media = {target: FakeMediaProjection(target) for target in targets}
    pool = SimpleNamespace(
        asset_pool_id="pool-1",
        projections=(text_projection, *media.values()),
        serving=(text_projection, *media.values()),
    )
    library = SimpleNamespace(
        name="test-library",
        _select_asset_pools=lambda _: [pool],
    )
    monkeypatch.setattr(api.registry, "require", lambda reference: library)
    return text_projection, media


def test_unrestricted_request_searches_text_and_all_media(monkeypatch):
    retriever, media = _setup(monkeypatch, ["video", "audio", "image"])

    result = asyncio.run(api.retrieve(RetrieveRequest(
        query="find it",
        libraries=["test-library"],
    )))

    assert retriever.queries == ["find it"], "text path not searched"
    for target, projection in media.items():
        assert projection.requests, f"{target} projection not searched"
    ids = {hit.id for hit in result.retrieved_chunks}
    assert {"video", "audio", "image"} <= ids


def test_document_only_uses_text_path_and_skips_media(monkeypatch):
    retriever, media = _setup(monkeypatch, ["video", "image"])

    asyncio.run(api.retrieve(RetrieveRequest(
        query="find it",
        libraries=["test-library"],
        target_media=["document"],
    )))

    assert retriever.queries == ["find it"], "text path not searched"
    assert not media["video"].requests, "video projection should be skipped"
    assert not media["image"].requests, "image projection should be skipped"


def test_document_and_image_search_text_path_and_image_projection(monkeypatch):
    retriever, media = _setup(monkeypatch, ["video", "image"])

    asyncio.run(api.retrieve(RetrieveRequest(
        query="find it",
        libraries=["test-library"],
        target_media=["document", "image"],
    )))

    assert retriever.queries == ["find it"], "text path not searched"
    assert media["image"].requests, "image projection not searched"
    assert not media["video"].requests, "video projection should be skipped"
