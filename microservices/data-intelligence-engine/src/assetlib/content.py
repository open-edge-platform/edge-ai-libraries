# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
from typing import Any, Mapping, Optional

from assetlib.contracts import Source
from databasehub.models import ObjectCollection

BLOB_PREFIX = "blobs"
ASSET_PREFIX = "assets"


def blob_key(data: bytes) -> str:
    """The content-addressed key for these bytes; shared blobs are never deleted per asset."""
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
        """Store bytes under their content address (idempotent) and return the key."""
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
