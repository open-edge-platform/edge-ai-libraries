# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""An asset pool, and how far each of its sources has got with it.

Nothing here knows what an asset *is*. A pool holds asset ids, the projections
those assets are materialized into, and a per-source record of progress -- which
is the same bookkeeping whether the assets are documents, images, or rows.
"""

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
    """How far one source has got with its pool's assets.

    Mutable, and it transitions itself. It used to be frozen and rebuilt from
    scratch at each transition, which meant every construction site had to
    re-list the fields it wanted to keep -- and the ones it forgot were silently
    reset. A failure diagnosis, in particular, did not survive the next
    unrelated ingest.
    """

    source_id: str
    status: str = "pending"
    indexed_revision: int = -1
    indexed_asset_ids: List[str] = field(default_factory=list)
    # Assets whose content changed since this source materialized them. The
    # source still *holds* records for them, so asking the backend what it has
    # would answer "these are done" -- this is how sync knows better.
    stale_asset_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None
    updated_at: str = field(default_factory=_now)
    # Whether this source answers the pool's retrievals -- a second dimension
    # beside `status`, maintained by `assetlib/sources/state_machine.py`. A record
    # written before it existed restores as SERVING, which is what every
    # attached source effectively was.
    serving_state: str = "SERVING"
    # The source this one is waiting to replace in this pool, until it does.
    replaces: Optional[str] = None
    serving_history: List[Dict[str, Any]] = field(default_factory=list)
    # A graph source extracting documents into OKF: how many document changes
    # it has seen, and how many the last successful extraction covered. More
    # changes than covered means its generated bundle is out of date.
    extraction_changes: int = 0
    extraction_done: int = 0

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
        """There is new work. Keeps `error`: the last failure still explains it."""
        self._touch("pending")

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
        # A pass covering an older pool revision must not acknowledge changes
        # that landed while it was writing, even for the same asset ids.
        if clear_stale:
            written = set(self.indexed_asset_ids)
            self.stale_asset_ids = [
                asset_id for asset_id in self.stale_asset_ids if asset_id not in written
            ]
        self.error = None
        self._touch("ready")

    def mark_stale(self, asset_ids: Collection[str]) -> None:
        """These assets' content changed; what this source holds is out of date."""
        known = set(self.stale_asset_ids)
        self.stale_asset_ids.extend(
            asset_id for asset_id in dict.fromkeys(asset_ids) if asset_id not in known
        )

    def mark_failed(self, error: str) -> None:
        """Leaves `indexed_*` alone -- whatever did land is still there."""
        self.error = error
        self._touch("failed")

    def forget_asset_ids(self, asset_ids: Collection[str]) -> None:
        """Stop counting assets the library no longer has."""
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
    """A set of assets, and the projections each of them is materialized into.

    Mutated in place. It used to be a frozen dataclass replaced wholesale on
    every change, which read as immutable but was not: the containers it points
    at were always mutable, and it was never hashable (two of its fields are
    dicts), so freezing only prevented the one thing nobody does -- rebinding a
    field. What it did cause was lost updates, because a caller holding a
    snapshot across slow I/O wrote its stale copy back over anything that had
    changed meanwhile. `sync_asset_pool` did exactly that, and dropped assets
    ingested while it was running.
    """

    asset_pool_id: str
    name: str
    projections: Tuple[Projection, ...] = ()
    asset_ids: List[str] = field(default_factory=list)
    revision: int = 0
    source_statuses: Dict[str, SourceSyncStatus] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    #: Sources this pool is attached to but currently has no projection for --
    #: because the database they name is not registered, or its backend could
    #: not be reached at restore. Keyed by source id, holding the `Source`.
    #:
    #: They are kept, rather than dropped, because the pool is persisted from
    #: what it holds: forgetting an unbuildable source here would erase it from
    #: the workspace on the next save, quietly turning a missing connection into
    #: a lost configuration. Their status is `failed`, they are invisible to
    #: `sync_asset_pool` (there is nothing to sync through), and they become
    #: real projections again once the database is registered.
    unavailable_sources: Dict[str, Any] = field(default_factory=dict)
    #: Sources attached but deliberately given no projection: deprecated in
    #: this pool, or disabled. Same shape and the same reason to be kept as
    #: `unavailable_sources` -- the pool is persisted from what it holds -- but
    #: not an error: their status stays as it was, and their data stays where
    #: it is. Holding no projection is the point: a frozen source is not
    #: written to and does not keep its model loaded.
    frozen_sources: Dict[str, Any] = field(default_factory=dict)
    #: The projections that answer retrievals, replaced as one tuple whenever a
    #: binding changes state. Readers take it in one attribute load, so a
    #: retrieval running beside a switch-over sees the old set or the new one,
    #: never half of each.
    serving: Tuple[Projection, ...] = ()

    def __post_init__(self) -> None:
        self.projections = tuple(self.projections)
        self.refresh_serving()

    def add_asset_ids(self, asset_ids: Iterable[str]) -> bool:
        """Extend the set. True if anything was new, so the caller can skip a save."""
        known = set(self.asset_ids)
        added = [
            asset_id
            for asset_id in dict.fromkeys(asset_ids)
            if asset_id not in known
        ]
        if not added:
            return False
        self.asset_ids.extend(added)
        self.revision += 1
        for status in self.source_statuses.values():
            status.mark_pending()
        return True

    def mark_assets_changed(
        self,
        asset_ids: Collection[str],
        source_ids: Optional[Collection[str]] = None,
    ) -> bool:
        """Re-open assets already in the pool whose content has been replaced.

        Ingesting a file the library already holds hits the same asset id, so
        there is nothing new to add -- but every source is now holding the old
        version. Bumping the revision is what makes the next sync look, and
        marking the assets stale is what stops it from believing the backend
        when it reports them as already there.

        `source_ids` narrows the stale marking to the sources whose records the
        change affects -- a caption landing changes nothing for the source that
        embedded the clip. The others see the new revision, find nothing
        missing, and settle at it without writing.
        """
        held = set(self.asset_ids)
        changed = [
            asset_id for asset_id in dict.fromkeys(asset_ids) if asset_id in held
        ]
        affected = [
            status
            for source_id, status in self.source_statuses.items()
            if source_ids is None or source_id in source_ids
        ]
        if not changed or not affected:
            return False
        self.revision += 1
        for status in affected:
            status.mark_stale(changed)
        for status in self.source_statuses.values():
            status.mark_pending()
        return True

    def forget_asset_ids(self, asset_ids: Collection[str]) -> bool:
        """Drop assets from the pool. True if anything was actually dropped.

        The revision does not move: removing work does not create any, and every
        source is still as up to date as it was.
        """
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
        """Replace the projections, keeping the progress of sources that stay.

        A source that is still attached keeps its status: re-attaching a list
        that happens to include it must not throw away what it has already
        indexed and make the next sync redo the work.

        A newly attached source is seeded from `already_indexed` -- the pool
        assets that source was found to hold when it was attached. A source that
        already holds all of them is `ready` immediately, including the trivial
        case of a pool with nothing in it yet; anything less is `pending`, and it
        keeps whatever it does hold so the sync only sends the difference.

        `unavailable` maps a source id to `(source, reason)` for a source that
        is attached but could not be given a projection. It keeps its place in
        the pool and reports `failed` with the reason, rather than vanishing.

        `frozen` maps a source id to the `Source` of a binding that is attached
        but deliberately has no projection (see `frozen_sources`). Its status is
        kept as it is, or created if the binding is new.
        """
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
            # Keep whatever progress it had recorded -- the records it wrote are
            # still in the backend, and will be found again when it comes back.
            status = self.source_statuses.get(source_id) or SourceSyncStatus(
                source_id=source_id
            )
            status.mark_failed(reason)
            statuses[source_id] = status
        # Sources no longer attached drop out with their statuses.
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
