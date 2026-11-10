# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod
from typing import BinaryIO, List, Optional, Union

from databasehub.models import ObjectCollection

ObjectData = Union[bytes, BinaryIO]


class ObjectAdapter(ABC):
    """Connection-owning contract for an object-storage backend; holds asset content."""

    @abstractmethod
    def ensure(self, collection: ObjectCollection) -> None:
        """Make `collection` usable, creating it if the backend allows."""

    @abstractmethod
    def exists(self, collection: ObjectCollection, key: str) -> bool: ...

    @abstractmethod
    def put(
        self,
        collection: ObjectCollection,
        key: str,
        data: ObjectData,
        content_type: Optional[str] = None,
    ) -> None: ...

    @abstractmethod
    def get(self, collection: ObjectCollection, key: str) -> bytes:
        """The bytes stored under `key`, or `KeyError` if there are none."""

    @abstractmethod
    def delete(self, collection: ObjectCollection, key: str) -> None: ...

    @abstractmethod
    def list(self, collection: ObjectCollection, prefix: str = "") -> List[str]: ...

    @abstractmethod
    def clear(self, collection: ObjectCollection) -> None: ...

    @abstractmethod
    def close(self) -> None:
        """Release the backend clients this adapter holds."""

    # --- liveness -------------------------------------------------------------

    def ping(self) -> None:
        """Raise if the backend is not reachable; no-op for backends that connect in the constructor."""
