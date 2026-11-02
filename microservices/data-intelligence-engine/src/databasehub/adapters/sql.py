# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The SQL backend contract: one adapter owns one connection."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence

from databasehub.models import SqlCollection


class SqlAdapter(ABC):
    """Connection-owning contract for a SQL backend.

    Every method names the table it acts on, and statements are parameterized.
    See `adapters/vector.py:VectorAdapter` for why this is an ABC here rather
    than a Protocol paired with an operator class.
    """

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
        """Raise if the backend is not reachable; return if it is.

        Concrete, and doing nothing is a truthful default for a backend whose
        constructor already dialled -- `check` builds the adapter first, so
        getting this far means the connection was established. A backend that
        connects lazily, or that can be reached but not used, overrides this
        with the cheapest real round trip it has.
        """
