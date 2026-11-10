# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    Any,
    Collection,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from assetlib.contracts import Projection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SourceSyncStatus:
    """How far one source has got with its pool's assets."""

    source_id: str
    status: str = "pending"
    indexed_revision: int = -1
    indexed_asset_ids: List[str] = field(default_factory=list)
    # Assets whose content changed since this source materialized them; the backend still holds old records.
    stale_asset_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None
    updated_at: str = field(default_factory=_now)
    # Whether this source answers retrievals; maintained by `assetlib/sources/state_machine.py`.
    serving_state: str = "SERVING"
    # The source this one is waiting to replace in this pool.
    replaces: Optional[str] = None
    serving_history: List[Dict[str, Any]] = field(default_factory=list)
    # OKF extraction: document changes seen vs. covered by the last successful extraction.
    extraction_changes: int = 0
    extraction_done: int = 0
    # Internal: latest pool revision that added work for this source; not in the public status.
    pending_revision: int = -1

    @property
    def extraction_outdated(self) -> bool:
        return self.extraction_changes > self.extraction_done

    def note_extraction_input_changed(self) -> None:
        """Documents this source extracts from were added, replaced or removed."""
        self.extraction_changes += 1

    def _touch(self, status: str) -> None:
        self.status = status
        self.updated_at = _now()

    def mark_pending(self) -> None:
        """Queue work without hiding an active write or the last failure."""
        self._touch("indexing" if self.status == "indexing" else "pending")

    def mark_indexing(self) -> None:
        self._touch("indexing")

    def mark_ready(
        self,
        revision: int,
        indexed_asset_ids: Iterable[str],
        *,
        clear_stale: bool = True,
    ) -> None:
        self.indexed_revision = revision
        self.indexed_asset_ids = list(indexed_asset_ids)
        if clear_stale:
            written = set(self.indexed_asset_ids)
            self.stale_asset_ids = [
                asset_id for asset_id in self.stale_asset_ids if asset_id not in written
            ]
        self.error = None
        self._touch("ready")

    def mark_stale(self, asset_ids: Collection[str]) -> None:
        known = set(self.stale_asset_ids)
        self.stale_asset_ids.extend(
            asset_id for asset_id in dict.fromkeys(asset_ids) if asset_id not in known
        )

    def mark_failed(self, error: str) -> None:
        """Leaves `indexed_*` unchanged."""
        self.error = error
        self._touch("failed")

    def forget_asset_ids(self, asset_ids: Collection[str]) -> None:
        dropped = set(asset_ids)
        self.indexed_asset_ids = [
            asset_id
            for asset_id in self.indexed_asset_ids
            if asset_id not in dropped
        ]
        self.stale_asset_ids = [
            asset_id for asset_id in self.stale_asset_ids if asset_id not in dropped
        ]


@dataclass
class AssetPool:
    """A set of assets and the projections they are materialized into; mutated in place."""

    asset_pool_id: str
    name: str
    projections: Tuple[Projection, ...] = ()
    asset_ids: List[str] = field(default_factory=list)
    revision: int = 0
    source_statuses: Dict[str, SourceSyncStatus] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    #: Attached sources with no projection because their database is missing or unreachable.
    #: Kept so they are persisted; status `failed`.
    unavailable_sources: Dict[str, Any] = field(default_factory=dict)
    #: Attached sources deliberately given no projection (deprecated or disabled).
    frozen_sources: Dict[str, Any] = field(default_factory=dict)
    #: Projections that answer retrievals; replaced as one tuple so readers see a consistent set.
    serving: Tuple[Projection, ...] = ()

    def __post_init__(self) -> None:
        self.projections = tuple(self.projections)
        self.refresh_serving()

    def add_asset_ids(
        self,
        asset_ids: Iterable[str],
        source_ids: Optional[Collection[str]] = None,
    ) -> bool:
        """Extend the set, reopening only sources that accept the new assets."""
        known = set(self.asset_ids)
        added = [
            asset_id
            for asset_id in dict.fromkeys(asset_ids)
            if asset_id not in known
        ]
        if not added:
            return False
        self.asset_ids.extend(added)
        self._advance_revision(source_ids)
        return True

    def _advance_revision(self, source_ids: Optional[Collection[str]]) -> None:
        previous = self.revision
        self.revision += 1
        for source_id, status in self.source_statuses.items():
            if source_ids is None or source_id in source_ids:
                status.pending_revision = self.revision
                if source_id not in self.unavailable_sources:
                    status.mark_pending()
            elif status.status == "ready" and status.indexed_revision == previous:
                status.indexed_revision = self.revision

    def mark_assets_changed(
        self,
        asset_ids: Collection[str],
        source_ids: Optional[Collection[str]] = None,
        *,
        source_asset_ids: Optional[Mapping[str, Collection[str]]] = None,
    ) -> bool:
        """Re-open assets already in the pool whose content has been replaced."""
        held = set(self.asset_ids)
        changed = [
            asset_id for asset_id in dict.fromkeys(asset_ids) if asset_id in held
        ]
        affected = {}
        for source_id in self.source_statuses:
            if source_ids is not None and source_id not in source_ids:
                continue
            accepted = (
                set(source_asset_ids.get(source_id, ()))
                if source_asset_ids is not None else set(changed)
            )
            selected = [asset_id for asset_id in changed if asset_id in accepted]
            if selected:
                affected[source_id] = selected
        if not changed or not affected:
            return False
        for source_id, selected in affected.items():
            self.source_statuses[source_id].mark_stale(selected)
        self._advance_revision(affected)
        return True

    def forget_asset_ids(self, asset_ids: Collection[str]) -> bool:
        """Drop assets from the pool without bumping the revision; True if anything was dropped."""
        dropped = set(asset_ids)
        kept = [
            asset_id for asset_id in self.asset_ids if asset_id not in dropped
        ]
        if len(kept) == len(self.asset_ids):
            return False
        self.asset_ids = kept
        for status in self.source_statuses.values():
            status.forget_asset_ids(dropped)
        return True

    def set_projections(
        self,
        projections: Sequence[Projection],
        already_indexed: Optional[Mapping[str, Collection[str]]] = None,
        unavailable: Optional[Mapping[str, Tuple[Any, str]]] = None,
        frozen: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Replace the projections, keeping the progress of sources that stay."""
        self.projections = tuple(projections)
        self.unavailable_sources = {
            source_id: source for source_id, (source, _) in (unavailable or {}).items()
        }
        seeded = already_indexed or {}
        statuses = {}
        for projection in self.projections:
            source_id = projection.source.source_id
            existing = self.source_statuses.get(source_id)
            statuses[source_id] = (
                existing
                if existing is not None
                else self._initial_status(source_id, seeded.get(source_id, ()))
            )
        self.frozen_sources = dict(frozen or {})
        for source_id in self.frozen_sources:
            statuses[source_id] = self.source_statuses.get(
                source_id
            ) or self._initial_status(source_id, seeded.get(source_id, ()))
        for source_id, (_, reason) in (unavailable or {}).items():
            status = self.source_statuses.get(source_id) or SourceSyncStatus(
                source_id=source_id
            )
            status.mark_failed(reason)
            statuses[source_id] = status
        self.source_statuses = statuses
        self.refresh_serving()

    def refresh_serving(self) -> None:
        """Recompute which projections serve, and publish them in one assignment."""
        self.serving = tuple(
            projection
            for projection in self.projections
            if getattr(
                self.source_statuses.get(projection.source.source_id),
                "serving_state",
                "SERVING",
            )
            == "SERVING"
        )

    def freeze(self, source_id: str, source: Any = None) -> bool:
        """Drop a binding's projection but keep the binding. True if it had one."""
        held = [p for p in self.projections if p.source.source_id == source_id]
        if not held and source_id in self.frozen_sources:
            return False
        if source is None:
            source = held[0].source if held else None
        if source is None:
            return False
        self.frozen_sources[source_id] = source
        self.projections = tuple(
            p for p in self.projections if p.source.source_id != source_id
        )
        self.refresh_serving()
        return bool(held)

    def thaw(self, projection: Projection) -> None:
        """Give a frozen binding its projection back."""
        source_id = projection.source.source_id
        self.frozen_sources.pop(source_id, None)
        self.projections = tuple(
            p for p in self.projections if p.source.source_id != source_id
        ) + (projection,)
        self.refresh_serving()

    def _initial_status(
        self, source_id: str, already_indexed: Collection[str]
    ) -> SourceSyncStatus:
        held = set(already_indexed)
        indexed = [asset_id for asset_id in self.asset_ids if asset_id in held]
        status = SourceSyncStatus(source_id=source_id)
        if len(indexed) == len(self.asset_ids):
            status.mark_ready(self.revision, indexed)
        else:
            status.indexed_asset_ids = indexed
            status.mark_pending()
        return status
