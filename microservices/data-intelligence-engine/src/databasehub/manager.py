# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The registered database connections, and the adapter that owns each one.

An adapter *is* the backend boundary (see `adapters/__init__.py`), so this hands
out adapters. There is no operator layer above them: the one it used to build
forwarded almost every call to the identically named adapter method.

**Nothing is registered at import time.** This used to read `MILVUS_URI`,
`NEBULA_URI` and the rest out of the environment in `__init__` and register four
fixed ids -- `default-vector`, `default-object` and friends. That made a
connection a deployment-time decision: pointing the engine at a different Milvus
meant editing the environment and restarting, connecting to two at once was
impossible, and there was no way to ask what the engine was connected to or
whether it worked. Connections are now runtime state like everything else --
registered over HTTP (`api/databases.py`), persisted in the workspace
(`databasehub/repository.py`), and restored *before* the asset libraries that
name them.

A consequence worth stating plainly: a fresh engine is connected to nothing, and
a source cannot be created until a database is registered.

`ensure_content_database` is the single, deliberate exception, and it is a
narrower one than it looks. It registers one object database -- a directory in
the workspace, through the filesystem backend -- the first time a library needs
somewhere to put asset content and has not been told where. Not at import, not
at startup: a fresh engine still reports nothing registered. What it buys is
that ingesting content cannot fail for want of an object store, which is
different from guessing at a connection, because the engine owns that directory
either way.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import config
from databasehub.adapters.filesystem import FilesystemObjectAdapter
from databasehub.adapters.graph import GraphAdapter
from databasehub.adapters.milvus import MilvusAdapter
from databasehub.adapters.minio import MinioAdapter
from databasehub.adapters.nebula import NebulaAdapter
from databasehub.adapters.object import ObjectAdapter
from databasehub.adapters.postgres import PostgresAdapter
from databasehub.adapters.sql import SqlAdapter
from databasehub.adapters.vector import VectorAdapter

DatabaseAdapter = VectorAdapter | SqlAdapter | GraphAdapter | ObjectAdapter

# The one place a (category, backend) pair becomes a connection. `register`
# validates against these keys, so adding a backend is a single entry.
BACKENDS: Dict[Tuple[str, str], Callable[[Mapping[str, object]], DatabaseAdapter]] = {
    ("vector", "milvus"): MilvusAdapter,
    ("graph", "nebula"): NebulaAdapter,
    ("sql", "postgres"): PostgresAdapter,
    ("object", "filesystem"): FilesystemObjectAdapter,
    ("object", "minio"): MinioAdapter,
}

#: Option keys never echoed back over the API. They are persisted -- a
#: connection that forgot its password would not reconnect -- but a GET returns
#: a placeholder, so a credential cannot leak into a log, a screenshot or a UI
#: that renders whatever it is given.
SECRET_OPTION_KEYS = frozenset(
    {"password", "secret_key", "token", "api_key", "secret", "dsn"}
)
REDACTED = "***"

#: The id of the object database the engine registers for itself to hold asset
#: content when nothing else has been registered to hold it. Not a connection
#: being guessed at -- a directory in the workspace the engine already owns
#: (`config.CONTENT_DIR`), reached through the filesystem object backend, which
#: needs no server and no credentials.
WORKSPACE_CONTENT_DATABASE = "workspace-content"


@dataclass(frozen=True)
class DatabaseRegistration:
    """One database the engine may talk to. Not a connection -- see `get_adapter`."""

    database_id: str
    database_type: str
    backend: str
    options: Mapping[str, Any]
    description: str = ""

    def to_record(self) -> dict:
        return {
            "database_id": self.database_id,
            "database_type": self.database_type,
            "backend": self.backend,
            "options": dict(self.options),
            "description": self.description,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "DatabaseRegistration":
        return cls(
            database_id=str(record["database_id"]),
            database_type=str(record["database_type"]).lower(),
            backend=str(record["backend"]).lower(),
            options=dict(record.get("options") or {}),
            description=str(record.get("description") or ""),
        )

    def redacted(self) -> dict:
        """This persisted registration shape, with credentials masked."""
        record = self.to_record()
        record["options"] = {
            key: (REDACTED if key in SECRET_OPTION_KEYS and value else value)
            for key, value in record["options"].items()
        }
        return record


class DatabaseHubManager:
    """The registered databases, and the adapter that owns each connection."""

    # Derived from BACKENDS, so a new entry there is immediately registrable and
    # there is no second list to keep in step.
    SUPPORTED_BACKENDS: Dict[str, set] = {}
    for _database_type, _backend in BACKENDS:
        SUPPORTED_BACKENDS.setdefault(_database_type, set()).add(_backend)
    del _database_type, _backend

    def __init__(self):
        self._registrations: Dict[str, DatabaseRegistration] = {}
        self._adapters: Dict[str, DatabaseAdapter] = {}
        #: Called after a registration this manager made on its own behalf, so
        #: it survives a restart. Set by the service entrypoint to write
        #: `databasehub/repository.py`; left a no-op elsewhere, which is what
        #: keeps this module free of any knowledge of where records are kept.
        #:
        #: Only `ensure_content_database` needs it. Every other registration
        #: arrives through the API, which persists on its own -- but a content
        #: database registered halfway through an ingest has no such caller.
        self.persist: Callable[[], Any] = lambda: None

    # --- registry -------------------------------------------------------------

    def register(
        self,
        database_id: str,
        database_type: str,
        backend: str,
        options: Optional[Mapping[str, Any]] = None,
        description: str = "",
        replace: bool = False,
    ) -> DatabaseRegistration:
        """Record a database the engine may connect to.

        Nothing is dialled here. The adapter is built on first use, so
        registering an unreachable database succeeds and `check` is how you find
        out -- which is the right way round: an operator should be able to write
        down a connection before the far end is up.
        """
        if not database_id:
            raise ValueError("A database needs an id")
        database_type = database_type.lower()
        backend = backend.lower()
        supported = self.SUPPORTED_BACKENDS.get(database_type)
        if supported is None:
            raise ValueError(
                f"Unsupported database type {database_type!r}; supported: "
                + ", ".join(sorted(self.SUPPORTED_BACKENDS))
            )
        if backend not in supported:
            raise ValueError(
                f"Unsupported {database_type} backend {backend!r}; supported: "
                + ", ".join(sorted(supported))
            )
        existing = self._registrations.get(database_id)
        if existing is not None and not replace:
            raise ValueError(f"Database {database_id!r} already exists")
        if existing is not None:
            self.release(database_id)
        registration = DatabaseRegistration(
            database_id=database_id,
            database_type=database_type,
            backend=backend,
            options=dict(options or {}),
            description=description,
        )
        self._registrations[database_id] = registration
        return registration

    def update(
        self,
        database_id: str,
        backend: Optional[str] = None,
        options: Optional[Mapping[str, Any]] = None,
        description: Optional[str] = None,
    ) -> DatabaseRegistration:
        """Change where a database points, closing the live connection.

        The type cannot change: sources already reference this id and were built
        against a vector or an object store, and turning one into the other
        under them would leave those sources describing something that is not
        there. Delete and re-register to do that deliberately.

        Options are replaced wholesale rather than merged, so removing a setting
        is possible -- but a secret left out is kept, since the API redacts them
        on the way out and a client that echoes a GET back would otherwise
        overwrite the real credential with `***`.
        """
        current = self.require(database_id)
        merged = dict(current.options if options is None else options)
        if options is not None:
            for key in SECRET_OPTION_KEYS:
                if merged.get(key) in (None, "", REDACTED) and current.options.get(key):
                    merged[key] = current.options[key]
        return self.register(
            database_id,
            database_type=current.database_type,
            backend=(backend or current.backend),
            options=merged,
            description=(
                current.description if description is None else description
            ),
            replace=True,
        )

    def remove(self, database_id: str) -> bool:
        """Forget a database and close its connection."""
        if database_id not in self._registrations:
            return False
        self.release(database_id)
        del self._registrations[database_id]
        return True

    def require(self, database_id: str) -> DatabaseRegistration:
        registration = self._registrations.get(database_id)
        if registration is None:
            known = ", ".join(sorted(self._registrations)) or "none registered"
            raise ValueError(
                f"Database {database_id!r} is not registered (known: {known})"
            )
        return registration

    # Kept under the old name: `create_source` and `build_projection` ask for a
    # registration, and this reads better there than `require` does.
    get_registration = require

    def get(self, database_id: str) -> Optional[DatabaseRegistration]:
        return self._registrations.get(database_id)

    def list_databases(self) -> List[DatabaseRegistration]:
        return list(self._registrations.values())

    def databases_of_type(self, database_type: str) -> List[DatabaseRegistration]:
        """Every registered database of one category, in registration order.

        `AssetLibrary.content_source` uses this to find the object store when a
        library has not named one and there is only one to find.
        """
        database_type = database_type.lower()
        return [
            registration
            for registration in self._registrations.values()
            if registration.database_type == database_type
        ]

    def ensure_content_database(self) -> str:
        """Register the workspace's own object store, if it is not already, and
        return its id.

        The one registration this manager makes on its own behalf, and the
        exception that proves the rule above: nothing is registered at import
        time or at startup, so a fresh engine still reports no databases. This
        runs only when a library actually needs somewhere to put content and has
        not been told where -- at which point "nowhere" is not a useful answer,
        and `config.CONTENT_DIR` is the answer the workspace layout has
        documented all along.

        Idempotent, and it never repoints an existing registration: an operator
        who has moved this id somewhere else keeps it.
        """
        existing = self._registrations.get(WORKSPACE_CONTENT_DATABASE)
        if existing is not None:
            return existing.database_id
        registration = self.register(
            WORKSPACE_CONTENT_DATABASE,
            database_type="object",
            backend="filesystem",
            options={"root": config.CONTENT_DIR},
            description="Asset content in the engine's workspace",
        )
        self.persist()
        return registration.database_id

    # --- connections ----------------------------------------------------------

    def get_adapter(self, database_id: str) -> DatabaseAdapter:
        """The adapter for `database_id`, connecting on first use."""
        registration = self.require(database_id)
        if database_id not in self._adapters:
            self._adapters[database_id] = self._build_adapter(registration)
        return self._adapters[database_id]

    def get_vector_adapter(self, database_id: str) -> VectorAdapter:
        adapter = self.get_adapter(database_id)
        if not isinstance(adapter, VectorAdapter):
            raise TypeError(f"Database {database_id!r} is not a vector database")
        return adapter

    def get_object_adapter(self, database_id: str) -> ObjectAdapter:
        adapter = self.get_adapter(database_id)
        if not isinstance(adapter, ObjectAdapter):
            raise TypeError(f"Database {database_id!r} is not an object store")
        return adapter

    def check(self, database_id: str) -> Tuple[bool, str]:
        """Connect and ask the backend whether it is there. `(ok, error)`.

        Reports rather than raises: "this database is unreachable" is the answer
        to the question, not a failure to answer it. A failed check drops the
        adapter, so the next attempt reconnects instead of reusing a client
        bound to a dead endpoint.
        """
        try:
            self.get_adapter(database_id).ping()
        except Exception as error:  # noqa: BLE001 - the error *is* the result
            self._adapters.pop(database_id, None)
            return False, f"{type(error).__name__}: {error}"
        return True, ""

    def release(self, database_id: str) -> bool:
        """Close the live connection, keeping the registration."""
        adapter = self._adapters.pop(database_id, None)
        if adapter is None:
            return False
        try:
            adapter.close()
        except Exception:  # noqa: BLE001 - closing must not fail a reconfigure
            pass
        return True

    def close(self) -> None:
        for database_id in list(self._adapters):
            self.release(database_id)

    @staticmethod
    def _build_adapter(registration: DatabaseRegistration) -> DatabaseAdapter:
        build = BACKENDS.get((registration.database_type, registration.backend))
        if build is None:
            raise ValueError(
                f"Unsupported {registration.database_type} backend: "
                f"{registration.backend!r}"
            )
        return build(registration.options)

    # --- persistence ----------------------------------------------------------

    def to_records(self) -> List[dict]:
        return [
            registration.to_record() for registration in self._registrations.values()
        ]

    def restore(self, records: List[Mapping[str, Any]]) -> List[str]:
        """Rebuild the registrations, reporting each bad record on its own.

        One unusable record -- a backend that no longer exists, say -- costs that
        database, not every other one and not the service starting.
        """
        restored = []
        for record in records:
            try:
                registration = DatabaseRegistration.from_record(record)
                self.register(
                    registration.database_id,
                    database_type=registration.database_type,
                    backend=registration.backend,
                    options=registration.options,
                    description=registration.description,
                    replace=True,
                )
            except Exception as error:  # noqa: BLE001 - isolate invalid records
                print(
                    "Skipping database "
                    f"{record.get('database_id', '<unnamed>')!r}: {error}"
                )
                continue
            restored.append(registration.database_id)
        return restored


database_manager = DatabaseHubManager()
