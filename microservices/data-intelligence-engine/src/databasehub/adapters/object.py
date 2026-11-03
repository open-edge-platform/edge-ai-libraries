# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The object-storage backend contract: one adapter owns one connection."""

from abc import ABC, abstractmethod
from typing import BinaryIO, List, Optional, Union

from databasehub.models import ObjectCollection

ObjectData = Union[bytes, BinaryIO]


class ObjectAdapter(ABC):
    """Connection-owning contract for an object-storage backend.

    Every method names the bucket and prefix it acts on. See
    `adapters/vector.py:VectorAdapter` for why this is an ABC here rather than a
    Protocol paired with an operator class.

    This is also where **asset content** lives -- the bytes an asset is made of,
    as opposed to the records a projection derives from them. A source of type
    `object` is a real source like any other: registered on the library, listed
    by the API, reached through an adapter. What makes it different is only who
    references it -- an asset, rather than a pool -- so it is never a projection
    target (`PROJECTION_TYPES` has no entry for it, by design).
    """

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
        """Raise if the backend is not reachable; return if it is.

        Concrete, and doing nothing is a truthful default for a backend whose
        constructor already dialled -- `check` builds the adapter first, so
        getting this far means the connection was established. A backend that
        connects lazily, or that can be reached but not used, overrides this
        with the cheapest real round trip it has.
        """
