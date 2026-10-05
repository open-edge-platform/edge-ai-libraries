# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Persistence for the live-stream registry.

The registry is the service's control-plane state: it must survive a restart so
that streams a caller registered are brought back automatically. It is kept
behind :class:`LiveStreamStore` so the backing technology is an implementation
detail.

Two implementations ship here:

* :class:`SqliteLiveStreamStore` — the default. Writes a single SQLite file on
  the existing dataprep volume (no new volume is introduced). SQLite is
  transactional, needs no extra dependency, and gives atomic read-modify-write,
  which an object store cannot.
* :class:`InMemoryLiveStreamStore` — used by tests and by deployments that
  explicitly opt out of persistence.

A future Redis (or other shared) backend only has to implement the same five
methods and register itself with :func:`register_store_backend`; nothing else in
the service talks to the storage layer directly.

.. note::
   The credentialed source URL is persisted here because reconnecting after a
   restart requires it. The database file is created with ``0600`` permissions
   and every other boundary (API, vector metadata, logs) sees only the redacted
   URL. See :mod:`src.core.live.urls`.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Dict, List, Optional, Type

from src.common import logger, sanitize_for_log, settings
from src.core.live.models import LiveStream

_SCHEMA = """
CREATE TABLE IF NOT EXISTS live_streams (
    stream_id   TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    created_ts  REAL NOT NULL,
    updated_ts  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_live_streams_created ON live_streams (created_ts);
"""


class LiveStreamStore(ABC):
    """Contract every live-stream registry backend implements."""

    @abstractmethod
    def initialize(self) -> None:
        """Prepare the backing store (create schema, open connections)."""

    @abstractmethod
    def upsert(self, stream: LiveStream) -> None:
        """Insert or replace ``stream``."""

    @abstractmethod
    def get(self, stream_id: str) -> Optional[LiveStream]:
        """Return the stream with ``stream_id``, or ``None``."""

    @abstractmethod
    def list(self) -> List[LiveStream]:
        """Return every registered stream, oldest registration first."""

    @abstractmethod
    def delete(self, stream_id: str) -> bool:
        """Remove ``stream_id``. Returns ``True`` when a record was removed."""

    @abstractmethod
    def clear(self) -> None:
        """Remove every record (test/reset helper)."""


class InMemoryLiveStreamStore(LiveStreamStore):
    """Non-persistent registry backend. Registrations are lost on restart."""

    def __init__(self) -> None:
        self._rows: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def initialize(self) -> None:
        """No-op; nothing to prepare."""

    def upsert(self, stream: LiveStream) -> None:
        """Store a snapshot of ``stream`` so later mutations do not alias it."""
        with self._lock:
            self._rows[stream.stream_id] = stream.to_row()

    def get(self, stream_id: str) -> Optional[LiveStream]:
        """Return a detached copy of the stored record."""
        with self._lock:
            row = self._rows.get(stream_id)
        return LiveStream.from_row(row) if row else None

    def list(self) -> List[LiveStream]:
        """Return detached copies of every record, oldest first."""
        with self._lock:
            rows = list(self._rows.values())
        rows.sort(key=lambda r: r.get("created_ts") or 0.0)
        return [LiveStream.from_row(row) for row in rows]

    def delete(self, stream_id: str) -> bool:
        """Remove a record if present."""
        with self._lock:
            return self._rows.pop(stream_id, None) is not None

    def clear(self) -> None:
        """Drop every record."""
        with self._lock:
            self._rows.clear()


class SqliteLiveStreamStore(LiveStreamStore):
    """SQLite-backed registry stored on the existing dataprep volume."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = Path(db_path or settings.LIVE_STREAM_STATE_PATH)
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def db_path(self) -> Path:
        """Filesystem location of the SQLite database."""
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        """Open a short-lived connection with sane durability settings."""
        conn = sqlite3.connect(str(self._db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def initialize(self) -> None:
        """Create the parent directory, the schema, and restrict file perms."""
        with self._lock:
            if self._initialized:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
            # The credentialed stream URLs live in this file; keep it owner-only.
            try:
                os.chmod(self._db_path, 0o600)
            except OSError as exc:
                logger.warning(
                    "Could not restrict permissions on the live-stream registry file: %s",
                    sanitize_for_log(str(exc), max_length=256),
                )
            self._initialized = True
            logger.info("Live-stream registry ready at %s", self._db_path)

    def upsert(self, stream: LiveStream) -> None:
        """Insert or replace ``stream`` atomically."""
        self.initialize()
        row = stream.to_row()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO live_streams (stream_id, payload, created_ts, updated_ts) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(stream_id) DO UPDATE SET "
                "payload=excluded.payload, updated_ts=excluded.updated_ts",
                (
                    stream.stream_id,
                    json.dumps(row),
                    stream.created_ts,
                    stream.updated_ts,
                ),
            )

    def get(self, stream_id: str) -> Optional[LiveStream]:
        """Return the stored record for ``stream_id``, or ``None``."""
        self.initialize()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "SELECT payload FROM live_streams WHERE stream_id = ?", (stream_id,)
            )
            row = cursor.fetchone()
        if not row:
            return None
        return self._decode(row[0], stream_id)

    def list(self) -> List[LiveStream]:
        """Return every stored record, oldest registration first."""
        self.initialize()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "SELECT stream_id, payload FROM live_streams ORDER BY created_ts ASC"
            )
            rows = cursor.fetchall()
        streams: List[LiveStream] = []
        for stream_id, payload in rows:
            decoded = self._decode(payload, stream_id)
            if decoded is not None:
                streams.append(decoded)
        return streams

    def delete(self, stream_id: str) -> bool:
        """Remove ``stream_id`` if present."""
        self.initialize()
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM live_streams WHERE stream_id = ?", (stream_id,))
            return cursor.rowcount > 0

    def clear(self) -> None:
        """Delete every stored record."""
        self.initialize()
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM live_streams")

    @staticmethod
    def _decode(payload: str, stream_id: str) -> Optional[LiveStream]:
        """Decode a persisted payload, skipping (and logging) corrupt rows."""
        try:
            return LiveStream.from_row(json.loads(payload))
        except Exception as exc:  # noqa: BLE001 - one bad row must not break listing
            logger.error(
                "Skipping unreadable live-stream record %s: %s",
                sanitize_for_log(stream_id, max_length=64),
                sanitize_for_log(str(exc), max_length=256),
            )
            return None


_BACKENDS: Dict[str, Callable[[], LiveStreamStore]] = {
    "sqlite": SqliteLiveStreamStore,
    "memory": InMemoryLiveStreamStore,
}

_store: Optional[LiveStreamStore] = None
_store_lock = threading.Lock()


def register_store_backend(name: str, factory: Callable[[], LiveStreamStore]) -> None:
    """Register an additional registry backend (e.g. a future Redis store)."""
    _BACKENDS[name.strip().lower()] = factory


def get_live_stream_store() -> LiveStreamStore:
    """Return the process-wide registry store, creating it on first use."""
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is None:
            store = SqliteLiveStreamStore()
            store.initialize()
            _store = store
    return _store


def set_live_stream_store(store: Optional[LiveStreamStore]) -> None:
    """Override the process-wide store (used by tests and alternate backends)."""
    global _store
    with _store_lock:
        if store is not None:
            store.initialize()
        _store = store


def reset_live_stream_store() -> None:
    """Drop the cached store so the next call rebuilds it."""
    set_live_stream_store(None)


__all__ = [
    "LiveStreamStore",
    "InMemoryLiveStreamStore",
    "SqliteLiveStreamStore",
    "get_live_stream_store",
    "set_live_stream_store",
    "reset_live_stream_store",
    "register_store_backend",
]


def _store_backend_names() -> List[str]:
    """Return the registered backend names (introspection helper)."""
    return sorted(_BACKENDS)


def get_store_backend(name: str) -> Type[LiveStreamStore]:
    """Return a registered backend factory by name."""
    try:
        return _BACKENDS[name.strip().lower()]
    except KeyError as exc:
        raise ValueError(
            f"Unknown live-stream store backend '{name}'. Available: {', '.join(_store_backend_names())}"
        ) from exc
