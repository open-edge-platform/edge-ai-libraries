# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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
