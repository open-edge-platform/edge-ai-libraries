# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import config
from databasehub.adapters.filesystem import FilesystemObjectAdapter
from databasehub.adapters.graph import GraphAdapter
from databasehub.adapters.milvus import MilvusAdapter
from databasehub.adapters.nebula import NebulaAdapter
from databasehub.adapters.object import ObjectAdapter
from databasehub.adapters.sql import SqlAdapter
from databasehub.adapters.vector import VectorAdapter

DatabaseAdapter = VectorAdapter | SqlAdapter | GraphAdapter | ObjectAdapter

BACKENDS: Dict[Tuple[str, str], Callable[[Mapping[str, object]], DatabaseAdapter]] = {
    ("vector", "milvus"): MilvusAdapter,
    ("graph", "nebula"): NebulaAdapter,
    ("object", "filesystem"): FilesystemObjectAdapter,
}

#: Option keys persisted but redacted when returned over the API.
SECRET_OPTION_KEYS = frozenset(
    {"password", "secret_key", "token", "api_key", "secret", "dsn"}
)
REDACTED = "***"

#: Filesystem object database at `config.CONTENT_DIR`, auto-registered for asset content.
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

    SUPPORTED_BACKENDS: Dict[str, set] = {}
    for _database_type, _backend in BACKENDS:
        SUPPORTED_BACKENDS.setdefault(_database_type, set()).add(_backend)
    del _database_type, _backend

    def __init__(self):
        self._registrations: Dict[str, DatabaseRegistration] = {}
        self._adapters: Dict[str, DatabaseAdapter] = {}
        #: Persists registrations made by `ensure_content_database`; set by the service entrypoint.
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
        """Record a database the engine may connect to; nothing is dialled until first use."""
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

        The type cannot change. Options are replaced wholesale, but omitted or redacted secrets are kept.
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

    get_registration = require

    def get(self, database_id: str) -> Optional[DatabaseRegistration]:
        return self._registrations.get(database_id)

    def list_databases(self) -> List[DatabaseRegistration]:
        return list(self._registrations.values())

    def databases_of_type(self, database_type: str) -> List[DatabaseRegistration]:
        """Every registered database of one category, in registration order."""
        database_type = database_type.lower()
        return [
            registration
            for registration in self._registrations.values()
            if registration.database_type == database_type
        ]

    def ensure_content_database(self) -> str:
        """Register the workspace object store if absent and return its id; never repoints an existing one."""
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
        """Ping the backend and return `(ok, error)`; a failed check drops the cached adapter."""
        try:
            self.get_adapter(database_id).ping()
        except Exception as error:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
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
        """Rebuild the registrations, skipping each invalid record individually."""
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
            except Exception as error:  # noqa: BLE001
                print(
                    "Skipping database "
                    f"{record.get('database_id', '<unnamed>')!r}: {error}"
                )
                continue
            restored.append(registration.database_id)
        return restored


database_manager = DatabaseHubManager()
