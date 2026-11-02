# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A library whose projections are in-memory fakes, so the rules run alone."""

from dataclasses import replace
from types import SimpleNamespace

from assetlib import Source
from core.content import ContentStream
from core.file_asset_library import FileAsset, FileAssetLibrary
from databasehub.models import VectorCollection
from llama_index.core.schema import Document


class FakeProjection:
    """A chunk projection backed by a shared per-collection set of asset ids."""

    kind = "vector"
    version = 0

    def __init__(self, source, store, fail_times=0):
        self.projection_id = f"p-{source.source_id}"
        self.name = "pool"
        self.source = source
        self._store = store
        self.adds = []
        self.fail_times = fail_times

    @property
    def held(self):
        return self._store.setdefault(self.source.location.name, set())

    @property
    def collection(self):
        return self.source.location

    def accepts(self, asset):
        return True

    def add(self, assets):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("backend unavailable")
        ids = [asset.asset_id for asset in assets]
        self.adds.append(ids)
        self.held.update(ids)
        return {"chunks_added": len(ids)}

    def remove(self, asset_ids):
        self.held.difference_update(asset_ids)
        return len(asset_ids)

    def materialize(self, request):
        return {}

    def retrieve(self, query):
        return [
            SimpleNamespace(node=SimpleNamespace(metadata={"asset_id": asset_id}))
            for asset_id in sorted(self.held)
        ]

    def load(self):
        return []

    def count(self):
        return len(self.held)

    def indexed_asset_ids(self, asset_ids):
        return self.held & set(asset_ids)

    def delete_by_metadata(self, field, values):
        self.held.difference_update(values)
        return 0


class FakeAdapter:
    def __init__(self, store):
        self._store = store
        self.deleted = []

    def delete_by_metadata(self, collection, field, values):
        self.deleted.append((collection.name, field, list(values)))
        held = self._store.setdefault(collection.name, set())
        removed = held & set(values)
        held.difference_update(values)
        return len(removed)


class FakeHub:
    def __init__(self, store):
        self.adapter = FakeAdapter(store)

    def get_registration(self, database_id):
        kind = "object" if database_id == "objects" else "vector"
        return SimpleNamespace(database_type=kind, database_id=database_id)

    def get_adapter(self, database_id):
        return self.adapter


class Library(FileAssetLibrary):
    """Builds fakes instead of indexers, and counts builds (model loads)."""

    BACKFILL_BATCH_SIZE = 2

    def __init__(self, name="library", store=None, **kwargs):
        self.store = {} if store is None else store
        self.builds = []
        self.fail_next = {}
        super().__init__(name=name, databasehub=FakeHub(self.store), **kwargs)

    def build_projection(self, projection_id, name, source):
        self.builds.append(source.source_id)
        return FakeProjection(
            source, self.store, fail_times=self.fail_next.pop(source.source_id, 0)
        )

    def describe_source(self, source):
        # The real resolution reads engine config; the rules only need a hash.
        from assetlib.sources.profile import build_profile

        return build_profile("text", "fake", "m", dict(source.configuration))


def add_source(library, source_id, collection=None, **configuration):
    source = Source(
        source_id=source_id,
        name=source_id,
        source_type="vector",
        database_id="db",
        location=VectorCollection(collection or f"c_{source_id}", 4),
        configuration=configuration,
    )
    source = replace(source, profile=library.describe_source(source))
    return library.add_source(source)


def asset(name):
    stream = ContentStream.from_document(Document(text=name, id_=name))
    return FileAsset(asset_id=stream.asset_id, origin=f"file:///{name}", cached=stream)


def ingest(library, pool_id, *names):
    assets = [asset(name) for name in names]
    library.register_assets(assets)
    library.add_assets_to_pool(pool_id, [item.asset_id for item in assets])
    return [item.asset_id for item in assets]


def state(library, pool_id, source_id):
    return library.asset_pools[pool_id].source_statuses[source_id].serving_state


def serving_ids(library, pool_id):
    return [p.source.source_id for p in library.asset_pools[pool_id].serving]


def retrieved_sources(library, pool_id):
    results = library.retrieve({pool_id: object()})[pool_id]
    return sorted({result.node.metadata["source_id"] for result in results})
