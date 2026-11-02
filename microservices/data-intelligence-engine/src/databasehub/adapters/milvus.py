# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Milvus vector adapter with connection ownership."""

import asyncio
import json
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

import config
from databasehub.adapters.vector import VectorAdapter
from databasehub.models import VectorCollection
from llama_index.core.schema import BaseNode
from llama_index.core.vector_stores.utils import metadata_dict_to_node
from llama_index.vector_stores.milvus import MilvusVectorStore
from pymilvus import MilvusClient


def _ensure_event_loop() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


class MilvusAdapter(VectorAdapter):
    """Own Milvus connection information and operate all reachable collections."""

    # `client.query` has no cursor here; see load_nodes.
    QUERY_LIMIT = config.MILVUS_QUERY_LIMIT

    def __init__(self, options: Mapping[str, object]):
        self._options = dict(options)
        self._uri = str(self._options["uri"])
        connection_options = {
            key: value for key, value in self._options.items() if key != "uri"
        }
        self._milvus_client = MilvusClient(
            uri=self._uri,
            **connection_options,
        )
        self._stores: Dict[Tuple[str, int], MilvusVectorStore] = {}

    def reconcile(self, collection: VectorCollection) -> None:
        if not self._milvus_client.has_collection(collection.name):
            self.vector_store(collection)
        if not self._milvus_client.has_collection(collection.name):
            raise ValueError(f"Milvus collection {collection.name!r} does not exist")

    def vector_store(self, collection: VectorCollection) -> MilvusVectorStore:
        key = (collection.name, collection.dimension)
        if key not in self._stores:
            _ensure_event_loop()
            store = MilvusVectorStore(
                uri=self._uri,
                dim=collection.dimension,
                collection_name=collection.name,
                overwrite=False,
                **{
                    option: value
                    for option, value in self._options.items()
                    if option != "uri"
                },
            )
            redundant_client = store.client
            if redundant_client is not self._milvus_client:
                redundant_client.close()
                store._milvusclient = self._milvus_client
            self._stores[key] = store
        return self._stores[key]

    def flush(self, collection: VectorCollection) -> None:
        """Seal what was just written, so a following query sees it.

        A failed flush costs read-visibility, not the write that preceded it --
        the rows are already in Milvus either way.
        """
        try:
            self._client(collection).flush(collection.name)
        except Exception:
            pass

    def existing_concept_store(
        self, collection: VectorCollection, concept_ids: Set[str], exact: bool = True,
    ):
        """Read-only recovery for unchanged concepts and embedding configuration.

        Check before constructing a store: its constructor can create a missing
        collection. Do not use best-effort helpers that swallow query errors.

        `exact` requires the collection to hold `concept_ids` and nothing else.
        Without it, other concepts may be there too -- a vector source attached
        to several pools holds every pool's concepts in one collection -- as long
        as each of `concept_ids` is, once, keyed by its own id.
        """
        client = self._milvus_client
        if not concept_ids or not client.has_collection(collection.name):
            return None
        schema = client.describe_collection(collection.name)
        dimension = next(
            (field.get("params", {}).get("dim") for field in schema["fields"]
             if field["name"] == "embedding"), None
        )
        if dimension is None or int(dimension) != collection.dimension:
            return None
        client.load_collection(collection.name)
        iterator = client.query_iterator(
            collection_name=collection.name, filter="", output_fields=["id", "cid"],
            batch_size=config.MILVUS_QUERY_BATCH_SIZE, consistency_level="Strong",
        )
        found = set()
        try:
            while True:
                rows = iterator.next()
                if not rows:
                    break
                for row in rows:
                    cid = row.get("cid")
                    if cid not in concept_ids:
                        if exact:
                            return None
                        continue
                    if row.get("id") != cid or cid in found:
                        return None
                    found.add(cid)
        finally:
            iterator.close()
        if found != concept_ids:
            return None
        return self.vector_store(collection)

    def _client(self, collection: VectorCollection) -> MilvusClient:
        """The shared client, with `collection`'s store built first.

        Constructing the store is what connects and loads the collection, so the
        direct client calls below have to go through here rather than reach for
        `self._milvus_client` themselves.
        """
        self.vector_store(collection)
        return self._milvus_client

    def delete_by_metadata(
        self, collection: VectorCollection, field: str, values: Sequence[str]
    ) -> int:
        if not values:
            return 0
        client = self._client(collection)
        quoted = ", ".join(json.dumps(value) for value in values)
        expression = f"{field} in [{quoted}]"
        try:
            matches = client.query(
                collection_name=collection.name,
                filter=expression,
                output_fields=["id"],
                limit=self.QUERY_LIMIT,
                consistency_level="Strong",
            )
            client.delete(collection_name=collection.name, filter=expression)
            client.flush(collection.name)
        except Exception:
            return 0
        return len(matches)

    def present_metadata_values(
        self, collection: VectorCollection, field: str, values: Sequence[str]
    ) -> Set[str]:
        """Ask in batches, splitting any batch whose answer was truncated.

        Milvus `query` has no DISTINCT, so a batch asking about N ids can match
        far more than N rows -- one per chunk. When a batch comes back at the
        row limit its answer may be partial, so it is halved and re-asked. That
        keeps the result exact while staying at one or two round trips in the
        normal case, instead of one per id.
        """
        found: Set[str] = set()
        remaining = [list(dict.fromkeys(values))]
        while remaining:
            batch = remaining.pop()
            if not batch:
                continue
            rows = self._query_metadata(collection, field, batch)
            if rows is None:
                continue  # unreachable backend: report a subset, per the contract
            if len(rows) >= self.QUERY_LIMIT and len(batch) > 1:
                middle = len(batch) // 2
                remaining.append(batch[:middle])
                remaining.append(batch[middle:])
                continue
            found.update(
                str(row[field]) for row in rows if row.get(field) is not None
            )
        return found

    def _query_metadata(
        self, collection: VectorCollection, field: str, values: Sequence[str]
    ) -> Optional[List[dict]]:
        """Rows matching `field in values`, or None if the query failed."""
        quoted = ", ".join(json.dumps(value) for value in values)
        try:
            return self._client(collection).query(
                collection_name=collection.name,
                filter=f"{field} in [{quoted}]",
                output_fields=[field],
                limit=self.QUERY_LIMIT,
            )
        except Exception:
            return None

    def count_records(self, collection: VectorCollection) -> int:
        try:
            stats = self._client(collection).get_collection_stats(collection.name)
        except Exception:
            return 0
        try:
            return int(stats.get("row_count", 0))
        except (TypeError, ValueError):
            return 0

    def load_nodes(self, collection: VectorCollection) -> List[BaseNode]:
        client = self._client(collection)
        try:
            # Strong: callers cache this list (VectorIndexer.load) and check OKF
            # provenance against it right after an ingest; a bounded-staleness
            # read can miss the rows just written and that miss would be kept.
            rows = client.query(
                collection_name=collection.name,
                filter="",
                output_fields=["*"],
                limit=self.QUERY_LIMIT,
                consistency_level="Strong",
            )
        except Exception:
            return []

        nodes: List[BaseNode] = []
        for row in rows:
            try:
                nodes.append(metadata_dict_to_node(row, text=row.get("text", "")))
            except Exception:
                continue
        return nodes

    def ping(self) -> None:
        """List the collections -- the cheapest thing that proves a round trip.

        `MilvusClient` is constructed eagerly, but constructing it does not
        always reach the server, so answering "is this Milvus there" needs an
        actual call.
        """
        self._milvus_client.list_collections()

    def close(self) -> None:
        for store in self._stores.values():
            async_client = getattr(store, "_async_milvusclient", None)
            close = getattr(async_client, "close", None)
            if close is not None:
                close_result = close()
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(close_result)
                else:
                    loop.create_task(close_result)
        self._stores.clear()
        self._milvus_client.close()
