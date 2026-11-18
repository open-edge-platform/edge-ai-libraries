# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The HTTP surface of multi-source: PATCH, `replaces`, and what is reported."""

import asyncio

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

from api import asset_library as asset_library_api
from schemas import AssetPoolSourcesIn, SourceIn, SourceUpdate

from tests.test_sources.fakes import Library, add_source, ingest


class _Registry:
    def __init__(self, library):
        self.library = library

    def get(self, ref):
        return self.library if ref == self.library.name else None

    def save(self):
        pass


@pytest.fixture
def library(monkeypatch):
    library = Library()
    add_source(library, "f8")
    library.create_asset_pool(asset_pool_id="pool", name="pool", source_configurations=[{"source_id": "f8"}])
    ingest(library, "pool", "a")
    library.sync_asset_pool("pool")
    add_source(library, "f16")
    monkeypatch.setattr(asset_library_api, "registry", _Registry(library))
    return library


def _run(coroutine):
    return asyncio.run(coroutine)


def test_a_patch_may_not_name_what_a_source_embeds_with():
    with pytest.raises(ValidationError):
        SourceUpdate.model_validate({"operator_options": {"frames_per_clip": 16}})
    assert SourceUpdate.model_validate({"enabled": False}).enabled is False


def test_a_source_needs_no_collection_name():
    assert SourceIn(name="s", database_id="db").collection_name is None


def test_pool_sources_accept_a_replacement_entry(library):
    body = AssetPoolSourcesIn.model_validate(
        {"sources": ["f8", {"source_id": "f16", "replaces": "f8"}]}
    )
    out = _run(
        asset_library_api.set_asset_pool_sources("library", "pool", body, BackgroundTasks())
    )
    statuses = {status.source_id: status for status in out.source_statuses}
    assert statuses["f16"].serving_state == "PREPARING"
    assert statuses["f16"].replaces == "f8"
    assert statuses["f8"].effective_state == "SERVING"


def test_a_refused_replacement_is_a_422(library):
    body = AssetPoolSourcesIn.model_validate({"sources": [{"source_id": "f16", "replaces": "f8"}]})
    with pytest.raises(HTTPException) as caught:
        _run(asset_library_api.set_asset_pool_sources("library", "pool", body, BackgroundTasks()))
    assert caught.value.status_code == 422


def test_patching_enabled_reports_bindings_and_schedules_the_catch_up(library):
    _run(asset_library_api.update_source("library", "f8", SourceUpdate(enabled=False), BackgroundTasks()))
    ingest(library, "pool", "b")
    tasks = BackgroundTasks()

    out = _run(asset_library_api.update_source("library", "f8", SourceUpdate(enabled=True), tasks))

    assert out.enabled is True
    assert [(b.pool_id, b.serving_state) for b in out.bindings] == [("pool", "PREPARING")]
    assert len(tasks.tasks) == 1, "the pool is synced in the background"


def test_disabling_a_content_source_is_refused(library):
    library.adopt_content_database("objects")
    content_id = library.default_content_source_id
    with pytest.raises(HTTPException) as caught:
        _run(asset_library_api.update_source("library", content_id, SourceUpdate(enabled=False), BackgroundTasks()))
    assert caught.value.status_code == 422


def test_patching_an_unknown_source_is_a_404(library):
    with pytest.raises(HTTPException) as caught:
        _run(asset_library_api.update_source("library", "nope", SourceUpdate(name="x"), BackgroundTasks()))
    assert caught.value.status_code == 404
