# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""SQLite `events` store written by the Router bridge and the OTLP receiver.

The layout is the one the Hermes hermes-otel plugin uses, so `observability show/disable --clean`
treat every source alike. Standard library only.
"""

import os
import sqlite3

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
    "ts INTEGER NOT NULL, data TEXT NOT NULL, trace_id TEXT, span_id TEXT, parent_span_id TEXT, "
    "session_id TEXT, name TEXT, status TEXT, start_ns INTEGER, end_ns INTEGER, duration_ms REAL, "
    "level INTEGER, logger TEXT, value REAL)"
)
INDEX = "events_span_ids"
PRUNE_EVERY = 500
# A replayed span (retried export, reset checkpoint) is ignored instead of stored twice.
INSERT_SPAN = (
    "INSERT OR IGNORE INTO events (kind, ts, data, trace_id, span_id, parent_span_id, session_id, name, status, "
    "start_ns, end_ns, duration_ms) VALUES ('span', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def open_store(path, check_same_thread=True):
    os.umask(0o077)
    con = sqlite3.connect(path, check_same_thread=check_same_thread, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(SCHEMA)
    has_index = con.execute("SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?", (INDEX,)).fetchone()
    if not has_index:
        # Stores written before span ids were unique may hold replayed duplicates; keep the first of each.
        con.execute(
            "DELETE FROM events WHERE kind = 'span' AND span_id <> '' AND seq NOT IN "
            "(SELECT MIN(seq) FROM events WHERE kind = 'span' AND span_id <> '' GROUP BY trace_id, span_id)")
        con.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} ON events (trace_id, span_id) "
            "WHERE kind = 'span' AND span_id <> ''")
    con.commit()
    return con


def prune(con, max_rows):
    """Keeps the newest `max_rows` rows; the caller commits."""
    con.execute("DELETE FROM events WHERE seq <= (SELECT MAX(seq) FROM events) - ?", (max_rows,))
