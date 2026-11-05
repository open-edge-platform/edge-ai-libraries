# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Domain-neutral contracts for assets, projections, and sources."""

from dataclasses import dataclass, field
from typing import (
    Any,
    Collection,
    Generic,
    Mapping,
    Protocol,
    Sequence,
    Set,
    TypeVar,
    runtime_checkable,
)

AssetT = TypeVar("AssetT")
QueryT = TypeVar("QueryT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class Source:
    """The physical origin or location of an asset or projection."""

    source_id: str
    source_type: str
    location: Any
    name: str = ""
    database_id: str = ""
    configuration: Mapping[str, Any] = field(default_factory=dict)
    # Off switch, set by the operator: a disabled source is frozen in every
    # pool it is attached to (assetlib/sources/binding.py). The only mutable
    # fact about a source, beside its name and labels -- what it embeds with
    # is fixed at creation, and changing it means creating a new source.
    enabled: bool = True
    labels: Mapping[str, str] = field(default_factory=dict)
    created_at: str = ""
    # What this source embeds with, resolved once at creation so a later change
    # of engine defaults cannot silently change what its records mean
    # (assetlib/sources/profile.py).
    profile: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        location = self.location
        return {
            "source_id": self.source_id,
            "name": self.name,
            "source_type": self.source_type,
            "database_id": self.database_id,
            "collection": (
                dict(location.__dict__) if hasattr(location, "__dict__") else location
            ),
            "operator_options": dict(self.configuration),
            "enabled": self.enabled,
            "labels": dict(self.labels),
            "created_at": self.created_at,
            "profile": dict(self.profile),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "Source":
        from databasehub.models import (
            GraphCollection,
            ObjectCollection,
            SqlCollection,
            VectorCollection,
        )

        source_type = str(record["source_type"]).lower()
        collection_types = {
            "vector": VectorCollection,
            "sql": SqlCollection,
            "graph": GraphCollection,
            "object": ObjectCollection,
        }
        collection_type = collection_types.get(source_type)
        location = record["collection"]
        if collection_type is not None:
            location = collection_type(**dict(location))
        return cls(
            source_id=str(record["source_id"]),
            name=str(record["name"]),
            source_type=source_type,
            # Absent in a record written before connections were runtime state,
            # when this was an `adapter_id` naming a connection the engine
            # registered for itself. Left empty rather than raised on, so the
            # library still restores and reports the source as unreconciled
            # (`AssetLibrary._source_problem`) instead of vanishing.
            database_id=str(record.get("database_id") or ""),
            location=location,
            configuration=dict(record.get("operator_options") or {}),
            enabled=bool(record.get("enabled", True)),
            labels=dict(record.get("labels") or {}),
            created_at=str(record.get("created_at") or ""),
            profile=dict(record.get("profile") or {}),
        )


class Asset(Protocol):
    """Something a library holds, and where it was read from.

    `origin` is not a `Source` the library registers: an origin is where the
    asset came *from* (a file on disk, a request body), a source is where it is
    materialized *to*. They were the same registry once, told apart by whether
    `database_id` happened to be set, which made a filtering accident part of the
    contract.
    """

    asset_id: str
    origin: Source


class Projection(Protocol, Generic[AssetT, QueryT, ResultT]):
    """A materialized view of assets and the behavior used to query it.

    This is the whole surface an asset library may rely on. Anything a
    projection exposes beyond it -- a LlamaIndex index, a backend client, a
    vendor handle -- is private to that projection.
    """

    projection_id: str
    name: str
    source: Source
    # Which category of projection this is: "vector", "graph", ...
    kind: str

    @property
    def collection(self) -> Any:
        """Where this projection is materialized -- a collection locator."""

    def accepts(self, asset: AssetT) -> bool: ...

    def add(self, assets: Sequence[AssetT]) -> Any: ...

    def remove(self, asset_ids: Collection[str]) -> Any: ...

    def materialize(self, request: Any) -> Mapping[str, int]: ...

    def retrieve(self, query: QueryT) -> Sequence[ResultT]: ...


@runtime_checkable
class ChunkProjection(Protocol):
    """A projection whose materialized records can be enumerated and dropped.

    A vector projection can be listed and deleted from by metadata; a graph
    projection cannot. Callers that need either test for this protocol by name
    rather than probing for the individual methods, so the capability is part of
    the contract instead of an ad-hoc `hasattr`.

    `version` counts writes: it changes whenever the materialized set does, so a
    cache built over `load()` can tell that it is stale.

    There is no `clear`: nothing drops a whole collection, because detaching a
    source or deleting an asset library deliberately leaves the physical data
    alone. Add it back alongside the first caller that means to destroy data.
    """

    version: int

    def load(self) -> Sequence[Any]: ...

    def count(self) -> int:
        """How many records this projection holds, for reporting."""
        ...

    def delete_by_metadata(self, field: str, values: Sequence[str]) -> int: ...

    def indexed_asset_ids(self, asset_ids: Sequence[str]) -> Set[str]:
        """Which of `asset_ids` this projection already holds.

        Answers about a known set rather than enumerating the projection, so
        attaching a source to a pool that already has assets -- or syncing one
        -- costs a bounded query instead of reading every record. May return a
        subset if the backend cannot answer; a caller treats anything missing as
        not indexed yet.
        """
        ...