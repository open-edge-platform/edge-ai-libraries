# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence

from databasehub.models import SqlCollection


class SqlAdapter(ABC):
    """Connection-owning contract for a SQL backend; statements are parameterized."""

    @abstractmethod
    def execute(
        self,
        collection: SqlCollection,
        statement: str,
        parameters: Sequence[Any] = (),
    ) -> int: ...

    @abstractmethod
    def fetch_all(
        self,
        collection: SqlCollection,
        statement: str,
        parameters: Sequence[Any] = (),
    ) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def clear(self, collection: SqlCollection) -> None: ...

    @abstractmethod
    def close(self) -> None:
        """Release the backend clients this adapter holds."""

    # --- liveness -------------------------------------------------------------

    def ping(self) -> None:
        """Raise if the backend is not reachable; no-op by default for eagerly connected backends."""
