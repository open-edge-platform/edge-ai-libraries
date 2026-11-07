# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The engine's asset libraries, kept by name and id.

A thin registry over `FileAssetLibrary`: it owns the set of asset libraries
and their lifecycle (create / look up / delete / persist), and nothing else.
The API layer resolves one here and then calls it, so every operation names an
asset library and there is no implicit active-library state.

The set is persisted in the workspace (core/repository.py). `create` and `delete`
save on their own; a handler that changes an asset library's state (ingest,
metadata update, file removal) calls `registry.save()` afterwards.

`registry` is the process-wide instance the API layer uses.

Two things write here at once: the request handlers (on the event loop) and the
`BackgroundTasks` that sync an asset pool (on a worker thread). `lock` -- a
reentrant lock held around every mutation of the set and around each save -- keeps
them from interleaving into the same file or losing a read-modify-write on a
library's own counters. A handler that mutates an asset library directly
should hold it too; keep the critical section short, and never load, embed, or
index inside it.
"""

import threading
from typing import List, Optional

from core import repository
from core.file_asset_library import FileAssetLibrary
from schemas import CollectionInfo


class AssetLibraryManager:
    def __init__(self):
        self._libraries: List[FileAssetLibrary] = []
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        """Guard for read-modify-write sequences on the set or its members."""
        return self._lock

    def list(self) -> List[FileAssetLibrary]:
        with self._lock:
            return list(self._libraries)

    def get(self, key: str) -> Optional[FileAssetLibrary]:
        """The asset library with this name or id, if there is one."""
        with self._lock:
            return next(
                (library for library in self._libraries if library.matches(key)),
                None,
            )

    def require(self, key: str) -> FileAssetLibrary:
        """The asset library with this name or id; raise if it does not exist."""
        library = self.get(key)
        if library is None:
            raise ValueError(f"Asset library '{key}' not found")
        return library

    def create(self, **kwargs) -> FileAssetLibrary:
        name = kwargs.get("name")
        # Check and insert under one lock: two concurrent creates of the same
        # name must not both pass the check.
        with self._lock:
            if self.get(name) is not None:
                raise ValueError(f"Asset library '{name}' already exists")
            library = FileAssetLibrary(**kwargs)
            self._libraries.append(library)
            self.save()
        return library

    def delete(self, key: str) -> bool:
        with self._lock:
            library = self.get(key)
            if library is None:
                return False
            self._libraries.remove(library)
            self.save()
        return True

    # --- persistence ----------------------------------------------------------

    def save(self) -> bool:
        """Write the current set of asset libraries to the workspace.

        The records are built under the lock, so a save never snapshots a set
        that another writer is halfway through changing.
        """
        with self._lock:
            return repository.save(self._libraries)

    def restore(self) -> List[str]:
        """Rebuild the asset libraries persisted in the workspace.

        Every asset library is rebuilt, then each persisted source is reconciled
        independently with its existing collection. A failed source is reported
        without preventing the library or its other sources from restoring.
        Returns the names restored.
        """
        restored = []
        for record in repository.load():
            if self.get(record["name"]) is not None:
                continue
            try:
                library = FileAssetLibrary.from_record(record)
            except Exception as error:  # noqa: BLE001 - isolate invalid records
                print(f"Skipping asset library '{record['name']}': {error}")
                continue
            with self._lock:
                self._libraries.append(library)
            for source_id, error in library.source_reconciliation_errors.items():
                print(
                    f"Could not reconcile source {source_id!r} for asset library "
                    f"{record['name']!r}: {error}"
                )
            restored.append(record["name"])
        return restored

    # --- reporting ------------------------------------------------------------

    def collections(self) -> List[CollectionInfo]:
        return [
            collection
            for library in self.list()
            for collection in library.collection_infos()
        ]


registry = AssetLibraryManager()
