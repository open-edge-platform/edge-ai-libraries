# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Asset content: the bytes an asset is made of, in the source that holds them.

An asset's content lives in a `Source` like anything else -- registered on the
library, listed by the API, reached through a `databasehub` adapter. The only
thing that distinguishes it from a pool's source is who points at it: an asset,
not a pool. So there is no separate storage abstraction here, just the seam that
turns (source, key) into bytes.

Two key shapes, and the store stays dumb about which is which:

- **blobs** -- immutable bytes, keyed by content: ``blobs/<sha256>``. Identical
  bytes ingested twice land on one key, which is why a blob is never deleted
  when one asset stops referring to it (another may still). Reclaim with a sweep
  over live keys instead.
- **documents** -- an asset's own record, keyed by identity:
  ``assets/<asset_id>.json``. Re-extracting the same asset overwrites it.
"""

import hashlib
import json
from typing import Any, Mapping, Optional

from assetlib.contracts import Source
from databasehub.models import ObjectCollection

BLOB_PREFIX = "blobs"
ASSET_PREFIX = "assets"


def blob_key(data: bytes) -> str:
    """The content-addressed key for these bytes."""
    return f"{BLOB_PREFIX}/{hashlib.sha256(data).hexdigest()}"


def asset_key(asset_id: str) -> str:
    return f"{ASSET_PREFIX}/{asset_id}.json"


class ContentStore:
    """Read and write asset content through the source that holds it."""

    def __init__(self, databasehub):
        self._databasehub = databasehub

    # --- resolution -----------------------------------------------------------

    def _bind(self, source: Source):
        if source.source_type.lower() != "object":
            raise TypeError(
                f"Source {source.source_id!r} is a {source.source_type!r} source; "
                "asset content needs an 'object' source"
            )
        adapter = self._databasehub.get_object_adapter(source.database_id)
        location = source.location
        if not isinstance(location, ObjectCollection):
            raise TypeError(
                f"Source {source.source_id!r} does not locate an object collection"
            )
        return adapter, location

    # --- bytes ----------------------------------------------------------------

    def put_blob(
        self, source: Source, data: bytes, content_type: Optional[str] = None
    ) -> str:
        """Store bytes under their content address and return the key.

        Idempotent: the same bytes produce the same key, and a key that is
        already present is not rewritten.
        """
        adapter, collection = self._bind(source)
        key = blob_key(data)
        adapter.ensure(collection)
        if not adapter.exists(collection, key):
            adapter.put(collection, key, data, content_type)
        return key

    def get_blob(self, source: Source, key: str) -> bytes:
        adapter, collection = self._bind(source)
        return adapter.get(collection, key)

    def exists(self, source: Source, key: str) -> bool:
        adapter, collection = self._bind(source)
        return adapter.exists(collection, key)

    # --- records --------------------------------------------------------------

    def put_record(self, source: Source, key: str, record: Mapping[str, Any]) -> str:
        adapter, collection = self._bind(source)
        adapter.ensure(collection)
        payload = json.dumps(record, ensure_ascii=False).encode("utf-8")
        adapter.put(collection, key, payload, "application/json")
        return key

    def get_record(self, source: Source, key: str) -> dict:
        return json.loads(self.get_blob(source, key).decode("utf-8"))

    def delete(self, source: Source, key: str) -> None:
        adapter, collection = self._bind(source)
        adapter.delete(collection, key)

    def live_keys(self, source: Source) -> set:
        """Every key the source holds -- one half of a sweep for orphans."""
        adapter, collection = self._bind(source)
        return set(adapter.list(collection))
