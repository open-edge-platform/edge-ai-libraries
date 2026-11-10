# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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
        """Guard for read-modify-write on the set or its members; never load or embed while holding it."""
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
        # Check and insert under one lock so concurrent creates cannot both pass.
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

    def purge(self, key: str) -> bool:
        library = self.get(key)
        if library is None:
            return False
        try:
            library.delete_all()
        except Exception:
            self.save()
            raise
        with self._lock:
            if library in self._libraries:
                self._libraries.remove(library)
            self.save()
        return True

    # --- persistence ----------------------------------------------------------

    def save(self) -> bool:
        """Write the current set of asset libraries to the workspace."""
        with self._lock:
            return repository.save(self._libraries)

    def restore(self) -> List[str]:
        """Rebuild the persisted asset libraries and return the names restored."""
        restored = []
        for record in repository.load():
            if self.get(record["name"]) is not None:
                continue
            try:
                library = FileAssetLibrary.from_record(record)
            except Exception as error:  # noqa: BLE001
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
