# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import gc
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, replace
from types import MappingProxyType
from typing import (
    Any,
    Collection,
    Dict,
    Generic,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
)

from assetlib.content import ContentStore
from assetlib.contracts import ChunkProjection, Projection, Source
from assetlib.pool import AssetPool, SourceSyncStatus
from assetlib.sources import (
    backfill,
    binding,
    exposure,
    state_machine,
    updates,
)
from assetlib.sources import profile as source_profile
from databasehub.models import (
    GraphCollection,
    ObjectCollection,
    SqlCollection,
    VectorCollection,
)

AssetT = TypeVar("AssetT")

_COLLECTION_TYPES = {
    "vector": VectorCollection,
    "graph": GraphCollection,
    "sql": SqlCollection,
    "object": ObjectCollection,
}


def collection_name(location: Any) -> str:
    """The bare name out of a collection locator, whichever kind it is."""
    for attribute in ("name", "space", "table", "bucket"):
        value = getattr(location, attribute, None)
        if value is not None:
            return value
    raise TypeError(f"Unsupported source location: {type(location).__name__}")


def merge_counts(results: Iterable[Mapping[str, int]]) -> Dict[str, int]:
    """Sum the per-projection tallies a pool-wide operation produces."""
    merged: Dict[str, int] = {}
    for result in results:
        for key, value in result.items():
            merged[key] = merged.get(key, 0) + value
    return merged


class AssetLibrary(ABC, Generic[AssetT]):
    """A set of assets, the sources they go into, and the pools that pair them."""

    #: Assets per write while a binding is preparing.
    BACKFILL_BATCH_SIZE = 32

    def __init__(
        self,
        name: str,
        description: Optional[str] = None,
        idx: Optional[str] = None,
        databasehub=None,
        content_database: str = "",
    ):
        if not name:
            raise ValueError("An asset library needs a name")
        self.library_id = idx or str(uuid.uuid4())
        self.name = name
        self.description = description
        # Source new content goes to; empty until chosen or set on first ingest.
        self.default_content_source_id = ""
        if databasehub is None:
            from databasehub.manager import database_manager

            databasehub = database_manager
        self._databasehub = databasehub
        self._asset_pools: Dict[str, AssetPool] = {}
        self._assets: Dict[str, AssetT] = {}
        self._sources: Dict[str, Source] = {}
        self._content_store: Optional[ContentStore] = None
        self.source_reconciliation_errors: Dict[str, str] = {}
        # Per-pool sync locks; `_sync_locks_guard` only protects the dict.
        self._sync_locks: Dict[str, threading.RLock] = {}
        self._sync_locks_guard = threading.Lock()
        if content_database:
            self.adopt_content_database(content_database)

    @abstractmethod
    def build_projection(
        self, projection_id: str, name: str, source: Source
    ) -> Projection:
        """The projection a source of this kind is materialized through."""

    def describe_source(self, source: Source) -> dict:
        """Embedding profile of a vector/graph source; empty for other kinds."""
        if source.source_type.lower() not in ("vector", "graph"):
            return {}
        configuration = dict(source.configuration)
        return source_profile.build_profile(
            encoder_kind=None,
            backend=configuration.pop("embedding_backend", None),
            model=configuration.pop("embedding_model", None),
            params=configuration,
        )

    @abstractmethod
    def asset_to_record(self, asset: AssetT) -> dict:
        """One asset, as persisted."""

    @abstractmethod
    def asset_from_record(self, record: Mapping[str, Any]) -> AssetT:
        """One asset, restored."""

    @property
    def idx(self) -> str:
        """Alias for `library_id`."""
        return self.library_id

    def matches(self, key: str) -> bool:
        return bool(key) and key in (self.name, self.idx)

    def update(
        self,
        description: Optional[str] = None,
        content_database: Optional[str] = None,
        default_content_source_id: Optional[str] = None,
    ) -> None:
        """Change the description, or where new content goes (existing content stays put)."""
        if description is not None:
            self.description = description
        if default_content_source_id:
            self.adopt_content_source(default_content_source_id)
        if content_database:
            self.adopt_content_database(content_database)

    @property
    def sources(self) -> Mapping[str, Source]:
        """Where assets can be materialized."""
        return MappingProxyType(self._sources)

    def add_source(self, source: Source) -> Source:
        if source.source_id in self._sources:
            raise ValueError(f"Source {source.source_id!r} already exists")
        self._register_source(source)
        self.source_reconciliation_errors.pop(source.source_id, None)
        return source

    def create_source(
        self,
        name: str,
        database_id: str,
        collection_name: str = "",
        configuration: Optional[Mapping[str, Any]] = None,
        register: bool = True,
        enabled: bool = True,
        labels: Optional[Mapping[str, str]] = None,
    ) -> Source:
        """Register a source; its model and parameters are fixed from here on."""
        if not name:
            raise ValueError("A source needs a name")
        if "embedding_model_path" in (configuration or {}):
            raise ValueError(
                "Invalid operator_options.embedding_model_path; "
                "select a prepared model with embedding_model under ENGINE_MODEL_ROOT_PATH"
            )
        collection_name = collection_name or source_profile.default_collection_name(
            self.name, name
        )
        registration = self._databasehub.get_registration(database_id)
        source_type = registration.database_type
        collection_type = _COLLECTION_TYPES.get(source_type)
        if collection_type is None:
            raise ValueError(f"Unsupported source type: {source_type!r}")
        source = Source(
            source_id=str(uuid.uuid4()),
            name=name,
            source_type=source_type,
            database_id=database_id,
            location=collection_type(collection_name),
            configuration=dict(configuration or {}),
            enabled=enabled,
            labels=dict(labels or {}),
            created_at=source_profile.now(),
        )
        source = replace(source, profile=self.describe_source(source))
        return self.add_source(source) if register else source

    def update_source(self, source_id: str, **fields: Any) -> List[str]:
        """Rename, relabel, or switch a source on or off; returns pools needing a sync."""
        changes = updates.check_patch(fields)
        source = self.source_for(source_id)
        if "enabled" in changes and source.source_type == "object":
            raise updates.SourceRuleError(
                "A content source cannot be disabled: assets read their bytes "
                "through it"
            )
        if "labels" in changes:
            changes["labels"] = dict(changes["labels"] or {})
        updated = replace(source, **changes)
        switched_on = updated.enabled and not source.enabled
        switched_off = source.enabled and not updated.enabled
        thawing = {}
        if switched_on:
            for asset_pool in self._asset_pools.values():
                status = asset_pool.source_statuses.get(source_id)
                if status is None or status.serving_state == binding.DEGRADE:
                    continue
                thawing[asset_pool.asset_pool_id] = self.build_projection(
                    str(uuid.uuid4()), asset_pool.name, updated
                )
        self._sources[source_id] = updated
        resync: List[str] = []
        for asset_pool in self._asset_pools.values():
            if source_id not in asset_pool.source_statuses:
                continue
            self._carry_source_fields(asset_pool, updated)
            if switched_off:
                asset_pool.freeze(source_id, updated)
            elif asset_pool.asset_pool_id in thawing:
                asset_pool.thaw(thawing[asset_pool.asset_pool_id])
                self._apply_transitions(
                    asset_pool,
                    state_machine.on_enabled(
                        state_machine.views(asset_pool, self._sources), source_id
                    ),
                )
                resync.append(asset_pool.asset_pool_id)
        if switched_off:
            gc.collect()
        return resync

    @staticmethod
    def _carry_source_fields(asset_pool: AssetPool, updated: Source) -> None:
        for projection in asset_pool.projections:
            if projection.source.source_id == updated.source_id:
                projection.source = replace(
                    projection.source,
                    name=updated.name,
                    labels=updated.labels,
                    enabled=updated.enabled,
                )
        if updated.source_id in asset_pool.frozen_sources:
            asset_pool.frozen_sources[updated.source_id] = updated

    def source_bindings(self, source_id: str) -> List[Tuple[str, SourceSyncStatus, str]]:
        """`(pool id, status, effective state)` for every pool this source is in."""
        source = self._sources.get(source_id)
        return [
            (
                asset_pool.asset_pool_id,
                status,
                binding.effective_state(source, status),
            )
            for asset_pool in self._asset_pools.values()
            for status in [asset_pool.source_statuses.get(source_id)]
            if status is not None
        ]

    def set_source_serving_state(
        self, asset_pool_id: str, source_id: str, serving_state: str
    ) -> List[str]:
        """Deprecate or resume one pool binding."""
        pool = self._require_asset_pool(asset_pool_id)
        source = self.source_for(source_id)
        status = pool.source_statuses.get(source_id)
        if status is None:
            raise updates.SourceRuleError("The source is not attached to this pool")
        if source.source_type == "object" or source_id == self.default_content_source_id:
            raise updates.SourceRuleError("A content source has no editable serving state")
        if serving_state not in (binding.SERVING, binding.DEGRADE):
            raise updates.SourceRuleError("Choose SERVING or DEGRADE")
        if serving_state == status.serving_state:
            return []
        if any(
            binding.pending_replacement(item)
            and (sid == source_id or item.replaces == source_id)
            for sid, item in pool.source_statuses.items()
        ):
            raise updates.SourceRuleError(
                "This binding has a pending replacement; finish or cancel it with the CLI first"
            )
        if serving_state == binding.DEGRADE:
            self._apply_transitions(pool, [state_machine.Transition(
                source_id, binding.DEGRADE, "manually deprecated"
            )])
            pool.unavailable_sources.pop(source_id, None)
            return []
        if not source.enabled:
            raise updates.SourceRuleError("Enable the source before resuming this binding")
        projection = next(
            (p for p in pool.projections if p.source.source_id == source_id), None
        )
        if projection is None:
            # Build before mutating state so a failed load leaves it untouched.
            projection = self.build_projection(str(uuid.uuid4()), pool.name, source)
        state = (
            binding.SERVING if binding.is_caught_up(status, pool.revision)
            else binding.PREPARING
        )
        self._apply_transitions(pool, [state_machine.Transition(
            source_id, state, "manually resumed"
        )])
        if state == binding.PREPARING:
            status.mark_pending()
        pool.unavailable_sources.pop(source_id, None)
        pool.thaw(projection)
        return [asset_pool_id] if state == binding.PREPARING else []

    def _apply_transitions(self, asset_pool: AssetPool, transitions) -> List[str]:
        frozen = state_machine.apply(asset_pool, transitions, self._sources)
        if frozen:
            # Release the frozen projections' models from memory now.
            gc.collect()
        return frozen

    def remove_source(self, source_id: str) -> bool:
        source = self._sources.pop(source_id, None)
        self.source_reconciliation_errors.pop(source_id, None)
        if source_id == self.default_content_source_id:
            self.default_content_source_id = ""
        return source is not None

    def detach_source(self, source_id: str) -> bool:
        """Remove a source from the library unless assets keep their content in it."""
        holders = self.assets_in_source(source_id)
        if holders:
            raise ValueError(
                f"Source {source_id!r} holds the content of "
                f"{len(holders)} asset(s) and cannot be detached: delete them "
                "first, or leave the source attached so they stay readable"
            )
        removed = self.remove_source(source_id)
        if not removed:
            return False
        for pool in self._asset_pools.values():
            pool.projections = tuple(p for p in pool.projections if p.source.source_id != source_id)
            pool.source_statuses.pop(source_id, None)
            pool.frozen_sources.pop(source_id, None)
            pool.unavailable_sources.pop(source_id, None)
            updates.drop_stale_replaces(pool, tuple(pool.source_statuses))
            pool.refresh_serving()
        gc.collect()
        return True

    def assets_in_source(self, source_id: str) -> List[str]:
        """Which assets keep their content in this source."""
        return [
            asset_id
            for asset_id, asset in self._assets.items()
            if getattr(asset, "content_source_id", "") == source_id
        ]

    CONTENT_SOURCE_NAME = "content"

    @property
    def content_store(self) -> ContentStore:
        if self._content_store is None:
            self._content_store = ContentStore(self._databasehub)
        return self._content_store

    @property
    def content_database(self) -> str:
        """Which object database the default content source writes to, if any."""
        source = self._sources.get(self.default_content_source_id)
        return source.database_id if source is not None else ""

    def content_source(self, source_id: Optional[str] = None) -> Source:
        """Where to put content: a named source, the default, or a default adopted now."""
        if source_id:
            source = self.source_for(source_id)
            if source.source_type.lower() != "object":
                raise ValueError(
                    f"Source {source_id!r} is a {source.source_type!r} source; "
                    "asset content needs an 'object' source"
                )
            return source
        existing = self._sources.get(self.default_content_source_id)
        if existing is not None:
            return existing
        return self.adopt_content_database(self.resolve_content_database())

    def adopt_content_database(self, database_id: str) -> Source:
        """Register a content source in `database_id` and make it the default."""
        self._databasehub.get_registration(database_id)
        existing = next(
            (
                source
                for source in self._sources.values()
                if source.source_type == "object"
                and source.database_id == database_id
                and collection_name(source.location) == self.library_id
            ),
            None,
        )
        source = existing or self.create_source(
            name=self._content_source_name(),
            database_id=database_id,
            # One container per library.
            collection_name=self.library_id,
        )
        self.default_content_source_id = source.source_id
        return source

    def adopt_content_source(self, source_id: str) -> Source:
        """Make an already registered object source the default for new content."""
        source = self.content_source(source_id)
        self.default_content_source_id = source.source_id
        return source

    def _content_source_name(self) -> str:
        """`content`, or `content-2`, `content-3`... once that name is taken."""
        taken = {source.name for source in self._sources.values()}
        if self.CONTENT_SOURCE_NAME not in taken:
            return self.CONTENT_SOURCE_NAME
        suffix = 2
        while f"{self.CONTENT_SOURCE_NAME}-{suffix}" in taken:
            suffix += 1
        return f"{self.CONTENT_SOURCE_NAME}-{suffix}"

    def resolve_content_database(self) -> str:
        """The sole registered object database, else the workspace content store."""
        candidates = self._databasehub.databases_of_type("object")
        if len(candidates) == 1:
            return candidates[0].database_id
        return self._databasehub.ensure_content_database()

    def source_for(self, source_id: str) -> Source:
        source = self._sources.get(source_id)
        if source is None:
            raise ValueError(f"Source {source_id!r} not found")
        return source

    def _register_source(self, source: Source) -> None:
        existing = self._sources.get(source.source_id)
        if existing is not None and existing != source:
            raise ValueError(
                f"Source {source.source_id!r} is already registered differently"
            )
        self._sources[source.source_id] = source

    def reconcile_sources(self, sources: Sequence[Source]) -> None:
        """Restore the source registry, recording per-source problems in `source_reconciliation_errors`."""
        self.source_reconciliation_errors = {}
        desired_ids = {source.source_id for source in sources}
        for source_id in list(self._sources):
            if source_id not in desired_ids:
                self.remove_source(source_id)
        current = dict(self._sources)
        for source in sources:
            if current.get(source.source_id) == source:
                continue
            self.remove_source(source.source_id)
            try:
                self.add_source(source)
            except Exception as error:  # noqa: BLE001
                self.source_reconciliation_errors[source.source_id] = str(error)
                continue
            problem = self._source_problem(source)
            if problem:
                self.source_reconciliation_errors[source.source_id] = problem

    def _source_problem(self, source: Source) -> str:
        """Why this source cannot currently be used, or "" if it can."""
        if not source.database_id:
            return (
                "This source has no database_id. It was written by a version "
                "that called it 'adapter_id'; re-create the source against a "
                "registered database."
            )
        try:
            registration = self._databasehub.get_registration(source.database_id)
        except Exception as error:  # noqa: BLE001
            return str(error)
        if registration.database_type != source.source_type:
            return (
                f"Source is a {source.source_type!r} source but database "
                f"{source.database_id!r} is a {registration.database_type!r} "
                "database"
            )
        return ""

    @property
    def assets(self) -> Mapping[str, AssetT]:
        return MappingProxyType(self._assets)

    @property
    def asset_count(self) -> int:
        return len(self._assets)

    def register_assets(self, assets: Sequence[AssetT]) -> None:
        """Take ownership of assets. Does not put them in a pool or index them."""
        for asset in assets:
            self._assets[asset.asset_id] = asset

    def forget_assets(self, asset_ids: Collection[str]) -> List[str]:
        """Drop assets from the library and its pools; materialized records are left to the caller."""
        removed = [
            asset_id
            for asset_id in dict.fromkeys(asset_ids)
            if asset_id in self._assets
        ]
        if not removed:
            return []
        for asset_id in removed:
            del self._assets[asset_id]
        for asset_pool in self._asset_pools.values():
            asset_pool.forget_asset_ids(removed)
        return removed

    @property
    def asset_pools(self) -> Mapping[str, AssetPool]:
        return MappingProxyType(self._asset_pools)

    def create_asset_pool(
        self,
        asset_pool_id: str,
        name: str,
        source_configurations: Sequence[Mapping[str, Any]] = (),
        metadata: Optional[Mapping[str, Any]] = None,
        asset_ids: Iterable[str] = (),
        revision: int = 0,
        source_statuses: Optional[Mapping[str, SourceSyncStatus]] = None,
        tolerant: bool = False,
    ) -> AssetPool:
        """Create a pool and the projection each of its sources needs.

        `asset_ids` / `revision` / `source_statuses` / `tolerant` are only for restoring a persisted pool.
        """
        if not asset_pool_id:
            raise ValueError("An asset pool needs an id")
        if asset_pool_id in self._asset_pools:
            raise ValueError(f"Asset pool {asset_pool_id!r} already exists")
        asset_pool = AssetPool(
            asset_pool_id=asset_pool_id,
            name=name,
            asset_ids=list(asset_ids),
            revision=revision,
            metadata=dict(metadata or {}),
        )
        if source_statuses:
            # Seeded first: a restored serving state decides whether a projection is built.
            asset_pool.source_statuses = dict(source_statuses)
        unavailable = self._attach_sources(
            asset_pool, source_configurations, tolerant=tolerant
        )
        for source_id, (_, reason) in unavailable.items():
            status = asset_pool.source_statuses.get(source_id)
            if status is not None:
                status.mark_failed(reason)
        self._asset_pools[asset_pool_id] = asset_pool
        return asset_pool

    def remove_asset_pool(self, asset_pool_id: str) -> bool:
        return self._asset_pools.pop(asset_pool_id, None) is not None

    def set_asset_pool_sources(
        self,
        asset_pool_id: str,
        source_configurations: Sequence[Mapping[str, Any]],
    ) -> None:
        asset_pool = self._require_asset_pool(asset_pool_id)
        if not source_configurations:
            raise ValueError("At least one source configuration is required")
        self._attach_sources(asset_pool, source_configurations)

    def add_assets_to_pool(
        self, asset_pool_id: str, asset_ids: Collection[str]
    ) -> None:
        asset_pool = self._require_asset_pool(asset_pool_id)
        missing = set(asset_ids) - set(self._assets)
        if missing:
            raise ValueError(f"Asset(s) not found: {', '.join(sorted(missing))}")
        added = set(asset_ids) - set(asset_pool.asset_ids)
        affected = self._affected_source_assets(asset_pool, added)
        asset_pool.add_asset_ids(asset_ids, source_ids=affected)

    def _source_accepts_asset(self, source: Source, asset: AssetT) -> bool:
        """Scope check without a projection, for frozen/unavailable bindings."""
        return True

    def _affected_source_assets(
        self,
        asset_pool: AssetPool,
        asset_ids: Collection[str],
        source_ids: Optional[Collection[str]] = None,
    ) -> Dict[str, List[str]]:
        projections = {p.source.source_id: p for p in asset_pool.projections}
        affected = {}
        for source_id in asset_pool.source_statuses:
            if source_ids is not None and source_id not in source_ids:
                continue
            projection = projections.get(source_id)
            source = (
                self._sources.get(source_id)
                or asset_pool.frozen_sources.get(source_id)
                or asset_pool.unavailable_sources.get(source_id)
            )
            selected = []
            for asset_id in asset_ids:
                if asset_id not in self._assets:
                    continue
                asset = self._assets[asset_id]
                accepts = (
                    projection.accepts(asset) if projection is not None
                    else source is None or self._source_accepts_asset(source, asset)
                )
                if accepts:
                    selected.append(asset_id)
            if selected:
                affected[source_id] = selected
        return affected

    def note_assets_changed(
        self,
        asset_ids: Collection[str],
        source_ids: Optional[Collection[str]] = None,
    ) -> None:
        """Mark replaced assets as pending in every pool holding them, optionally only for `source_ids`."""
        for asset_pool in self._asset_pools.values():
            held = set(asset_pool.asset_ids)
            changed = [asset_id for asset_id in asset_ids if asset_id in held]
            affected = self._affected_source_assets(asset_pool, changed, source_ids)
            asset_pool.mark_assets_changed(changed, source_asset_ids=affected)

    def _attach_sources(
        self,
        asset_pool: AssetPool,
        source_configurations: Sequence[Mapping[str, Any]],
        tolerant: bool = False,
    ) -> Dict[str, Tuple[Source, str]]:
        """Resolve the configurations and give `asset_pool` their projections.

        Returns `{source_id: (source, reason)}` for unbuildable projections, only
        when `tolerant` (restore); otherwise rolls back created sources and raises.
        """
        source_configurations, replaces = updates.split_replaces(
            source_configurations
        )
        sources, created_source_ids = self._resolve_source_configurations(
            source_configurations, tolerant=tolerant
        )
        attached_ids = [source.source_id for source in sources]
        try:
            replaces = {
                new: updates.resolve_ref(old, self._sources)
                for new, old in replaces.items()
            }
            if replaces:
                updates.check_replacements(
                    asset_pool, attached_ids, replaces, self._sources
                )
            for new in replaces:
                if not self._sources[new].enabled:
                    raise updates.SourceRuleError(
                        f"Source {new!r} is disabled and could not catch up; "
                        "enable it before attaching it as a replacement"
                    )
        except Exception:
            for source_id in created_source_ids:
                self.remove_source(source_id)
            raise
        previous = set(asset_pool.source_statuses)
        projections = []
        unavailable: Dict[str, Tuple[Source, str]] = {}
        frozen: Dict[str, Source] = {}
        for source in sources:
            registered = self._sources.get(source.source_id, source)
            status = asset_pool.source_statuses.get(source.source_id)
            if source.source_id not in replaces and (
                not registered.enabled
                or (status is not None and status.serving_state == binding.DEGRADE)
            ):
                # Kept, not built: no projection, so no writes and no model.
                frozen[source.source_id] = registered
                continue
            try:
                projections.append(
                    self.build_projection(str(uuid.uuid4()), asset_pool.name, source)
                )
            except Exception as error:  # noqa: BLE001
                if not tolerant:
                    for source_id in created_source_ids:
                        self.remove_source(source_id)
                    raise
                unavailable[source.source_id] = (source, str(error))
                self.source_reconciliation_errors[source.source_id] = str(error)
        asset_pool.set_projections(
            projections,
            self._already_indexed(asset_pool, projections),
            unavailable=unavailable,
            frozen=frozen,
        )
        if tolerant:
            return unavailable
        updates.drop_stale_replaces(asset_pool, attached_ids)
        for new, old in replaces.items():
            asset_pool.source_statuses[new].replaces = old
        self._apply_transitions(
            asset_pool,
            state_machine.on_attach(
                state_machine.views(asset_pool, self._sources),
                newly_attached=[
                    source_id
                    for source_id in asset_pool.source_statuses
                    if source_id not in previous
                ],
                redeclared=[source_id for source_id in replaces if source_id in previous],
            ),
        )
        return unavailable

    def _already_indexed(
        self, asset_pool: AssetPool, projections: Sequence[Projection]
    ) -> Dict[str, Collection[str]]:
        """Which of the pool's assets each newly attached source already holds."""
        if not asset_pool.asset_ids:
            return {}
        already: Dict[str, Collection[str]] = {}
        for projection in projections:
            source_id = projection.source.source_id
            if source_id in asset_pool.source_statuses:
                continue
            if not isinstance(projection, ChunkProjection):
                continue
            wanted = [
                asset_id
                for asset_id in asset_pool.asset_ids
                if projection.accepts(self._assets[asset_id])
            ]
            try:
                already[source_id] = projection.indexed_asset_ids(wanted)
            except Exception:  # noqa: BLE001 - an unreachable source syncs later
                continue
        return already

    def _resolve_source_configurations(
        self, configurations: Sequence[Mapping[str, Any]], tolerant: bool = False
    ) -> Tuple[List[Source], List[str]]:
        sources: List[Source] = []
        created_source_ids: List[str] = []
        try:
            for configuration in configurations:
                source_id = configuration.get("source_id")
                if source_id:
                    source = self._sources.get(str(source_id))
                    if source is None and tolerant:
                        # Unreconciled source on restore: rebuild it so it is kept as unavailable.
                        source = Source.from_record(configuration)
                    if source is None:
                        raise ValueError(f"Source {source_id!r} not found")
                else:
                    required = ("name", "database_id", "collection_name")
                    missing = [key for key in required if not configuration.get(key)]
                    if missing:
                        raise ValueError(
                            "A source configuration without source_id requires "
                            + ", ".join(required)
                        )
                    source = self.create_source(
                        name=str(configuration["name"]),
                        database_id=str(configuration["database_id"]),
                        collection_name=str(configuration["collection_name"]),
                        configuration=dict(
                            configuration.get("operator_options") or {}
                        ),
                    )
                    created_source_ids.append(source.source_id)
                if any(item.source_id == source.source_id for item in sources):
                    raise ValueError(f"Source {source.source_id!r} is duplicated")
                sources.append(source)
        except Exception:
            for source_id in created_source_ids:
                self.remove_source(source_id)
            raise
        return sources, created_source_ids

    def _sync_projection_order(self, asset_pool: AssetPool) -> Sequence[Projection]:
        """The order to sync the pool's projections in; defaults to attachment order."""
        return asset_pool.projections

    def _prepare_projection_add(
        self, asset_pool: AssetPool, projection: Projection, assets: Sequence[AssetT]
    ) -> None:
        """Hook called just before `projection.add(assets)`; default no-op."""

    def _finish_projection_add(
        self, asset_pool: AssetPool, projection: Projection, assets: Sequence[AssetT]
    ) -> None:
        """Hook called just after `projection.add(assets)`; default no-op."""

    def sync_asset_pool(self, asset_pool_id: str) -> None:
        """Bring every projection in the pool up to the pool's current revision.

        Syncs of one pool are serialized to avoid duplicate writes; different pools run in parallel.
        """
        with self._sync_lock(asset_pool_id):
            self._sync_pass(self._require_asset_pool(asset_pool_id))

    def _sync_lock(self, asset_pool_id: str) -> threading.RLock:
        """The lock serializing syncs of `asset_pool_id` (reentrant, for hooks)."""
        with self._sync_locks_guard:
            return self._sync_locks.setdefault(asset_pool_id, threading.RLock())

    def _sync_pass(self, asset_pool: AssetPool) -> None:
        """One pass of `sync_asset_pool`; ingests landing mid-sync are picked up next pass."""
        revision = asset_pool.revision
        pool_asset_ids = list(asset_pool.asset_ids)
        for projection in self._sync_projection_order(asset_pool):
            source_id = projection.source.source_id
            status = asset_pool.source_statuses.get(source_id)
            if status is None or (
                status.status == "ready" and status.indexed_revision >= revision
            ):
                continue
            if binding.is_frozen(self._sources.get(source_id, projection.source), status):
                continue
            # Progress is measured only against the assets this source accepts.
            asset_ids = [
                asset_id
                for asset_id in pool_asset_ids
                if projection.accepts(self._assets[asset_id])
            ]
            indexed_ids = set(status.indexed_asset_ids) & set(asset_ids)
            if asset_ids and isinstance(projection, ChunkProjection):
                # The backend's actual holdings take precedence over the recorded set.
                try:
                    indexed_ids = set(projection.indexed_asset_ids(asset_ids))
                except Exception:  # noqa: BLE001 - fall back to what we recorded
                    pass
            # Stale assets have records in the source, but outdated ones.
            indexed_ids -= set(status.stale_asset_ids)
            missing_ids = [
                asset_id for asset_id in asset_ids if asset_id not in indexed_ids
            ]
            assets = [self._assets[asset_id] for asset_id in missing_ids]
            status.mark_indexing()
            completed_ids = set()

            def record_batch(ids):
                completed_ids.update(ids)
                status.indexed_asset_ids.extend(
                    asset_id for asset_id in ids if asset_id not in status.indexed_asset_ids
                )

            try:
                if assets:
                    self._prepare_projection_add(asset_pool, projection, assets)
                if assets and isinstance(projection, ChunkProjection):
                    # Idempotent write; a preparing binding is written in recorded batches.
                    backfill.add_in_batches(
                        projection,
                        assets,
                        self.BACKFILL_BATCH_SIZE
                        if status.serving_state == binding.PREPARING
                        else None,
                        on_batch=record_batch,
                    )
                elif assets:
                    projection.add(assets)
                if assets:
                    self._finish_projection_add(asset_pool, projection, assets)
            except Exception as error:  # noqa: BLE001 - reported on the source
                # Partially written assets are marked stale so the retry deletes them first.
                if isinstance(projection, ChunkProjection):
                    status.mark_stale([
                        asset_id for asset_id in missing_ids
                        if asset_id not in completed_ids
                    ])
                status.mark_failed(str(error))
                continue
            caught_up = status.pending_revision <= revision
            status.mark_ready(
                asset_pool.revision if caught_up else revision,
                dict.fromkeys(
                    (
                        *status.indexed_asset_ids,
                        *(asset_id for asset_id in asset_ids if asset_id in indexed_ids),
                        *missing_ids,
                    )
                ),
                clear_stale=caught_up,
            )
            if not caught_up:
                status.mark_pending()
            if (
                getattr(projection, "kind", "") == "vector"
                and status.serving_state == binding.PREPARING
                and not status.replaces
            ):
                # Serve a completed vector backfill before graph hooks pick a text source.
                self._apply_transitions(
                    asset_pool,
                    state_machine.on_sync_result(
                        {source_id: state_machine.views(asset_pool, self._sources)[source_id]}
                    ),
                )
        self._apply_transitions(
            asset_pool,
            state_machine.on_sync_result(
                state_machine.views(asset_pool, self._sources)
            ),
        )

    def add_assets(
        self,
        assets: Sequence[AssetT],
        asset_pool_ids: Collection[str] = (),
    ) -> Mapping[str, Any]:
        """Materialize each asset in every selected projection that accepts it."""
        selected = self._select_asset_pools(asset_pool_ids)
        shares = {
            id(projection): [
                asset for asset in assets if projection.accepts(asset)
            ]
            for asset_pool in selected
            for projection in asset_pool.projections
        }
        if assets and not any(shares.values()):
            raise ValueError("No selected projection accepts these assets")
        return {
            asset_pool.asset_pool_id: merge_counts(
                projection.add(shares[id(projection)])
                for projection in asset_pool.projections
                if shares.get(id(projection))
            )
            for asset_pool in selected
            if any(
                shares.get(id(projection))
                for projection in asset_pool.projections
            )
        }

    def remove_assets(
        self,
        asset_ids: Collection[str],
        asset_pool_ids: Collection[str] = (),
    ) -> Mapping[str, Any]:
        return {
            asset_pool.asset_pool_id: sum(
                projection.remove(asset_ids)
                for projection in self._require_pool_projections(asset_pool)
            )
            for asset_pool in self._select_asset_pools(asset_pool_ids)
        }

    def ingest(self, requests: Mapping[str, Any]) -> Dict[str, Any]:
        """Materialize a per-pool request directly, bypassing the asset registry."""
        return {
            asset_pool_id: merge_counts(
                projection.materialize(request)
                for projection in self._require_pool_projections(
                    self._require_asset_pool(asset_pool_id)
                )
            )
            for asset_pool_id, request in requests.items()
        }

    def retrieve(self, requests: Mapping[str, Any]) -> Dict[str, Any]:
        """Retrieve through each pool's serving sources, stamping each result with its source."""
        results: Dict[str, Any] = {}
        for asset_pool_id, request in requests.items():
            asset_pool = self._require_asset_pool(asset_pool_id)
            self._require_pool_projections(asset_pool)
            results[asset_pool_id] = [
                result
                for projection in exposure.serving_projections(asset_pool)
                for result in exposure.stamp_results(
                    projection.retrieve(request), projection.source
                )
            ]
        return results

    def _require_asset_pool(self, asset_pool_id: str) -> AssetPool:
        asset_pool = self._asset_pools.get(asset_pool_id)
        if asset_pool is None:
            raise ValueError(f"Asset pool {asset_pool_id!r} not found")
        return asset_pool

    @staticmethod
    def _require_pool_projections(asset_pool: AssetPool) -> Sequence[Projection]:
        if not asset_pool.projections:
            raise ValueError(f"Asset pool {asset_pool.asset_pool_id!r} has no source")
        return asset_pool.projections

    def _select_asset_pools(
        self, asset_pool_ids: Collection[str]
    ) -> List[AssetPool]:
        if not asset_pool_ids:
            return list(self._asset_pools.values())
        return [
            self._require_asset_pool(asset_pool_id)
            for asset_pool_id in asset_pool_ids
        ]

    def chunk_projections(self) -> Dict[Any, ChunkProjection]:
        """Every chunk projection in the library, keyed by (and deduplicated on) collection."""
        return {
            projection.collection: projection
            for asset_pool in self._asset_pools.values()
            for projection in asset_pool.projections
            if isinstance(projection, ChunkProjection)
        }

    def clear(self) -> None:
        """Forget all pools, projections, and sources without deleting data."""
        self._asset_pools.clear()
        self._sources.clear()
        self.source_reconciliation_errors.clear()
        self.default_content_source_id = ""

    def to_record(self) -> dict:
        """This library as persisted; subclasses add their own keys."""
        return {
            "idx": self.idx,
            "name": self.name,
            "description": self.description,
            "default_content_source_id": self.default_content_source_id,
            "sources": [source.to_record() for source in self._sources.values()],
            "assets": [
                self.asset_to_record(asset) for asset in self._assets.values()
            ],
            "asset_pools": [
                {
                    "asset_pool_id": asset_pool.asset_pool_id,
                    "name": asset_pool.name,
                    "metadata": dict(asset_pool.metadata),
                    "asset_ids": list(asset_pool.asset_ids),
                    "revision": asset_pool.revision,
                    "source_statuses": {
                        source_id: asdict(status)
                        for source_id, status in asset_pool.source_statuses.items()
                    },
                    # Include unavailable and frozen sources so they are not lost on save.
                    "sources": [
                        projection.source.to_record()
                        for projection in asset_pool.projections
                    ]
                    + [
                        source.to_record()
                        for source in asset_pool.unavailable_sources.values()
                    ]
                    + [
                        source.to_record()
                        for source in asset_pool.frozen_sources.values()
                    ],
                }
                for asset_pool in self._asset_pools.values()
            ],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any], databasehub=None):
        library = cls(
            name=record["name"],
            description=record.get("description"),
            idx=record.get("idx"),
            databasehub=databasehub,
            # A legacy `content_database` is migrated in `restore`, not passed here.
        )
        library.restore(record)
        return library

    def restore(self, record: Mapping[str, Any]) -> None:
        """Rebuild from a record: sources first, then assets, then pools."""
        sources = [
            self._with_profile(Source.from_record(source_record))
            for source_record in record.get("sources") or []
        ]
        sources, default_content_source_id = self._content_source_records(
            record, sources
        )
        self.reconcile_sources(sources)
        # Kept even if the source reconciled with an error, so content is never silently redirected.
        if default_content_source_id in self._sources:
            self.default_content_source_id = default_content_source_id
        self.register_assets(
            [
                self.asset_from_record(asset_record)
                for asset_record in record.get("assets") or []
            ]
        )
        for asset_pool_record in self._asset_pool_records(record):
            configurations = tuple(asset_pool_record["_sources"])
            if "sources" in record:
                # Skip pool entries for sources no longer in the registry.
                declared = {source.source_id for source in sources}
                configurations = tuple(
                    entry for entry in configurations
                    if not entry.get("source_id") or entry["source_id"] in declared
                )
            pool = self.create_asset_pool(
                asset_pool_id=str(
                    asset_pool_record.get("asset_pool_id")
                    or asset_pool_record["asset_set_id"]
                ),
                name=str(asset_pool_record["name"]),
                source_configurations=configurations,
                metadata=dict(asset_pool_record.get("metadata") or {}),
                asset_ids=asset_pool_record.get("asset_ids") or (),
                revision=int(asset_pool_record.get("revision") or 0),
                source_statuses={
                    source_id: SourceSyncStatus(**status_record)
                    for source_id, status_record in dict(
                        asset_pool_record.get("source_statuses") or {}
                    ).items()
                },
                tolerant=True,
            )
            updates.drop_stale_replaces(pool, tuple(pool.source_statuses))

    def _with_profile(self, source: Source) -> Source:
        """Give a profile-less source one, best effort."""
        if source.profile:
            return source
        try:
            return replace(source, profile=self.describe_source(source))
        except Exception:  # noqa: BLE001 - reconciliation reports it
            return source

    def _content_source_records(
        self, record: Mapping[str, Any], sources: List[Source]
    ) -> Tuple[List[Source], str]:
        """The sources to restore, and the default content source id.

        Resolved from `default_content_source_id`, else an object source named
        `content`, else a source synthesized from a legacy `content_database`.
        """
        named = str(record.get("default_content_source_id") or "")
        if named:
            return sources, named
        by_name = next(
            (
                source
                for source in sources
                if source.source_type == "object"
                and source.name == self.CONTENT_SOURCE_NAME
            ),
            None,
        )
        if by_name is not None:
            return sources, by_name.source_id
        legacy_database = str(record.get("content_database") or "")
        if legacy_database and not any(
            source.source_type == "object" for source in sources
        ):
            synthesized = Source(
                source_id=str(uuid.uuid4()),
                name=self.CONTENT_SOURCE_NAME,
                source_type="object",
                database_id=legacy_database,
                location=ObjectCollection(self.library_id),
            )
            return [*sources, synthesized], synthesized.source_id
        return sources, ""

    @staticmethod
    def _asset_pool_records(record: Mapping[str, Any]) -> List[dict]:
        """Pool records with `_sources` resolved, including legacy `source`/`projection_ids`/`asset_sets` shapes."""
        legacy_projections = {
            str(item["projection_id"]): item
            for item in record.get("projections") or []
        }
        resolved = []
        for pool_record in record.get("asset_pools") or record.get("asset_sets") or []:
            sources = list(pool_record.get("sources") or ())
            if not sources and pool_record.get("source") is not None:
                sources = [pool_record["source"]]
            if not sources:
                sources = [
                    legacy_projections[str(projection_id)]["source"]
                    for projection_id in pool_record.get("projection_ids") or ()
                ]
            resolved.append({**pool_record, "_sources": sources})
        return resolved
