# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""JSON persistence for the registered database connections.

Separate from `configs/asset_library.json` and restored **before** it, because a
library's sources name a `database_id` and the databases have to exist by then.

Credentials are written here in the clear, like any other connection file. They
are redacted on the way out of the API (`DatabaseRegistration.redacted`), so
`configs/databases.json` is the only place they appear -- protect it the way you
would protect any other file holding a database password.
"""

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
