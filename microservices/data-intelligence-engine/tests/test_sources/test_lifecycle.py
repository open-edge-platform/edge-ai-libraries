# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Switching sources off and on, deleting through frozen bindings, restoring."""

import gc
from types import SimpleNamespace
from unittest.mock import Mock
import weakref

import pytest

from assetlib.sources.binding import DEGRADE, DISABLED, PREPARING, SERVING, effective_state
from assetlib.sources.updates import SourceRuleError
from inference.model_cache import ModelCache

from tests.test_sources.fakes import Library, add_source, ingest, serving_ids, state


def _pool(library, pool_id="pool", sources=("f8",), assets=("a", "b")):
    for source_id in sources:
        if source_id not in library.sources:
            add_source(library, source_id)
    library.create_asset_pool(
        asset_pool_id=pool_id,
        name=pool_id,
        source_configurations=[{"source_id": source_id} for source_id in sources],
    )
    ids = ingest(library, pool_id, *assets)
    library.sync_asset_pool(pool_id)
    return ids


def test_disabling_a_source_freezes_it_in_every_pool():
    library = Library()
    _pool(library, "A")
    _pool(library, "B")

    resync = library.update_source("f8", enabled=False)

    assert resync == []
    for pool_id in ("A", "B"):
        pool = library.asset_pools[pool_id]
        assert pool.projections == () and "f8" in pool.frozen_sources
        assert serving_ids(library, pool_id) == []
        status = pool.source_statuses["f8"]
        assert status.serving_state == SERVING, "the stored state is kept"
        assert effective_state(library.sources["f8"], status) == DISABLED


def test_a_disabled_source_takes_no_writes_and_catches_up_when_enabled():
    library = Library()
    _pool(library)
    library.update_source("f8", enabled=False)
    ingest(library, "pool", "c")
    library.sync_asset_pool("pool")
    assert library.store["c_f8"] == {"a", "b"}, "nothing written while off"

    builds = len(library.builds)
    resync = library.update_source("f8", enabled=True)

    assert resync == ["pool"]
    assert len(library.builds) == builds + 1, "its projection is rebuilt"
    assert state(library, "pool", "f8") == PREPARING
    library.sync_asset_pool("pool")
    assert state(library, "pool", "f8") == SERVING
    assert library.store["c_f8"] == {"a", "b", "c"}


def test_a_failed_rebuild_leaves_the_source_disabled():
    library = Library()
    _pool(library)
    library.update_source("f8", enabled=False)

    def broken(*args, **kwargs):
        raise RuntimeError("model missing")

    library.build_projection = broken
    with pytest.raises(RuntimeError):
        library.update_source("f8", enabled=True)
    assert library.sources["f8"].enabled is False
    assert "f8" in library.asset_pools["pool"].frozen_sources


def test_enabling_does_not_revive_a_deprecated_binding():
    library = Library()
    _pool(library)
    add_source(library, "f16")
    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    library.sync_asset_pool("pool")
    library.update_source("f8", enabled=False)

    assert library.update_source("f8", enabled=True) == []
    assert state(library, "pool", "f8") == DEGRADE
    assert serving_ids(library, "pool") == ["f16"]


@pytest.mark.parametrize("field", ["operator_options", "collection_name", "serving_state"])
def test_a_source_refuses_changes_to_what_it_embeds_with(field):
    library = Library()
    add_source(library, "f8")
    with pytest.raises(SourceRuleError, match="cannot"):
        library.update_source("f8", **{field: "x"})


@pytest.mark.parametrize("source_type", ["vector", "graph", "object"])
@pytest.mark.parametrize("path", [None, "", "/explicit/model", "relative/model"])
def test_source_creation_validates_model_options_before_registration(monkeypatch, source_type, path):
    library = Library()
    lookup = Mock(return_value=SimpleNamespace(database_type=source_type))
    monkeypatch.setattr(library._databasehub, "get_registration", lookup)

    with pytest.raises(ValueError, match="Invalid operator_options.embedding_model_path.*embedding_model"):
        library.create_source("source", "db", configuration={
            "embedding_model": "prepared-model", "embedding_model_path": path,
        })

    lookup.assert_not_called()
    assert not library.sources
    assert library.builds == []


def test_renaming_reaches_the_pools_copies():
    library = Library()
    _pool(library)
    library.update_source("f8", name="video-f8", labels={"modality": "video"})
    projection = library.asset_pools["pool"].projections[0]
    assert projection.source.name == "video-f8"
    assert library.to_record()["asset_pools"][0]["sources"][0]["labels"] == {"modality": "video"}


def test_a_disabled_source_attached_later_is_kept_but_not_built():
    library = Library()
    _pool(library)
    add_source(library, "off")
    library.update_source("off", enabled=False)
    builds = len(library.builds)

    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "off"}])

    assert "off" not in library.builds[builds:]
    assert "off" in library.asset_pools["pool"].frozen_sources
    assert state(library, "pool", "off") == PREPARING


def test_a_disabled_source_cannot_be_attached_as_a_replacement():
    library = Library()
    _pool(library)
    add_source(library, "f16")
    library.update_source("f16", enabled=False)
    with pytest.raises(SourceRuleError, match="disabled"):
        library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])


def test_deleting_an_asset_reaches_frozen_bindings():
    library = Library()
    ids = _pool(library)
    add_source(library, "f16")
    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    library.sync_asset_pool("pool")
    assert library.store["c_f8"] == {"a", "b"}

    library.delete_assets([ids[0]])

    assert library.store["c_f8"] == {"b"}, "or a rollback would bring it back"
    assert library.store["c_f16"] == {"b"}


def test_a_frozen_binding_records_changes_for_after_it_thaws():
    library = Library()
    ids = _pool(library)
    library.update_source("f8", enabled=False)
    library.note_assets_changed([ids[0]])
    assert library.asset_pools["pool"].source_statuses["f8"].stale_asset_ids == [ids[0]]


def test_a_restore_brings_bindings_back_without_loading_frozen_ones():
    library = Library()
    _pool(library)
    add_source(library, "f16")
    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    library.sync_asset_pool("pool")
    record = library.to_record()

    restored = Library.__new__(Library)
    restored.store, restored.builds, restored.fail_next = library.store, [], {}
    Library.__init__(restored, name=record["name"], store=library.store)
    restored.restore(record)

    assert restored.builds == ["f16"], "the deprecated f8 is not built"
    assert state(restored, "pool", "f8") == DEGRADE
    assert state(restored, "pool", "f16") == SERVING
    assert serving_ids(restored, "pool") == ["f16"]
    assert "f8" in restored.asset_pools["pool"].frozen_sources


def test_a_legacy_record_restores_every_binding_as_serving():
    library = Library()
    _pool(library)
    record = library.to_record()
    for status in record["asset_pools"][0]["source_statuses"].values():
        for key in ("serving_state", "replaces", "serving_history"):
            status.pop(key)
    for source in record["sources"]:
        for key in ("enabled", "labels", "created_at", "profile"):
            source.pop(key, None)

    restored = Library(store=library.store)
    restored.restore(record)

    assert state(restored, "pool", "f8") == SERVING
    assert restored.sources["f8"].enabled is True
    assert restored.sources["f8"].profile["profile_hash"], "filled in on restore"


def test_retrieved_records_name_the_source_that_produced_them():
    library = Library()
    _pool(library, sources=("f8", "text"))
    results = library.retrieve({"pool": object()})["pool"]
    assert {r.node.metadata["source_id"] for r in results} == {"f8", "text"}
    assert all(r.node.metadata["profile_hash"] for r in results)


def test_a_model_is_released_once_no_projection_holds_it():
    class Model:
        pass

    cache = ModelCache()
    model = cache.get_or_build("k", Model)
    assert cache.get_or_build("k", Model) is model, "shared while held"
    ref = weakref.ref(model)
    del model
    gc.collect()
    assert ref() is None and "k" not in cache


def test_a_model_that_cannot_be_weakly_held_is_cached_as_before():
    cache = ModelCache()
    value = cache.get_or_build("k", lambda: 7)
    assert cache.get_or_build("k", lambda: 8) == value == 7


@pytest.mark.parametrize("frozen", [False, True])
def test_delete_and_recreate_source_leaves_no_stale_pool_binding(frozen):
    library = Library()
    _pool(library, "A")
    _pool(library, "B")
    stored = {name: set(ids) for name, ids in library.store.items()}
    if frozen:
        library.update_source("f8", enabled=False)

    assert library.detach_source("f8")

    for pool in library.asset_pools.values():
        assert "f8" not in pool.source_statuses
        assert "f8" not in pool.frozen_sources and "f8" not in pool.unavailable_sources
        assert all(p.source.source_id != "f8" for p in (*pool.projections, *pool.serving))
    assert library.store == stored, "deleting a locator must not delete its external collection"

    source = library.create_source(name="f8", database_id="db", collection_name="new_f8")
    for pool in library.asset_pools.values():
        current = [{"source_id": st.source_id} for st in pool.source_statuses.values()]
        library.set_asset_pool_sources(pool.asset_pool_id, [*current, {"source_id": source.source_id}])
        library.sync_asset_pool(pool.asset_pool_id)
    restored = Library(store=library.store)
    restored.restore(library.to_record())
    assert all("f8" not in pool.source_statuses for pool in restored.asset_pools.values())
    assert all(source.source_id in pool.source_statuses for pool in restored.asset_pools.values())


def test_deleting_a_replacement_target_clears_its_pending_intent():
    library = Library()
    _pool(library)
    add_source(library, "f16")
    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])

    library.detach_source("f8")

    assert library.asset_pools["pool"].source_statuses["f16"].replaces is None
    library.sync_asset_pool("pool")
    assert serving_ids(library, "pool") == ["f16"]


def test_source_delete_recreate_attach_round_trip_through_the_api(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import asset_library as api_module

    library = Library()
    _pool(library)
    monkeypatch.setattr(api_module, "_require", lambda _: library)
    monkeypatch.setattr(api_module.registry, "save", lambda: None)
    app = FastAPI()
    app.include_router(api_module.router)
    with TestClient(app) as client:
        assert client.delete("/v1/libraries/library/sources/f8").status_code == 204
        created = client.post("/v1/libraries/library/sources", json={
            "name": "f8", "database_id": "db", "collection_name": "new_f8", "operator_options": {},
        })
        assert created.status_code == 201, created.text
        source_id = created.json()["id"]
        attached = client.put("/v1/libraries/library/asset_pools/pool/sources", json={"sources": [source_id]})
        assert attached.status_code == 200, attached.text
        assert [st["source_id"] for st in attached.json()["source_statuses"]] == [source_id]


def test_restore_does_not_resurrect_a_source_left_in_an_old_deleted_pool_record():
    library = Library()
    _pool(library)
    record = library.to_record()
    record["sources"] = []  # shape left by the former registry-only deletion

    restored = Library(store=library.store)
    restored.restore(record)

    assert not restored.sources
    assert not restored.asset_pools["pool"].source_statuses
    source = restored.create_source(name="replacement", database_id="db")
    restored.set_asset_pool_sources("pool", [{"source_id": source.source_id}])
    assert list(restored.asset_pools["pool"].source_statuses) == [source.source_id]
