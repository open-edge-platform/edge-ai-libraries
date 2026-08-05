# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""VDMS implementation of :class:`BaseVectorStore`.

Encapsulates all ``langchain_vdms`` specifics (client creation, the dummy
embedding shim, ``add_from`` based inserts, list-flattening metadata cleaning,
and the descriptor-set index update previously embedded in the app lifespan).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List, Optional

from langchain_core.embeddings import Embeddings

from src.common import Strings, logger, settings
from src.core.vectorstores.base import BaseVectorStore
from src.core.vectorstores.factory import register_backend
from src.core.vectorstores.metadata import flatten_to_scalars, project_to_canonical

if TYPE_CHECKING:
    from langchain_vdms.vectorstores import VDMS, VDMS_Client

_DEFAULT_DIMENSIONS = 512
_BATCH_SIZE = 200


class _DummyEmbedding(Embeddings):
    """Minimal embedding shim; VDMS requires one but ``add_from`` bypasses it."""

    def __init__(self, dimensions: int = _DEFAULT_DIMENSIONS):
        self.dimensions = dimensions

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError("Use add_from() / add_embeddings() instead")

    def embed_query(self, text: str) -> List[float]:
        raise NotImplementedError("Use add_from() / add_embeddings() instead")


@register_backend("vdms")
class VDMSVectorStore(BaseVectorStore):
    """Vector store backed by VDMS via ``langchain_vdms``."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_dimensions: int = _DEFAULT_DIMENSIONS,
    ) -> None:
        self.host = host or settings.VDMS_VDB_HOST
        self.port = port or settings.VDMS_VDB_PORT
        self.collection_name = collection_name or settings.DB_COLLECTION
        self.embedding_dimensions = embedding_dimensions or _DEFAULT_DIMENSIONS
        self.distance_strategy = (settings.VDB_METRIC_TYPE or "IP").upper()
        self.client: Optional[VDMS_Client] = None
        self.video_db: Optional[VDMS] = None

    def connect(self) -> None:
        if self.video_db is not None:
            return
        try:
            from langchain_vdms.vectorstores import VDMS, VDMS_Client

            logger.info("Connecting to VDMS DB server at %s:%s...", self.host, self.port)
            self.client = VDMS_Client(host=self.host, port=int(self.port))
            self.video_db = VDMS(
                client=self.client,
                embedding=_DummyEmbedding(self.embedding_dimensions),
                collection_name=self.collection_name,
                engine="FaissFlat",
                distance_strategy=self.distance_strategy,
                embedding_dimensions=self.embedding_dimensions,
            )
            logger.info(
                "VDMS initialized - collection: %s (%dD, %s)",
                self.collection_name,
                self.embedding_dimensions,
                self.distance_strategy,
            )
        except Exception as ex:
            logger.error("Error initializing VDMS: %s", ex)
            raise Exception(Strings.db_conn_error)

    def clean_metadata(self, metadata: dict) -> dict:
        """Project onto the canonical contract, then flatten to VDMS scalars."""
        return flatten_to_scalars(project_to_canonical(metadata))

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
            batch_embeddings = embeddings[start_idx:end_idx]
            batch_texts = texts[start_idx:end_idx]
            batch_metadatas = cleaned_metadatas[start_idx:end_idx]
            if ids is not None:
                batch_ids = [str(i) for i in ids[start_idx:end_idx]]
            else:
                batch_ids = [str(uuid.uuid4()) for _ in batch_embeddings]

            inserted_ids = self._add_from_with_retry(
                batch_texts, batch_embeddings, batch_metadatas, batch_ids
            )

            if not inserted_ids or len(inserted_ids) != len(batch_ids):
                raise ValueError(
                    "VDMS add_from returned unexpected result size. "
                    f"Expected {len(batch_ids)}, received "
                    f"{len(inserted_ids) if inserted_ids else 0}."
                )
            generated_ids.extend(str(i) for i in inserted_ids)

        self.video_db.check_and_update_properties()
        logger.info("Stored %d embeddings in VDMS", len(generated_ids))
        return generated_ids

    def _add_from_with_retry(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: List[dict],
        ids: List[str],
    ) -> List[str]:
        try:
            return self.video_db.add_from(
                texts=texts,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
                batch_size=_BATCH_SIZE,
            )
        except Exception as exc:
            logger.warning(
                "VDMS add_from failed; reinitializing VDMS client and retrying once. Error: %s",
                exc,
            )
            self.video_db = None
            self.connect()
            return self.video_db.add_from(
                texts=texts,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
                batch_size=_BATCH_SIZE,
            )

    def update_index(self) -> None:
        """Persist the VDMS descriptor-set index (previously in app lifespan)."""
        if self.client is None:
            logger.debug("VDMS client not initialized; skipping index update.")
            return
        try:
            from langchain_vdms.vectorstores import VDMS_Utils

            vdms_utils = VDMS_Utils(self.client)
            query = vdms_utils.add_descriptor_set(
                "FindDescriptorSet",
                name=self.collection_name,
                storeIndex=True,
            )
            res, _ = vdms_utils.run_vdms_query([query])
            if res and "FailedCommand" in res[0]:
                raise ValueError(
                    f"Failed to update VDMS index for collection {self.collection_name}."
                )
            logger.info("VDMS index updated for collection '%s'.", self.collection_name)
        except Exception as exc:
            logger.error("Error updating VDMS index: %s", exc)

    def delete_embeddings(self, bucket_name: str, video_id: str) -> int:
        """Delete all VDMS vectors for a video via a metadata constraint.

        Uses ``langchain_vdms``' constraint-based delete: descriptors whose
        ``video_id`` and ``bucket_name`` properties match are removed. VDMS does
        not report an exact deleted count, so this returns ``-1`` on success.
        """
        self.connect()
        constraints = {
            "video_id": ["==", video_id],
            "bucket_name": ["==", bucket_name],
        }
        try:
            self.video_db.delete(constraints=constraints)
        except Exception as exc:
            logger.error(
                "VDMS delete failed for %s/%s: %s", bucket_name, video_id, exc
            )
            raise
        logger.info(
            "Deleted VDMS vectors for video %s in bucket %s", video_id, bucket_name
        )
        return -1

    def delete_bucket_embeddings(self, bucket_name: str) -> int:
        """Delete every VDMS vector belonging to a bucket via a metadata constraint."""
        self.connect()
        try:
            self.video_db.delete(constraints={"bucket_name": ["==", bucket_name]})
        except Exception as exc:
            logger.error("VDMS bucket delete failed for %s: %s", bucket_name, exc)
            raise
        logger.info("Deleted VDMS vectors for bucket %s", bucket_name)
        return -1

    def health(self) -> dict:
        status = {"backend": "vdms", "collection": self.collection_name}
        try:
            from langchain_vdms.vectorstores import VDMS_Client

            if self.client is None:
                VDMS_Client(host=self.host, port=int(self.port))
            status["status"] = "ok"
        except Exception as exc:
            status["status"] = "error"
            status["error"] = str(exc)
        return status
