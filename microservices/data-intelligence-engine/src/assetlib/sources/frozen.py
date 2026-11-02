# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Housekeeping for frozen bindings, which hold data but no projection.

A frozen binding (deprecated in its pool, or its source disabled) keeps its
collection so it can be rolled back to. Two things still have to reach it:

- **deletes.** An asset deleted from the library must not survive in a frozen
  collection, or a rollback would bring it back. Removing rows needs only the
  database adapter, not the model, so this does not thaw anything.
- **changes.** A re-ingested asset is recorded stale on the frozen binding's
  status like on any other (`AssetPool.mark_assets_changed`); nothing is
  written now, and the sync that follows a thaw re-materializes it.
"""

from typing import Any, Collection, Dict, Mapping


def delete_assets(
    databasehub, frozen_sources: Mapping[str, Any], asset_ids: Collection[str]
) -> Dict[str, int]:
    """Remove `asset_ids` from every frozen source's collection, by metadata.

    A source whose adapter cannot delete by metadata (a graph) is reported by
    raising, the same way deleting from a live graph projection is refused.
    """
    removed: Dict[str, int] = {}
    ids = list(asset_ids)
    if not ids:
        return removed
    for source_id, source in frozen_sources.items():
        adapter = databasehub.get_adapter(source.database_id)
        delete = getattr(adapter, "delete_by_metadata", None)
        if delete is None:
            raise ValueError(
                f"Cannot delete assets from frozen source {source_id!r}: its "
                "backend has no removal support"
            )
        removed[source_id] = int(delete(source.location, "asset_id", ids) or 0)
    return removed


__all__ = ["delete_assets"]
