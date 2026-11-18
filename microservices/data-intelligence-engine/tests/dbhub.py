# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A real `DatabaseHubManager` for tests that need one.

The suites used to hand libraries a hand-written stub with `get_registration`
and `get_adapter` on it. That was fine while the hub had two methods; now that
registering a database is a real operation with real rules -- one type per id,
no unknown backends, resolution when a library has not chosen a content store --
a stub would only assert that the stub agrees with itself.

So these build the actual manager against a temporary directory. Nothing here
reaches the network: the filesystem object backend needs no server, which is
what makes it usable as the default in tests and in a bare deployment alike.
"""

import tempfile

from databasehub.manager import DatabaseHubManager

OBJECT_DATABASE = "test-content"
VECTOR_DATABASE = "test-vectors"


def object_hub(database_id: str = OBJECT_DATABASE, root: str = "") -> DatabaseHubManager:
    """A hub with one filesystem object database, rooted in a temp directory."""
    hub = DatabaseHubManager()
    hub.register(
        database_id,
        database_type="object",
        backend="filesystem",
        options={"root": root or tempfile.mkdtemp()},
    )
    return hub


def with_vector(hub: DatabaseHubManager, database_id: str = VECTOR_DATABASE):
    """Add a vector database. Registering one dials nothing, so no Milvus is
    needed until something actually builds its adapter."""
    hub.register(
        database_id,
        database_type="vector",
        backend="milvus",
        options={"uri": "http://milvus.invalid:19530"},
    )
    return hub


GRAPH_DATABASE = "test-graph"


def with_graph(hub: DatabaseHubManager, database_id: str = GRAPH_DATABASE):
    """Add a graph database. Like the vector one, registering dials nothing."""
    hub.register(
        database_id,
        database_type="graph",
        backend="nebula",
        options={"url": "nebula://nebula.invalid:9669"},
    )
    return hub
