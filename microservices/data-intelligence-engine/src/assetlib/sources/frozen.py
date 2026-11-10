# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Collection, Dict, Mapping


def delete_assets(
    databasehub, frozen_sources: Mapping[str, Any], asset_ids: Collection[str]
) -> Dict[str, int]:
    """Remove `asset_ids` from every frozen source's collection, by metadata."""
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
