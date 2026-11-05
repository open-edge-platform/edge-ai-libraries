# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Database adapter contracts.

One adapter per database category defines the whole boundary between the engine
and that backend: collection-locator arguments, connection ownership, and no
vendor types in the signatures. Concrete backends live in sibling modules and
are imported directly by `databasehub/manager.py`, which is the only thing that
constructs them -- so they are not re-exported here.
"""

from databasehub.adapters.graph import GraphAdapter
from databasehub.adapters.object import ObjectAdapter, ObjectData
from databasehub.adapters.sql import SqlAdapter
from databasehub.adapters.vector import VectorAdapter

__all__ = [
    "GraphAdapter",
    "ObjectAdapter",
    "ObjectData",
    "SqlAdapter",
    "VectorAdapter",
]
