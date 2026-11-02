# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Which source handles which kind of content in a pool, as configured now.

Routing is not configured in one place, and should not be: the extractor turns
every file into typed blocks the same way, and each source's own filters
(`block_kinds`, `block_roles`, `asset_types`) plus its model's supported
roles decide what it takes. That keeps adding a model a matter of
adding a source -- but it means "what happens to an image in this pool?" has to
be answered by asking every source. This does the asking.

What a source can take is the library specialization's question (`covers`,
supplied by the caller); this module only tabulates the answers per binding.
"""

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from assetlib.sources import binding


def pool_routing(
    pool,
    sources: Mapping[str, Any],
    kinds: Sequence[str],
    covers: Callable[[Any, str], Optional[str]],
) -> Dict[str, Any]:
    """`{routes: {kind: [...]}, uncovered: [...]}` for one pool.

    `covers(source, kind)` returns how a source embeds that kind of content
    (for example "vector" or "caption"), or None if it does not take it. A kind
    is *uncovered* when no serving binding takes it.
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
