# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import List

import config, jsonstore

ASSET_LIBRARY_FILE = config.ASSET_LIBRARY_FILE


def save(asset_libraries: List) -> bool:
    """Rewrite the workspace's asset-library file atomically; callers serialize writes."""
    return jsonstore.write_json(
        ASSET_LIBRARY_FILE,
        [library.to_record() for library in asset_libraries],
        what="asset libraries",
    )


def load() -> List[dict]:
    return [
        record
        for record in jsonstore.read_json(ASSET_LIBRARY_FILE, what="asset-library")
        if record.get("name")
    ]
