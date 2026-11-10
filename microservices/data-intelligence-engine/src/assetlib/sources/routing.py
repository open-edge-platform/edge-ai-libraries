# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from assetlib.sources import binding


def pool_routing(
    pool,
    sources: Mapping[str, Any],
    kinds: Sequence[str],
    covers: Callable[[Any, str], Optional[str]],
) -> Dict[str, Any]:
    """Which sources take each content kind in one pool, and which kinds no serving binding takes.

    `covers(source, kind)` returns how a source embeds that kind (e.g. "vector"), or None.
    """
    routes: Dict[str, List[Dict[str, Any]]] = {kind: [] for kind in kinds}
    for source_id, status in pool.source_statuses.items():
        source = sources.get(source_id)
        if source is None:
            continue
        effective = binding.effective_state(source, status)
        for kind in kinds:
            how = covers(source, kind)
            if how is None:
                continue
            routes[kind].append(
                {
                    "source_id": source_id,
                    "source_name": source.name,
                    "via": how,
                    "serving_state": status.serving_state,
                    "effective_state": effective,
                }
            )
    uncovered = [
        kind
        for kind, entries in routes.items()
        if not any(entry["effective_state"] == binding.SERVING for entry in entries)
    ]
    return {"pool_id": pool.asset_pool_id, "routes": routes, "uncovered": uncovered}


__all__ = ["pool_routing"]
