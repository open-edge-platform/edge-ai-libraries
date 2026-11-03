# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Asset libraries: assets, the sources they are materialized into, and pools.

`AssetLibrary` is the concept and the working implementation. A domain
specializes it by saying what its assets are and which projection a source gets
-- see `data-intelligence-engine/src/core/file_asset_library.py:FileAssetLibrary`.
"""

from assetlib.contracts import (
    Asset,
    ChunkProjection,
    Projection,
    Source,
)
from assetlib.library import AssetLibrary, collection_name, merge_counts
from assetlib.pool import AssetPool, SourceSyncStatus

__all__ = [
    "Asset",
    "AssetLibrary",
    "AssetPool",
    "ChunkProjection",
    "Projection",
    "Source",
    "SourceSyncStatus",
    "collection_name",
    "merge_counts",
]
