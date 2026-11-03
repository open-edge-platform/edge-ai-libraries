# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""JSON persistence for asset libraries in the engine workspace.

The chunks themselves already survive a restart -- they are in Milvus -- and an
asset's content is in the object store. What has to be written down is each
asset library, its sources, and its asset pools. Startup restores passive
sources first, then recreates the vector and graph indexers owned by each asset
pool.

Sources name a `database_id`, and the databases are a separate file
(`databasehub/repository.py`) restored *before* this one. A library whose
database is not registered still restores -- with the source reported
unreconciled -- because dropping it here would erase it from the next save.

One JSON file, rewritten whole from the live set, read back on startup. The
rewrite is atomic; see `data-intelligence-engine/src/jsonstore.py`. Callers
serialize their own writes (core/manager.py holds a lock around `save`).
"""

from typing import List

import config, jsonstore

ASSET_LIBRARY_FILE = config.ASSET_LIBRARY_FILE


def save(asset_libraries: List) -> bool:
    """Rewrite the workspace's asset-library file atomically."""
    return jsonstore.write_json(
        ASSET_LIBRARY_FILE,
        [library.to_record() for library in asset_libraries],
        what="asset libraries",
    )


def load() -> List[dict]:
    """Return the persisted asset-library records."""
    return [
        record
        for record in jsonstore.read_json(ASSET_LIBRARY_FILE, what="asset-library")
        if record.get("name")
    ]
