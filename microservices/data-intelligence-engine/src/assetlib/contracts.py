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
    # A disabled source is frozen in every pool it is attached to.
    enabled: bool = True
    labels: Mapping[str, str] = field(default_factory=dict)
    created_at: str = ""
    # What this source embeds with, fixed at creation.
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

        from assetlib.sources.profile import upgrade_legacy_backends

        source_type = str(record["source_type"]).lower()
        profile, configuration = upgrade_legacy_backends(
            record.get("profile") or {}, record.get("operator_options") or {}
        )
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
            # May be absent; empty restores the source as unreconciled rather than failing.
            database_id=str(record.get("database_id") or ""),
            location=location,
            configuration=configuration,
            enabled=bool(record.get("enabled", True)),
            labels=dict(record.get("labels") or {}),
            created_at=str(record.get("created_at") or ""),
            profile=profile,
        )


class Asset(Protocol):
    """Something a library holds; `origin` is where it was read from, not a registered source."""

    asset_id: str
    origin: Source


class Projection(Protocol, Generic[AssetT, QueryT, ResultT]):
    """A materialized view of assets and the behavior used to query it."""

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
    """A projection whose records can be enumerated and dropped; `version` changes on every write."""

    version: int

    def load(self) -> Sequence[Any]: ...

    def count(self) -> int:
        """How many records this projection holds, for reporting."""
        ...

    def delete_by_metadata(self, field: str, values: Sequence[str]) -> int: ...

    def indexed_asset_ids(self, asset_ids: Sequence[str]) -> Set[str]:
        """Which of `asset_ids` this projection already holds; missing ones count as not indexed."""
        ...