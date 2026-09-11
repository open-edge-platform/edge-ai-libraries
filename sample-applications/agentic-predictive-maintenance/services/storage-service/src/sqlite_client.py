# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
SQLite client for persisting and querying defect detections.
"""

import sqlite3
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id  INTEGER NOT NULL,
    label     TEXT    NOT NULL,
    confidence REAL   NOT NULL,
    x         REAL    NOT NULL,
    y         REAL    NOT NULL,
    width     REAL    NOT NULL,
    height    REAL    NOT NULL,
    timestamp TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_frame_id   ON detections(frame_id);
CREATE INDEX IF NOT EXISTS idx_label      ON detections(label);
CREATE INDEX IF NOT EXISTS idx_confidence ON detections(confidence);
"""


class SQLiteClient:
    """Thread-safe SQLite client for detection persistence."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True) if os.path.dirname(db_path) else None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript(SCHEMA)
        logger.info("Database initialised at %s", self.db_path)

    def insert_detection(self, frame_id: int, label: str, confidence: float,
                         x: float, y: float, width: float, height: float) -> int:
        sql = """INSERT INTO detections (frame_id, label, confidence, x, y, width, height)
                 VALUES (?, ?, ?, ?, ?, ?, ?)"""
        with self._get_conn() as conn:
            cursor = conn.execute(sql, (frame_id, label, confidence, x, y, width, height))
            return cursor.lastrowid

    def insert_many(self, records: list[dict]) -> int:
        """Bulk insert detections. Each dict must have frame_id, label, confidence, x, y, width, height."""
        sql = """INSERT INTO detections (frame_id, label, confidence, x, y, width, height)
                 VALUES (:frame_id, :label, :confidence, :x, :y, :width, :height)"""
        with self._get_conn() as conn:
            conn.executemany(sql, records)
            return len(records)

    def get_detections(self, label: Optional[str] = None,
                       min_confidence: Optional[float] = None,
                       limit: Optional[int] = None) -> list[dict]:
        conditions = []
        params: list = []
        if label:
            conditions.append("label = ?")
            params.append(label)
        if min_confidence is not None:
            conditions.append("confidence >= ?")
            params.append(min_confidence)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit_clause = f"LIMIT {int(limit)}" if limit else ""
        sql = f"SELECT * FROM detections {where} ORDER BY confidence DESC {limit_clause}"

        with self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_summary(self) -> dict:
        """Return per-class detection counts and confidence stats."""
        sql = """
        SELECT label,
               COUNT(*)          AS count,
               AVG(confidence)   AS avg_confidence,
               MAX(confidence)   AS max_confidence,
               MIN(confidence)   AS min_confidence
        FROM detections
        GROUP BY label
        ORDER BY count DESC
        """
        with self._get_conn() as conn:
            rows = conn.execute(sql).fetchall()
        return {"by_class": [dict(r) for r in rows]}

    def count(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]

    def clear(self):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM detections")
        logger.info("Cleared all detections from database")
