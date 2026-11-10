# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""JSON persistence for database registrations; credentials are stored in clear text."""

from typing import List

import config, jsonstore

DATABASE_FILE = config.DATABASE_FILE


def save(database_manager) -> bool:
    """Rewrite the workspace's database file atomically."""
    return jsonstore.write_json(
        DATABASE_FILE, database_manager.to_records(), what="databases"
    )


def load() -> List[dict]:
    """Return the persisted database records."""
    return [
        record
        for record in jsonstore.read_json(DATABASE_FILE, what="database")
        if record.get("database_id")
    ]
