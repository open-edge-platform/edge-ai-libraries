# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
from typing import Any, Dict, List, Mapping
from urllib.parse import urlparse

import config as engine_config
from databasehub.adapters.graph import GraphAdapter
from databasehub.models import GraphCollection
from llama_index.core.graph_stores.types import EntityNode, Relation
from llama_index.graph_stores.nebula import NebulaPropertyGraphStore
from llama_index.graph_stores.nebula.nebula_property_graph import DEFAULT_PROPS_SCHEMA
from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool


_DEFAULT_USERNAME = "root"
_SPACE_PARTITION_NUM = 1
_SPACE_REPLICA_FACTOR = 1
_SPACE_VID_LENGTH = 256


def _schema_columns(schema: str) -> Dict[str, str]:
    """``{column: TYPE}`` from a ``"`name` TYPE, ..."`` tag schema."""
    columns = {}
    for column in schema.split(","):
        name, _, kind = column.strip().partition(" ")
        if name:
            columns[name.strip("`")] = kind.strip().upper()
    return columns


# Nebula is schema-full: a property that is not a `Props__` column fails the whole INSERT.
_PROPS_COLUMNS = _schema_columns(DEFAULT_PROPS_SCHEMA)
_PACKED_PROPERTY = "_node_content"
_DELETE_BATCH = 200


def _vid_literal(vid: str) -> str:
    return '"' + vid.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _fit_properties(properties: Mapping[str, Any]) -> Dict[str, Any]:
    """Map properties onto the fixed columns; the rest is packed as JSON into `_node_content`."""
    fitted: Dict[str, Any] = {}
    extra: Dict[str, Any] = {}
    for key, value in properties.items():
        if value is None:
            continue
        kind = _PROPS_COLUMNS.get(key)
        if kind is None:
            extra[key] = value
        elif kind.startswith("INT"):
            try:
                fitted[key] = int(value)
            except (TypeError, ValueError):
                extra[key] = value
        elif isinstance(value, str):
            fitted[key] = value
        else:
            fitted[key] = json.dumps(value, ensure_ascii=False, default=str)
    if extra:
        packed: Dict[str, Any] = {}
        if _PACKED_PROPERTY in fitted:
            try:
                existing = json.loads(fitted[_PACKED_PROPERTY])
            except ValueError:
                existing = None
            packed = existing if isinstance(existing, dict) else {_PACKED_PROPERTY: fitted[_PACKED_PROPERTY]}
        fitted[_PACKED_PROPERTY] = json.dumps(
            {**extra, **packed}, ensure_ascii=False, default=str
        )
    return fitted


class NebulaAdapter(GraphAdapter):
    """Operate graph spaces through one NebulaGraph connection."""

    def __init__(self, options: Mapping[str, object]):
        self._options = dict(options)
        self._url = str(self._options["url"])
        self._username = str(self._options.get("username") or _DEFAULT_USERNAME)
        # nebula3 refuses an empty password even with auth disabled, so default to the username.
        self._password = str(self._options.get("password") or self._username)
        self._host, self._port = self._parse_url(self._url)
        self._default_space = str(self._options.get("space") or "")
        self._stores: Dict[str, NebulaPropertyGraphStore] = {}

    # --- url / space ----------------------------------------------------------

    @staticmethod
    def _parse_url(url: str):
        parsed = urlparse(url)
        if parsed.scheme != "nebula" or not parsed.hostname or parsed.port is None:
            raise ValueError("Nebula URL must use the format nebula://host:port")
        return parsed.hostname, parsed.port

    def _ensure_space(self, space: str) -> None:
        """Create the space if it does not exist, and wait for it to be usable."""
        config = Config()
        config.timeout = engine_config.NEBULA_TIMEOUT_MS
        connection_pool = ConnectionPool()
        try:
            if not connection_pool.init([(self._host, self._port)], config):
                raise ConnectionError(
                    f"Failed to connect to Nebula Graph at {self._host}:{self._port}"
                )
            session = connection_pool.get_session(self._username, self._password)
            try:
                result = session.execute(
                    f"CREATE SPACE IF NOT EXISTS `{space}`("
                    f"partition_num={_SPACE_PARTITION_NUM}, "
                    f"replica_factor={_SPACE_REPLICA_FACTOR}, "
                    f"vid_type=FIXED_STRING({_SPACE_VID_LENGTH}))"
                )
                if not result.is_succeeded():
                    raise RuntimeError(
                        f"Failed to create Nebula space {space}: {result.error_msg()}"
                    )
                deadline = time.monotonic() + engine_config.NEBULA_SPACE_READY_TIMEOUT
                last_error = "unknown error"
                while time.monotonic() < deadline:
                    use_result = session.execute(f"USE `{space}`")
                    if use_result.is_succeeded():
                        return
                    last_error = use_result.error_msg()
                    time.sleep(engine_config.NEBULA_SPACE_POLL_INTERVAL)
                raise TimeoutError(
                    f"Nebula space {space} was not ready within "
                    f"{engine_config.NEBULA_SPACE_READY_TIMEOUT:g}s: {last_error}"
                )
            finally:
                session.release()
        finally:
            connection_pool.close()

    def _wait_for_entity_schema(self, space: str) -> None:
        """Wait until graphd can see the tag the property graph store writes."""
        config = Config()
        config.timeout = engine_config.NEBULA_TIMEOUT_MS
        connection_pool = ConnectionPool()
        try:
            if not connection_pool.init([(self._host, self._port)], config):
                raise ConnectionError(
                    f"Failed to connect to Nebula Graph at {self._host}:{self._port}"
                )
            session = connection_pool.get_session(self._username, self._password)
            try:
                last_error = "unknown error"
                attempts = engine_config.NEBULA_SCHEMA_READY_ATTEMPTS
                interval = engine_config.NEBULA_SCHEMA_RETRY_INTERVAL
                for attempt in range(attempts):
                    use_result = session.execute(f"USE `{space}`")
                    if use_result.is_succeeded():
                        result = session.execute("DESCRIBE TAG `Entity__`")
                        if result.is_succeeded():
                            return
                        last_error = result.error_msg()
                    else:
                        last_error = use_result.error_msg()
                    if attempt < attempts - 1:
                        time.sleep(interval)
                raise TimeoutError(
                    f"Nebula schema Entity__ was not ready after {attempts} attempts "
                    f"({(attempts - 1) * interval:g}s retry delay) in "
                    f"space {space}: {last_error}"
                )
            finally:
                session.release()
        finally:
            connection_pool.close()

    def store(self, space: str) -> NebulaPropertyGraphStore:
        """The property-graph store bound to `space`, creating it if needed."""
        if space not in self._stores:
            self._ensure_space(space)
            self._stores[space] = NebulaPropertyGraphStore(
                space=space,
                username=self._username,
                password=self._password,
                url=self._url,
                overwrite=False,
            )
            self._wait_for_entity_schema(space)
        return self._stores[space]

    def _space_of(self, collection: GraphCollection) -> str:
        return collection.space or self._default_space

    def existing_store(self, space: str) -> NebulaPropertyGraphStore:
        """Open a persisted space for retrieval; never create a missing space."""
        space = space or self._default_space
        config = Config()
        config.timeout = engine_config.NEBULA_TIMEOUT_MS
        pool = ConnectionPool()
        try:
            if not pool.init([(self._host, self._port)], config):
                raise ConnectionError("Cannot connect to Nebula for graph retrieval")
            session = pool.get_session(self._username, self._password)
            try:
                result = session.execute(f"USE `{space}`")
                if not result.is_succeeded():
                    raise ValueError(
                        f"Nebula graph space {space!r} is unavailable: {result.error_msg()}"
                    )
            finally:
                session.release()
        finally:
            pool.close()
        if space not in self._stores:
            self._stores[space] = NebulaPropertyGraphStore(
                space=space, username=self._username, password=self._password,
                url=self._url, overwrite=False,
            )
        return self._stores[space]

    # --- GraphAdapter contract ------------------------------------------------

    @staticmethod
    def _upsert_nodes(store, nodes) -> None:
        # Method name differs across llama-index versions (add_nodes -> upsert_nodes).
        upsert = getattr(store, "upsert_nodes", None) or getattr(store, "add_nodes", None)
        if upsert is None:
            raise NotImplementedError(
                "NebulaPropertyGraphStore has no upsert_nodes/add_nodes method"
            )
        upsert(nodes)

    @staticmethod
    def _upsert_relations(store, relations) -> None:
        upsert = getattr(store, "upsert_relations", None) or getattr(
            store, "add_relations", None
        )
        if upsert is None:
            raise NotImplementedError(
                "NebulaPropertyGraphStore has no upsert_relations/add_relations method"
            )
        upsert(relations)

    @staticmethod
    def _retry_schema_write(write) -> None:
        """Allow new schemas to propagate to both graphd and storaged."""
        attempts = engine_config.NEBULA_SCHEMA_WRITE_ATTEMPTS
        for attempt in range(attempts):
            try:
                write()
                return
            except Exception as error:
                # LlamaIndex puts the statement in args too; classify only the backend error.
                message = str(error)
                if len(error.args) > 1 and error.args[0] == "NebulaGraph query failed:":
                    message = str(error.args[1])
                schema_pending = any(
                    marker in message
                    for marker in (
                        "No schema found",
                        "Storage Error: Tag not found.",
                        "Storage Error: Edge not found.",
                    )
                )
                if not schema_pending or attempt == attempts - 1:
                    raise
                time.sleep(engine_config.NEBULA_SCHEMA_RETRY_INTERVAL)

    def upsert_vertices(
        self, collection: GraphCollection, vertices: List[Dict[str, Any]]
    ) -> None:
        if not vertices:
            return
        store = self.store(self._space_of(collection))
        nodes = [
                EntityNode(
                    name=str(vertex["id"]),
                    label=str(vertex["label"]),
                    properties=_fit_properties(vertex.get("properties") or {}),
                )
                for vertex in vertices
            ]
        self._retry_schema_write(lambda: self._upsert_nodes(store, nodes))

    def upsert_edges(
        self, collection: GraphCollection, edges: List[Dict[str, Any]]
    ) -> None:
        if not edges:
            return
        store = self.store(self._space_of(collection))
        relations = [
                Relation(
                    source_id=str(edge["source"]),
                    target_id=str(edge["target"]),
                    label=str(edge["label"]),
                    properties=_fit_properties(edge.get("properties") or {}),
                )
                for edge in edges
            ]
        self._retry_schema_write(lambda: self._upsert_relations(store, relations))

    def delete_vertices(self, collection: GraphCollection, vertex_ids: List[str]) -> int:
        """`DELETE VERTEX ... WITH EDGE` in batches; a missing space is not created."""
        ids = [str(vertex_id) for vertex_id in dict.fromkeys(vertex_ids)]
        if not ids:
            return 0
        try:
            store = self.existing_store(self._space_of(collection))
        except ValueError:
            return 0
        for start in range(0, len(ids), _DELETE_BATCH):
            batch = ", ".join(_vid_literal(vid) for vid in ids[start:start + _DELETE_BATCH])
            store.structured_query(f"DELETE VERTEX {batch} WITH EDGE;")
        return len(ids)

    def query(
        self,
        collection: GraphCollection,
        statement: str,
        parameters: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        store = self.store(self._space_of(collection))
        # Returns the raw nebula3 ResultSet, not a list of dicts.
        return store.structured_query(statement, param_map=dict(parameters or {}))

    def clear(self, collection: GraphCollection) -> None:
        space = self._space_of(collection)
        store = self.store(space)
        store.structured_query(f"CLEAR SPACE `{space}`")

    def ping(self) -> None:
        """One real round trip: reach the graphd and list spaces."""
        config = Config()
        config.timeout = engine_config.NEBULA_TIMEOUT_MS
        pool = ConnectionPool()
        try:
            if not pool.init([(self._host, self._port)], config):
                raise ConnectionError(
                    f"Failed to connect to Nebula Graph at {self._host}:{self._port}"
                )
            session = pool.get_session(self._username, self._password)
            try:
                result = session.execute("SHOW SPACES")
                if not result.is_succeeded():
                    raise ConnectionError(result.error_msg())
            finally:
                session.release()
        finally:
            pool.close()

    def close(self) -> None:
        self._stores.clear()
