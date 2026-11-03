# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL adapter placeholder."""

from typing import Any, Dict, List, Mapping, Sequence

from databasehub.adapters.sql import SqlAdapter
from databasehub.models import SqlCollection


class PostgresAdapter(SqlAdapter):
    """Operate SQL collections through one PostgreSQL connection."""

    def __init__(self, options: Mapping[str, object]):
        self._options = dict(options)

    @staticmethod
    def _unavailable():
        raise NotImplementedError("PostgreSQL backend integration is not implemented")

    def execute(
        self, collection: SqlCollection, statement: str, parameters: Sequence[Any] = ()
    ) -> int:
        self._unavailable()

    def fetch_all(
        self, collection: SqlCollection, statement: str, parameters: Sequence[Any] = ()
    ) -> List[Dict[str, Any]]:
        self._unavailable()

    def clear(self, collection: SqlCollection) -> None:
        self._unavailable()

    def ping(self) -> None:
        """Unreachable by construction: this backend is not implemented.

        Inherited, the default would report the connection healthy -- which
        would be a lie an operator only discovers when the first PostgreSQL
        write fails, long after the check said it was fine.
        """
        self._unavailable()

    def close(self) -> None:
        pass