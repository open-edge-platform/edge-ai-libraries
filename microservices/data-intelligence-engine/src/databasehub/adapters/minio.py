# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""MinIO adapter placeholder."""

from typing import List, Mapping, Optional

from databasehub.adapters.object import ObjectAdapter, ObjectData
from databasehub.models import ObjectCollection


class MinioAdapter(ObjectAdapter):
    """Operate buckets and prefixes through one MinIO connection."""

    def __init__(self, options: Mapping[str, object]):
        self._options = dict(options)

    @staticmethod
    def _unavailable():
        raise NotImplementedError("MinIO backend integration is not implemented")

    def ensure(self, collection: ObjectCollection) -> None:
        self._unavailable()

    def exists(self, collection: ObjectCollection, key: str) -> bool:
        self._unavailable()

    def put(
        self,
        collection: ObjectCollection,
        key: str,
        data: ObjectData,
        content_type: Optional[str] = None,
    ) -> None:
        self._unavailable()

    def get(self, collection: ObjectCollection, key: str) -> bytes:
        self._unavailable()

    def delete(self, collection: ObjectCollection, key: str) -> None:
        self._unavailable()

    def list(self, collection: ObjectCollection, prefix: str = "") -> List[str]:
        self._unavailable()

    def clear(self, collection: ObjectCollection) -> None:
        self._unavailable()

    def ping(self) -> None:
        """Unreachable by construction: this backend is not implemented.

        Inherited, the default would report the connection healthy -- which
        would be a lie an operator only discovers when the first MinIO
        write fails, long after the check said it was fine.
        """
        self._unavailable()

    def close(self) -> None:
        pass