# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Milvus implementation of :class:`BaseVectorStore`.

Encapsulates all ``langchain_milvus`` specifics. The behaviors below were
validated against a real Milvus 2.6.x standalone container during the
dependency/PoC spike and MUST be preserved:

1. Connection is passed as ``connection_args={"uri": "http://host:port"}`` —
   supplying host/port separately made the internal ``MilvusClient`` default to
   port 19530 regardless of configuration.
2. After the store is constructed, an ORM-style connection is registered via
   ``pymilvus.connections.connect(alias=..., uri=...)`` so langchain_milvus
   0.3.3's ``col`` property (used by ``_extract_fields`` during inserts)
   resolves; without it ``add_embeddings`` raises ``ConnectionNotExistException``.
3. ``enable_dynamic_field=True`` preserves list/nested metadata as-is, so the
   metadata adapter is near pass-through (no VDMS-style list flattening).
4. ``add_embeddings`` returns int64 primary keys; they are normalized to ``str``
   for the common contract.
5. Proxy env vars are cleared for the Milvus host so localhost/in-cluster gRPC
   is not routed through an HTTP proxy.
"""

from __future__ import annotations

import os
from typing import List, Optional
from urllib.parse import urlparse

from langchain_core.embeddings import Embeddings

from src.common import Strings, logger, settings
from src.core.vectorstores.base import BaseVectorStore
from src.core.vectorstores.factory import register_backend
from src.core.vectorstores.metadata import project_to_canonical

_BATCH_SIZE = 200


class _DummyEmbedding(Embeddings):
    """Minimal embedding shim; langchain_milvus requires one but
    ``add_embeddings`` consumes precomputed vectors directly."""

    def embed_documents(self, texts):
        raise NotImplementedError("Use add_embeddings() with precomputed vectors")

    def embed_query(self, text):
        raise NotImplementedError("Use add_embeddings() with precomputed vectors")


@register_backend("milvus")
class MilvusVectorStore(BaseVectorStore):
    """Vector store backed by Milvus via ``langchain_milvus``."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[str] = None,
        uri: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        self.collection_name = collection_name or settings.DB_COLLECTION
        self.metric_type = (settings.VDB_METRIC_TYPE or "IP").upper()
        self.index_type = (settings.VDB_INDEX_TYPE or "FLAT").upper()
        self.uri = self._resolve_uri(host, port, uri)
        self.store = None  # langchain_milvus.Milvus, lazily constructed

    @staticmethod
    def _resolve_uri(
        host: Optional[str], port: Optional[str], uri: Optional[str]
    ) -> str:
        explicit_uri = uri or settings.MILVUS_URI
        if explicit_uri:
            return explicit_uri
        resolved_host = host or settings.MILVUS_HOST or "localhost"
        resolved_port = port or settings.MILVUS_PORT or "19530"
        return f"http://{resolved_host}:{resolved_port}"

    def _disable_proxy_for_host(self) -> None:
        """Ensure gRPC to the Milvus host bypasses any configured HTTP proxy."""
        hostname = urlparse(self.uri).hostname or "localhost"
        existing = os.environ.get("no_proxy", "") or os.environ.get("NO_PROXY", "")
        entries = {e.strip() for e in existing.split(",") if e.strip()}
        entries.update({hostname, "localhost", "127.0.0.1"})
        joined = ",".join(sorted(entries))
        os.environ["no_proxy"] = joined
        os.environ["NO_PROXY"] = joined

    def connect(self) -> None:
        if self.store is not None:
            return
        try:
            from langchain_milvus import Milvus
            from pymilvus import connections

            self._disable_proxy_for_host()

            # Quirk 1: pass the full URI via connection_args.
            self.store = Milvus(
                embedding_function=_DummyEmbedding(),
                collection_name=self.collection_name,
                connection_args={"uri": self.uri},
                enable_dynamic_field=True,  # Quirk 3: preserve list/nested metadata
                index_params={
                    "metric_type": self.metric_type,
                    "index_type": self.index_type,
                },
                auto_id=True,
            )

            # Quirk 2: register an ORM-style connection so the `col` property
            # resolves during inserts with langchain_milvus 0.3.3 + pymilvus 2.6.
            alias = getattr(self.store, "alias", None) or "default"
            connections.connect(alias=alias, uri=self.uri)

            logger.info(
                "Milvus initialized - collection: %s (%s/%s) at %s",
                self.collection_name,
                self.metric_type,
                self.index_type,
                self.uri,
            )
        except Exception as ex:
            logger.error("Error initializing Milvus: %s", ex)
            raise Exception(Strings.db_conn_error)

    def clean_metadata(self, metadata: dict) -> dict:
        """Project onto the canonical contract, then drop ``None`` values.

        Lists and nested values are preserved as-is because Milvus dynamic
        fields are enabled.
        """
        return {
            key: value
            for key, value in project_to_canonical(metadata).items()
            if value is not None
        }

    def add_embeddings(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: List[dict],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        if not embeddings:
            return []
        self.connect()

        cleaned_metadatas = [self.clean_metadata(m or {}) for m in metadatas]
        generated_ids: List[str] = []

        for start_idx in range(0, len(embeddings), _BATCH_SIZE):
            end_idx = min(start_idx + _BATCH_SIZE, len(embeddings))
            batch_texts = texts[start_idx:end_idx]
            batch_embeddings = embeddings[start_idx:end_idx]
            batch_metadatas = cleaned_metadatas[start_idx:end_idx]

            inserted = self.store.add_embeddings(
                texts=batch_texts,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
            )
            # Quirk 4: normalize int64 pks to str.
            generated_ids.extend(str(i) for i in inserted)

        logger.info("Stored %d embeddings in Milvus", len(generated_ids))
        return generated_ids

    def update_index(self) -> None:
        """No-op: Milvus indexes eagerly; nothing to flush at teardown."""
        logger.debug("Milvus update_index() is a no-op (eager indexing).")

    def health(self) -> dict:
        status = {"backend": "milvus", "collection": self.collection_name}
        try:
            from pymilvus import connections

            self._disable_proxy_for_host()
            alias = "health_check"
            connections.connect(alias=alias, uri=self.uri)
            connections.disconnect(alias)
            status["status"] = "ok"
        except Exception as exc:
            status["status"] = "error"
            status["error"] = str(exc)
        return status
