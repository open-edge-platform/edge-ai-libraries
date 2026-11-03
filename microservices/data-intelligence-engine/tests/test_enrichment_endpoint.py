# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Reporting how far a media asset's description has got.

This endpoint exists because a pool's `ready` cannot answer the question it
gets asked. `ready` means a backend holds what the asset currently says; it
says nothing about whether the asset has finished saying it. A clip can be
`ready` everywhere while a vision model is still watching it, and it is
`ready` in exactly the same way for a recording nothing will ever describe.

So the three states a user actually cares about -- still working, it failed,
this kind of media is not supported yet -- are reported here instead, where
they can be told apart.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import config

from api import asset_library as asset_library_api
from core.content import (
    ROLE_IMAGE,
    ROLE_LONG_VIDEO,
    ROLE_SHORT_VIDEO,
    VIDEO,
    ContentBlock,
    ContentStream,
)


def _library_with(stream, monkeypatch, pools=None):
    asset = SimpleNamespace(asset_id=stream.asset_id, content=stream)

    class FakeLibrary:
        assets = {stream.asset_id: asset}
        asset_pools = pools or {}

    class FakeRegistry:
        def get(self, library):
            return FakeLibrary()

    monkeypatch.setattr(asset_library_api, "registry", FakeRegistry())


def _stream(asset_id="a1", role=ROLE_SHORT_VIDEO, **metadata):
    block = ContentBlock(
        block_id=f"{asset_id}:0",
        kind=VIDEO,
        media_key="blobs/abc",
        metadata={"role": role},
    )
    return ContentStream(
        asset_id=asset_id, blocks=[block], metadata={"asset_id": asset_id, **metadata}
    )


def _get(asset_id="a1"):
    return asyncio.run(
        asset_library_api.get_asset_enrichment("library-1", asset_id)
    )


@pytest.fixture(autouse=True)
def _summary_service(monkeypatch):
    monkeypatch.setattr(config, "VIDEO_SUMMARY_BASE_URL", "http://summary:8000")


def test_a_clip_waiting_to_be_described_reports_pending(monkeypatch):
    _library_with(_stream(), monkeypatch)

    result = _get()

    assert result.asset_id == "a1"
    assert result.role == ROLE_SHORT_VIDEO
    assert result.caption_status == "pending"
    assert result.error is None


def test_a_finished_description_reports_completed_with_a_timestamp(monkeypatch):
    _library_with(
        _stream(caption_status="completed", caption_updated_at=1760000000.0),
        monkeypatch,
    )

    result = _get()

    assert result.caption_status == "completed"
    assert result.updated_at == 1760000000.0


def test_a_failure_reports_the_reason_rather_than_just_a_state(monkeypatch):
    """Otherwise the only way to learn why is to read the engine's logs."""
    _library_with(
        _stream(caption_status="failed", caption_error="Video summary request failed: timeout"),
        monkeypatch,
    )

    result = _get()

    assert result.caption_status == "failed"
    assert "timeout" in result.error


def test_a_recording_nothing_describes_is_skipped_not_failed(monkeypatch):
    """Captioning reports on captioning only; it says nothing of the vector."""
    _library_with(_stream(role=ROLE_LONG_VIDEO), monkeypatch)

    result = _get()

    assert result.caption_status == "skipped"
    assert result.role == ROLE_LONG_VIDEO
    assert result.error is None


def test_an_asset_in_no_pool_reports_embedding_as_unassigned(monkeypatch):
    _library_with(_stream(), monkeypatch)

    assert _get().embedding_status == "unassigned"


def test_without_a_service_a_clip_reports_skipped_not_pending(monkeypatch):
    monkeypatch.setattr(config, "VIDEO_SUMMARY_BASE_URL", "")
    _library_with(_stream(), monkeypatch)

    result = _get()

    assert result.caption_status == "skipped"
    assert "ENGINE_VIDEO_SUMMARY_BASE_URL" in result.error


def test_a_covered_clip_reports_its_embedding_progress_beside_its_caption(monkeypatch):
    from tests.test_embedding_coverage import covered_pool

    _library_with(_stream(), monkeypatch, pools={"p": covered_pool("a1", ready=True)})

    result = _get()

    assert result.embedding_status == "ready"
    assert result.caption_status == "pending", "the two pipelines are independent"


def test_media_no_source_can_embed_says_why(monkeypatch):
    from tests.test_embedding_coverage import covered_pool

    _library_with(
        _stream(role=ROLE_LONG_VIDEO), monkeypatch, pools={"p": covered_pool("a1")}
    )

    result = _get()

    assert result.embedding_status == "no_source"
    assert "long_video" in result.embedding_reason


def test_an_image_is_not_described(monkeypatch):
    """Skipped for captioning is a statement about captioning, not about search."""
    _library_with(_stream(role=ROLE_IMAGE), monkeypatch)

    assert _get().caption_status == "skipped"


def test_an_unknown_asset_is_a_404(monkeypatch):
    _library_with(_stream(), monkeypatch)

    with pytest.raises(HTTPException) as caught:
        _get("no-such-asset")

    assert caught.value.status_code == 404


# --- telling the caller at ingest, not at search time -------------------------


def _warnings(library, role, asset_id="a1", path="/w/long.mp4"):
    stream = _stream(asset_id=asset_id, role=role)
    return asset_library_api._uncovered_media_warnings(
        library, {asset_id: (path, stream)}
    )


def test_ingest_warns_about_media_no_source_in_its_pools_can_embed():
    from tests.test_embedding_coverage import _library, covered_pool

    warnings = _warnings(_library(covered_pool("a1")), ROLE_LONG_VIDEO)

    assert len(warnings) == 1
    assert "long.mp4 is stored but will not be embedded" in warnings[0]
    assert "long_video" in warnings[0]


def test_ingest_stays_quiet_when_a_source_covers_the_media():
    from tests.test_embedding_coverage import _library, covered_pool

    assert _warnings(_library(covered_pool("a1")), ROLE_SHORT_VIDEO) == []


def test_ingest_stays_quiet_for_an_asset_in_no_pool():
    """Nothing was promised, so nothing is broken."""
    from tests.test_embedding_coverage import _library

    assert _warnings(_library(), ROLE_LONG_VIDEO) == []
