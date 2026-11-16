# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
import tempfile
from typing import List, Mapping, Optional

from databasehub.adapters.object import ObjectAdapter, ObjectData
from databasehub.models import ObjectCollection


class FilesystemObjectAdapter(ObjectAdapter):
    """Buckets as directories under one root."""

    def __init__(self, options: Mapping[str, object]):
        self._options = dict(options)
        root = self._options.get("root")
        if not root:
            raise ValueError("The filesystem object backend needs a 'root' directory")
        self._root = os.path.abspath(str(root))

    def _bucket_dir(self, collection: ObjectCollection) -> str:
        if not collection.bucket:
            raise ValueError("An object collection needs a bucket")
        return self._resolve(self._root, collection.bucket)

    def _path(self, collection: ObjectCollection, key: str) -> str:
        if not key:
            raise ValueError("An object key cannot be empty")
        relative = f"{collection.prefix}/{key}" if collection.prefix else key
        return self._resolve(self._bucket_dir(collection), relative)

    @staticmethod
    def _resolve(base: str, relative: str) -> str:
        """Join, and refuse anything that escapes `base`."""
        candidate = os.path.abspath(os.path.join(base, relative))
        if candidate != base and not candidate.startswith(base + os.sep):
            raise ValueError(f"Object key escapes its bucket: {relative!r}")
        return candidate

    def ensure(self, collection: ObjectCollection) -> None:
        os.makedirs(self._bucket_dir(collection), exist_ok=True)

    def exists(self, collection: ObjectCollection, key: str) -> bool:
        return os.path.isfile(self._path(collection, key))

    def put(
        self,
        collection: ObjectCollection,
        key: str,
        data: ObjectData,
        content_type: Optional[str] = None,
    ) -> None:
        """Write atomically: a reader sees either the old bytes or the new."""
        path = self._path(collection, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = data if isinstance(data, bytes) else data.read()
        descriptor, temporary = tempfile.mkstemp(
            dir=os.path.dirname(path), prefix=".put.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def get(self, collection: ObjectCollection, key: str) -> bytes:
        path = self._path(collection, key)
        try:
            with open(path, "rb") as file:
                return file.read()
        except FileNotFoundError as error:
            raise KeyError(key) from error

    def delete(self, collection: ObjectCollection, key: str) -> None:
        try:
            os.unlink(self._path(collection, key))
        except FileNotFoundError:
            pass

    def list(self, collection: ObjectCollection, prefix: str = "") -> List[str]:
        """Keys under `prefix`, relative to the collection, sorted."""
        base = self._bucket_dir(collection)
        start = self._path(collection, prefix) if prefix else (
            self._resolve(base, collection.prefix) if collection.prefix else base
        )
        if os.path.isfile(start):
            start_dir, only = os.path.dirname(start), os.path.basename(start)
        else:
            start_dir, only = start, None
        scope = self._resolve(base, collection.prefix) if collection.prefix else base
        keys = []
        for directory, _, files in os.walk(start_dir):
            for name in files:
                if name.startswith(".put."):
                    continue  # an interrupted put
                if only is not None and name != only:
                    continue
                keys.append(
                    os.path.relpath(os.path.join(directory, name), scope).replace(
                        os.sep, "/"
                    )
                )
        return sorted(keys)

    def clear(self, collection: ObjectCollection) -> None:
        target = (
            self._resolve(self._bucket_dir(collection), collection.prefix)
            if collection.prefix
            else self._bucket_dir(collection)
        )
        shutil.rmtree(target, ignore_errors=True)

    def ping(self) -> None:
        """Create the root if missing and check it is writable."""
        os.makedirs(self._root, exist_ok=True)
        if not os.access(self._root, os.W_OK | os.X_OK):
            raise PermissionError(f"Object root {self._root!r} is not writable")

    def close(self) -> None:
        ...
