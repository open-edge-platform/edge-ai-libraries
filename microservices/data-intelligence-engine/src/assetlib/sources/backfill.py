# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Writing a preparing binding's backlog in batches.

An ordinary sync hands a projection everything it is missing in one `add`.
That is right for an ingest, which brings a handful of assets. A binding that
is *preparing* -- a new model attached to a pool that already holds the whole
corpus -- is missing all of it, and one `add` would build every node and every
vector in memory before writing any, and on failure throw all of it away.

So a preparing binding is written a batch at a time. Each batch is made
idempotent the same way the single write is (delete the batch's records, then
add), and recorded on the status as it lands, so a pass that fails part-way
leaves the batches that did land counted and the retry starts after them.
"""

from typing import Any, Callable, Optional, Sequence


def add_in_batches(
    projection: Any,
    assets: Sequence[Any],
    batch_size: Optional[int],
    on_batch: Callable[[Sequence[str]], None] = lambda ids: None,
    idempotent: bool = True,
) -> None:
    """`projection.add(assets)`, `batch_size` at a time (all at once if falsy)."""
    assets = list(assets)
    size = batch_size if batch_size and batch_size > 0 else len(assets) or 1
    for start in range(0, len(assets), size):
        batch = assets[start: start + size]
        ids = [asset.asset_id for asset in batch]
        if idempotent:
            projection.delete_by_metadata("asset_id", ids)
        projection.add(batch)
        on_batch(ids)


__all__ = ["add_in_batches"]
