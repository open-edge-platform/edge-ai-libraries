# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Database connections are runtime state, not deployment configuration.

They used to be read out of the environment at import time and registered under
four fixed ids. This suite pins the three things that changed and the one thing
that must not break because of them:

- a fresh hub is connected to nothing, and says so usefully;
- registering, repointing and removing a connection works and survives a
  restart, with credentials kept but not echoed;
- a library with no object database chosen picks the only one, refuses to guess
  between several, and always has somewhere to put content;
- **a library whose database is not registered still restores.** That is the
  dangerous one. Restore used to drop such a library, and the next save rewrote
  the workspace from the live set -- so an unreachable connection silently
  destroyed the assets and pools it was attached to. Since a fresh engine now
  starts with nothing registered, that path went from rare to guaranteed.
"""

import secrets
import tempfile
from types import SimpleNamespace

import pytest

from assetlib.contracts import Source
from core.content import TEXT, ContentBlock, ContentStream
from core.file_asset_library import FileAssetLibrary, file_origin
from databasehub.manager import (
    REDACTED,
    WORKSPACE_CONTENT_DATABASE,
    DatabaseHubManager,
)
from databasehub.models import VectorCollection
from . import dbhub

# Generated per run, so no credential literal sits in the source.
SECRET = secrets.token_hex(8)


class FakeProjection:
    kind = "vector"
    version = 0

    def __init__(self, source):
        self.projection_id = "p1"
        self.name = "pool"
        self.source = source
        self.added = []

    @property
    def collection(self):
        return self.source.location

    def accepts(self, asset):
        return True

    def materialize(self, request):
        return {}

    def retrieve(self, query):
        return []

    def remove(self, asset_ids):
        return 0

    def add(self, assets):
        self.added.extend(asset.asset_id for asset in assets)
        return {}


class StubLibrary(FileAssetLibrary):
    """Builds a projection only for a database that is actually registered."""

    def build_projection(self, projection_id, name, source):
        registration = self._databasehub.get_registration(source.database_id)
        if registration.database_type != source.source_type:
            raise TypeError(f"{source.database_id!r} is the wrong kind of database")
        return FakeProjection(source)


def _hub():
    return DatabaseHubManager()


# --- nothing at bootstrap ------------------------------------------------------


def test_a_fresh_hub_is_connected_to_nothing():
    """The whole point: no environment variable registers anything any more."""
    assert _hub().list_databases() == []


def test_asking_for_an_unregistered_database_says_what_is_registered():
    hub = _hub()

    with pytest.raises(ValueError) as caught:
        hub.require("prod-milvus")
    assert "none registered" in str(caught.value)

    hub.register("local", database_type="vector", backend="milvus", options={})
    with pytest.raises(ValueError) as caught:
        hub.require("prod-milvus")
    assert "local" in str(caught.value)


# --- registering ---------------------------------------------------------------


def test_registering_records_without_connecting():
    """An operator should be able to write down a connection before it is up."""
    hub = _hub()

    registration = hub.register(
        "prod",
        database_type="vector",
        backend="milvus",
        options={"uri": "http://nothing-is-listening:19530"},
    )

    assert registration.database_id == "prod"
    assert hub.list_databases() == [registration]


def test_a_duplicate_id_is_refused():
    hub = _hub()
    hub.register("prod", database_type="vector", backend="milvus", options={})

    with pytest.raises(ValueError) as caught:
        hub.register("prod", database_type="vector", backend="milvus", options={})
    assert "already exists" in str(caught.value)


def test_an_unknown_type_or_backend_is_refused_with_the_alternatives():
    hub = _hub()

    with pytest.raises(ValueError) as caught:
        hub.register("x", database_type="timeseries", backend="influx")
    assert "vector" in str(caught.value)

    with pytest.raises(ValueError) as caught:
        hub.register("x", database_type="vector", backend="pinecone")
    assert "milvus" in str(caught.value)


def test_databases_of_type_filters():
    hub = dbhub.with_vector(dbhub.object_hub())

    assert [item.database_id for item in hub.databases_of_type("object")] == [
        dbhub.OBJECT_DATABASE
    ]
    assert [item.database_id for item in hub.databases_of_type("graph")] == []


# --- updating and removing -----------------------------------------------------


def test_updating_repoints_and_drops_the_live_connection():
    hub = dbhub.object_hub()
    first = hub.get_adapter(dbhub.OBJECT_DATABASE)

    hub.update(dbhub.OBJECT_DATABASE, options={"root": tempfile.mkdtemp()})

    assert hub.get_adapter(dbhub.OBJECT_DATABASE) is not first, "reconnected"


def test_the_type_cannot_change_under_the_sources_that_use_it():
    hub = dbhub.object_hub()

    hub.update(dbhub.OBJECT_DATABASE, description="renamed")

    assert hub.require(dbhub.OBJECT_DATABASE).database_type == "object"


def test_a_secret_left_out_of_an_update_is_kept():
    """A client that GETs, edits one field and PATCHes back sends `***` for the
    password. Taking that literally would overwrite the real credential."""
    hub = _hub()
    hub.register(
        "store",
        database_type="graph",
        backend="nebula",
        options={"url": "nebula://nebula-graphd:9669", "password": SECRET},
    )

    hub.update("store", options={"url": "nebula://other-graphd:9669", "password": REDACTED})

    options = hub.require("store").options
    assert options["url"] == "nebula://other-graphd:9669"
    assert options["password"] == SECRET


def test_removing_forgets_and_closes():
    hub = dbhub.object_hub()

    assert hub.remove(dbhub.OBJECT_DATABASE) is True
    assert hub.list_databases() == []
    assert hub.remove(dbhub.OBJECT_DATABASE) is False


# --- secrets -------------------------------------------------------------------


def test_credentials_are_masked_on_the_way_out_and_kept_on_the_way_in():
    hub = _hub()
    hub.register(
        "store",
        database_type="graph",
        backend="nebula",
        options={"url": "nebula://nebula-graphd:9669", "password": SECRET},
    )

    registration = hub.require("store")

    assert registration.redacted()["options"]["password"] == REDACTED
    assert registration.redacted()["options"]["url"] == "nebula://nebula-graphd:9669"
    assert registration.to_record()["options"]["password"] == SECRET


def test_an_empty_secret_is_not_masked_into_looking_set():
    hub = _hub()
    empty = ""
    hub.register(
        "store",
        database_type="graph",
        backend="nebula",
        options={"url": "nebula://nebula-graphd:9669", "password": empty},
    )

    assert hub.require("store").redacted()["options"]["password"] == empty


# --- persistence ---------------------------------------------------------------


def test_a_round_trip_keeps_everything_including_the_secret():
    hub = _hub()
    hub.register(
        "store",
        database_type="graph",
        backend="nebula",
        options={"url": "nebula://nebula-graphd:9669", "password": SECRET},
        description="shared content",
    )

    restored = _hub()
    assert restored.restore(hub.to_records()) == ["store"]

    registration = restored.require("store")
    assert registration.options["password"] == SECRET
    assert registration.description == "shared content"


def test_one_unusable_record_does_not_cost_the_others():
    restored = _hub()

    names = restored.restore(
        [
            {"database_id": "good", "database_type": "vector", "backend": "milvus"},
            {"database_id": "bad", "database_type": "vector", "backend": "pinecone"},
        ]
    )

    assert names == ["good"]


# --- choosing where content goes -----------------------------------------------


def test_with_no_object_database_the_workspace_store_is_registered():
    """An ingest cannot fail for want of somewhere to put content.

    This used to raise "register an object database". The engine owns a
    directory either way, so refusing was a rule with nothing behind it.
    """
    hub = _hub()
    library = StubLibrary(name="library", databasehub=hub)

    source = library.content_source()

    assert source.database_id == WORKSPACE_CONTENT_DATABASE
    assert hub.get(WORKSPACE_CONTENT_DATABASE) is not None, "and it is registered"
    assert library.content_database == WORKSPACE_CONTENT_DATABASE


def test_nothing_is_registered_until_something_needs_it():
    """The exception to "a fresh engine is connected to nothing" is narrow."""
    hub = _hub()
    StubLibrary(name="library", databasehub=hub)

    assert hub.list_databases() == []


def test_the_workspace_store_is_registered_once_and_persisted():
    hub = _hub()
    saves = []
    hub.persist = lambda: saves.append(True)

    first = StubLibrary(name="a", databasehub=hub).content_source()
    second = StubLibrary(name="b", databasehub=hub).content_source()

    assert first.database_id == second.database_id == WORKSPACE_CONTENT_DATABASE
    assert len(saves) == 1, "registered once, and written down when it was"
    # One database, but a bucket each: removing a library's content stays one
    # sweep and two libraries never share a key space.
    assert first.location.bucket != second.location.bucket


def test_with_exactly_one_it_is_adopted():
    """Adopted as a source, which is what records the choice -- so a second
    object store registered later cannot silently move where new content goes
    while the content already written stays put."""
    library = StubLibrary(name="library", databasehub=dbhub.object_hub())

    source = library.content_source()

    assert source.database_id == dbhub.OBJECT_DATABASE
    assert library.default_content_source_id == source.source_id
    assert library.content_database == dbhub.OBJECT_DATABASE


def test_with_several_it_does_not_guess_between_them():
    """"One is registered so it must be the one you meant" is a fair inference.
    "You have three, pick one" is not, so content goes to the store the engine
    owns until the library is told otherwise."""
    hub = dbhub.object_hub()
    hub.register(
        "second", database_type="object", backend="filesystem",
        options={"root": tempfile.mkdtemp()},
    )
    library = StubLibrary(name="library", databasehub=hub)

    assert library.content_source().database_id == WORKSPACE_CONTENT_DATABASE

    library.update(content_database="second")
    assert library.content_source().database_id == "second"
    assert library.content_database == "second"


def test_naming_a_database_that_is_not_registered_fails_at_the_library():
    library = StubLibrary(name="library", databasehub=dbhub.object_hub())

    with pytest.raises(ValueError):
        library.update(content_database="nope")


def test_naming_one_at_creation_registers_the_source_there():
    hub = dbhub.object_hub()
    hub.register(
        "second", database_type="object", backend="filesystem",
        options={"root": tempfile.mkdtemp()},
    )

    library = StubLibrary(name="library", databasehub=hub, content_database="second")

    assert library.content_database == "second"
    assert [source.database_id for source in library.sources.values()] == ["second"]


def test_the_choice_survives_a_record_round_trip():
    hub = dbhub.object_hub()
    library = StubLibrary(name="library", databasehub=hub)
    source = library.content_source()

    restored = StubLibrary.from_record(library.to_record(), databasehub=hub)

    assert restored.default_content_source_id == source.source_id
    assert restored.content_database == dbhub.OBJECT_DATABASE


def test_a_legacy_content_database_becomes_a_content_source():
    """Workspaces written before the default was a pointer recorded a field."""
    hub = dbhub.object_hub()
    record = {
        "idx": "lib-1",
        "name": "library",
        "content_database": dbhub.OBJECT_DATABASE,
        "sources": [],
        "assets": [],
        "asset_pools": [],
    }

    restored = StubLibrary.from_record(record, databasehub=hub)

    source = restored.content_source()
    assert source.database_id == dbhub.OBJECT_DATABASE
    assert source.location.bucket == "lib-1"
    assert restored.default_content_source_id == source.source_id


def test_a_legacy_record_whose_content_database_is_gone_still_restores():
    """The hazard below, for content: an unregistered database must not cost
    the library its assets and pools."""
    record = {
        "idx": "lib-1",
        "name": "library",
        "content_database": "removed",
        "sources": [],
        "assets": [],
        "asset_pools": [],
    }

    restored = StubLibrary.from_record(record, databasehub=_hub())

    assert restored.name == "library"
    assert len(restored.source_reconciliation_errors) == 1
    # Still the default: clearing it would let the next ingest adopt a
    # different store and quietly move where content goes.
    assert restored.default_content_source_id in restored.sources


# --- the hazard: an unregistered database must not destroy a library -----------


def _library_with_everything():
    """A library with a source, a pool and an asset, as an ingest would leave it."""
    hub = dbhub.with_vector(dbhub.object_hub())
    library = StubLibrary(name="library", databasehub=hub)
    source = library.create_source(
        name="primary",
        database_id=dbhub.VECTOR_DATABASE,
        collection_name="docs",
    )
    library.create_asset_pool(
        asset_pool_id="pool",
        name="pool",
        source_configurations=[{"source_id": source.source_id}],
    )
    asset = library.create_asset(
        origin=file_origin("/w/a.pdf"),
        stream=ContentStream(
            asset_id="a1",
            blocks=[ContentBlock(block_id="a1:0", kind=TEXT, text="hello")],
        ),
    )
    library.register_assets([asset])
    library.add_assets_to_pool("pool", ["a1"])
    return library, source


def test_a_library_restores_even_though_its_database_is_gone():
    record, _ = (lambda pair: (pair[0].to_record(), pair[1]))(_library_with_everything())

    # A restart with nothing registered -- the ordinary state of a fresh engine.
    restored = StubLibrary.from_record(record, databasehub=_hub())

    assert restored.name == "library"
    assert restored.asset_count == 1, "the assets survived"
    assert "pool" in restored.asset_pools, "the pool survived"


def test_the_source_is_reported_unreconciled_with_the_reason():
    record, source = (
        lambda pair: (pair[0].to_record(), pair[1])
    )(_library_with_everything())

    restored = StubLibrary.from_record(record, databasehub=_hub())

    problem = restored.source_reconciliation_errors[source.source_id]
    assert "not registered" in problem


def test_the_pool_keeps_the_source_and_reports_it_failed():
    record, source = (
        lambda pair: (pair[0].to_record(), pair[1])
    )(_library_with_everything())

    restored = StubLibrary.from_record(record, databasehub=_hub())
    pool = restored.asset_pools["pool"]

    assert pool.projections == (), "nothing to project through"
    assert source.source_id in pool.unavailable_sources
    assert pool.source_statuses[source.source_id].status == "failed"


def test_saving_after_such_a_restore_does_not_erase_the_source():
    """The actual data loss: the pool is persisted from what it holds, so a
    source dropped at restore is gone from the workspace on the next save."""
    record, source = (
        lambda pair: (pair[0].to_record(), pair[1])
    )(_library_with_everything())

    restored = StubLibrary.from_record(record, databasehub=_hub())
    again = restored.to_record()

    # The library also holds its content source, so check membership.
    assert source.source_id in {item["source_id"] for item in again["sources"]}
    pool_record = again["asset_pools"][0]
    assert [item["source_id"] for item in pool_record["sources"]] == [source.source_id]
    assert pool_record["asset_ids"] == ["a1"]


def test_registering_the_database_again_brings_the_pool_back():
    record, source = (
        lambda pair: (pair[0].to_record(), pair[1])
    )(_library_with_everything())

    hub = dbhub.with_vector(dbhub.object_hub())
    restored = StubLibrary.from_record(record, databasehub=hub)

    assert restored.asset_pools["pool"].projections != ()
    assert restored.source_reconciliation_errors == {}


def test_a_source_written_before_the_rename_reports_the_field_it_lacks():
    """`adapter_id` records do not raise -- they reconcile as an error saying so."""
    library = StubLibrary(name="library", databasehub=_hub())

    library.reconcile_sources(
        [
            Source.from_record(
                {
                    "source_id": "s1",
                    "name": "primary",
                    "source_type": "vector",
                    "adapter_id": "default-vector",
                    "collection": {"name": "docs", "dimension": 8},
                }
            )
        ]
    )

    assert "s1" in library.sources, "kept, so a save does not erase it"
    assert "database_id" in library.source_reconciliation_errors["s1"]


def test_a_source_pointed_at_the_wrong_kind_of_database_is_reported():
    hub = dbhub.object_hub()
    library = StubLibrary(name="library", databasehub=hub)

    library.reconcile_sources(
        [
            Source(
                source_id="s1",
                name="primary",
                source_type="vector",
                database_id=dbhub.OBJECT_DATABASE,
                location=VectorCollection("docs", 8),
            )
        ]
    )

    problem = library.source_reconciliation_errors["s1"]
    assert "'object'" in problem and "'vector'" in problem
