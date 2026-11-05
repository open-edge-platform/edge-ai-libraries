# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Attaching, replacing and rolling back sources in a pool, end to end."""

import pytest

from assetlib.sources.binding import DEGRADE, PREPARING, SERVING
from assetlib.sources.updates import SourceRuleError

from tests.test_sources.fakes import (
    Library,
    add_source,
    ingest,
    retrieved_sources,
    serving_ids,
    state,
)


def _serving_pool(library, pool_id="pool", source_id="f8", assets=("a", "b", "c")):
    if source_id not in library.sources:
        add_source(library, source_id)
    library.create_asset_pool(asset_pool_id=pool_id, name=pool_id, source_configurations=[{"source_id": source_id}])
    ingest(library, pool_id, *assets)
    library.sync_asset_pool(pool_id)
    assert state(library, pool_id, source_id) == SERVING
    return library


def test_a_source_attached_to_a_full_pool_does_not_serve_until_it_catches_up():
    library = _serving_pool(Library())
    add_source(library, "extra")

    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "extra"}])

    assert state(library, "pool", "extra") == PREPARING
    assert retrieved_sources(library, "pool") == ["f8"], "no half-filled results"
    library.sync_asset_pool("pool")
    assert state(library, "pool", "extra") == SERVING
    assert retrieved_sources(library, "pool") == ["extra", "f8"], "added, not replaced"


def test_a_replacement_takes_over_once_it_has_caught_up():
    library = _serving_pool(Library())
    add_source(library, "f16", frames_per_clip=16)

    library.set_asset_pool_sources(
        "pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}]
    )
    pool = library.asset_pools["pool"]
    assert state(library, "pool", "f16") == PREPARING
    assert retrieved_sources(library, "pool") == ["f8"], "the old source keeps serving"

    library.sync_asset_pool("pool")

    assert state(library, "pool", "f16") == SERVING
    assert state(library, "pool", "f8") == DEGRADE
    assert retrieved_sources(library, "pool") == ["f16"]
    assert "f8" in pool.frozen_sources, "kept, with its data"
    assert all(p.source.source_id != "f8" for p in pool.projections), "and no model"
    assert pool.source_statuses["f16"].replaces is None
    assert pool.source_statuses["f8"].serving_history[-1]["reason"] == "replaced_by:f16"


def test_a_replacement_is_scoped_to_the_pool_it_was_declared_in():
    library = _serving_pool(Library(), "A")
    _serving_pool(library, "B")
    add_source(library, "f16")

    library.set_asset_pool_sources("A", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    library.sync_asset_pool("A")

    assert serving_ids(library, "A") == ["f16"]
    assert serving_ids(library, "B") == ["f8"]
    assert state(library, "B", "f8") == SERVING


def test_a_replacement_into_an_empty_pool_happens_at_once():
    library = Library()
    add_source(library, "f8")
    add_source(library, "f16")
    library.create_asset_pool(asset_pool_id="pool", name="pool", source_configurations=[{"source_id": "f8"}])

    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])

    assert state(library, "pool", "f16") == SERVING
    assert state(library, "pool", "f8") == DEGRADE


def test_rolling_back_is_a_replacement_in_the_other_direction():
    library = _serving_pool(Library())
    add_source(library, "f16")
    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    library.sync_asset_pool("pool")
    ingest(library, "pool", "d")  # arrives while f8 is frozen
    library.sync_asset_pool("pool")

    library.set_asset_pool_sources("pool", [{"source_id": "f16"}, {"source_id": "f8", "replaces": "f16"}])
    assert state(library, "pool", "f8") == PREPARING, "it missed `d`, so it catches up first"
    library.sync_asset_pool("pool")

    assert state(library, "pool", "f8") == SERVING
    assert state(library, "pool", "f16") == DEGRADE
    assert len(library.store["c_f8"]) == 4


def test_a_failed_catch_up_keeps_the_old_source_serving():
    library = _serving_pool(Library())
    add_source(library, "f16")
    library.fail_next["f16"] = 1

    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    library.sync_asset_pool("pool")

    status = library.asset_pools["pool"].source_statuses["f16"]
    assert (status.status, status.serving_state) == ("failed", PREPARING)
    assert serving_ids(library, "pool") == ["f8"]
    library.sync_asset_pool("pool")
    assert serving_ids(library, "pool") == ["f16"]


def test_new_assets_do_not_take_a_serving_source_out_of_service():
    library = _serving_pool(Library())
    ingest(library, "pool", "d")
    assert library.asset_pools["pool"].source_statuses["f8"].status == "pending"
    assert state(library, "pool", "f8") == SERVING
    assert serving_ids(library, "pool") == ["f8"]


def test_a_preparing_source_is_written_in_batches():
    library = _serving_pool(Library(), assets=("a", "b", "c", "d", "e"))
    add_source(library, "f16")
    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    library.sync_asset_pool("pool")
    f16 = next(p for p in library.asset_pools["pool"].projections if p.source.source_id == "f16")
    assert [len(batch) for batch in f16.adds] == [2, 2, 1]


def test_an_ordinary_sync_is_one_write():
    library = _serving_pool(Library(), assets=())
    ingest(library, "pool", "a", "b", "c")
    library.sync_asset_pool("pool")
    f8 = library.asset_pools["pool"].projections[0]
    assert [len(batch) for batch in f8.adds] == [3]


@pytest.mark.parametrize(
    "entries, message",
    [
        ([{"source_id": "f16", "replaces": "f8"}], "must stay"),
        ([{"source_id": "f8"}, {"source_id": "f16", "replaces": "nope"}], "not found"),
        ([{"source_id": "f8", "replaces": "f8"}], "itself"),
        ([{"source_id": "f8"}, {"source_id": "f16", "replaces": "other"}], "not attached"),
    ],
)
def test_replacements_that_cannot_be_carried_out_are_refused(entries, message):
    library = _serving_pool(Library())
    add_source(library, "f16")
    add_source(library, "other")
    with pytest.raises(SourceRuleError, match=message):
        library.set_asset_pool_sources("pool", entries)
    assert serving_ids(library, "pool") == ["f8"], "nothing changed"


def test_one_source_cannot_be_replaced_twice_at_once():
    library = _serving_pool(Library())
    add_source(library, "f16")
    add_source(library, "f32")
    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    with pytest.raises(SourceRuleError, match="already being replaced"):
        library.set_asset_pool_sources(
            "pool",
            [{"source_id": "f8"}, {"source_id": "f16"}, {"source_id": "f32", "replaces": "f8"}],
        )


def test_a_deprecated_source_cannot_be_replaced_again():
    library = _serving_pool(Library())
    add_source(library, "f16")
    add_source(library, "f32")
    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    library.sync_asset_pool("pool")
    with pytest.raises(SourceRuleError, match="already deprecated"):
        library.set_asset_pool_sources(
            "pool",
            [{"source_id": "f8"}, {"source_id": "f16"}, {"source_id": "f32", "replaces": "f8"}],
        )


def test_a_replacement_named_by_source_name_resolves_to_its_id():
    library = _serving_pool(Library())
    add_source(library, "f16")
    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    assert library.asset_pools["pool"].source_statuses["f16"].replaces == "f8"


def test_detaching_the_replaced_source_drops_the_pending_replacement():
    library = _serving_pool(Library())
    add_source(library, "f16")
    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    library.set_asset_pool_sources("pool", [{"source_id": "f16"}])
    assert library.asset_pools["pool"].source_statuses["f16"].replaces is None


def test_the_serving_set_is_swapped_in_one_assignment():
    """A retrieval that took the tuple before the switch keeps a consistent set."""
    library = _serving_pool(Library())
    add_source(library, "f16")
    library.set_asset_pool_sources("pool", [{"source_id": "f8"}, {"source_id": "f16", "replaces": "f8"}])
    before = library.asset_pools["pool"].serving
    library.sync_asset_pool("pool")
    after = library.asset_pools["pool"].serving
    assert [p.source.source_id for p in before] == ["f8"]
    assert [p.source.source_id for p in after] == ["f16"]


def test_a_pool_sharing_a_filled_collection_counts_what_it_already_holds():
    library = _serving_pool(Library(), "A")
    library.create_asset_pool(asset_pool_id="B", name="B", source_configurations=[{"source_id": "f8"}])
    library.add_assets_to_pool("B", list(library.asset_pools["A"].asset_ids))
    library.sync_asset_pool("B")
    status = library.asset_pools["B"].source_statuses["f8"]
    assert sorted(status.indexed_asset_ids) == sorted(library.asset_pools["A"].asset_ids)
