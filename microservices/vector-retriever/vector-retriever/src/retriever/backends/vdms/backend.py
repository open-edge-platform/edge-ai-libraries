# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from functools import lru_cache
from typing import Any

from langchain_vdms.vectorstores import VDMS, VDMS_Client

from src.common.logger import get_logger
from src.common.settings import settings
from src.retriever.backends.base import VectorStoreBackend
from src.retriever.embedding_client import EmbeddingAPI


logger = get_logger()


class VDMSBackend(VDMS):
    """VDMS store that persists list-typed metadata as comma-joined strings.

    langchain-vdms's ``validate_vdms_properties`` silently drops any metadata
    key whose value is a Python list (VDMS has no native array property type).
    This subclass encodes list values as ``","``-joined strings before they
    reach that validation step, allowing the service's in-memory filter path
    (which already handles comma-separated strings via ``_normalize_string_list``)
    to evaluate list-typed predicates such as ``contains_any`` / ``contains_all``
    against the stored data.
    """

    @staticmethod
    def _encode_list_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        """Convert list metadata values into VDMS-compatible comma-separated strings."""
        return {
            k: ",".join(str(v) for v in val) if isinstance(val, list) else val
            for k, val in metadata.items()
        }

    def add_texts(
        self,
        texts: Any,
        metadatas: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """Encode list metadata before delegating to the VDMS client."""
        if metadatas:
            metadatas = [self._encode_list_metadata(m) for m in metadatas]
        return super().add_texts(texts, metadatas=metadatas, **kwargs)

    def _refresh_collection_properties(self) -> None:
        """Re-sync the cached descriptor-set property list from VDMS.

        ``langchain-vdms`` snapshots the collection's property names when the
        store is constructed and only refreshes them after a write (guarded by
        its ``updated_properties_flag``). A read-only retriever whose store was
        created *before* any data was ingested therefore keeps an empty/stale
        property list, and because the query builder only requests the
        properties it knows about (``results={"list": self.collection_properties}``)
        every hit comes back with empty ``metadata``. This forces a refresh so
        results carry the metadata persisted by the writer (``multimodal-dataprep``)
        even when the collection was empty at startup or gained new fields after
        the store was cached.
        """
        try:
            self.updated_properties_flag = True
            super().check_and_update_properties()
        except Exception as exc:  # pragma: no cover - defensive, non-fatal
            logger.warning("Failed to refresh VDMS collection properties: %s", exc)

    def check_and_update_properties(self) -> None:
        """Always re-read the descriptor-set properties from VDMS.

        ``query_by_embeddings`` (the shared code path for every similarity
        search, text or vector) calls this at the start of each query, but the
        base implementation is a no-op unless ``updated_properties_flag`` is set
        — a flag only raised by the write path. Overriding here (rather than the
        ``similarity_search_*`` methods) keeps those methods' signatures intact
        so the service's ``inspect.signature`` based ``fetch_k`` dispatch keeps
        working, while still guaranteeing metadata is populated on read.
        """
        self._refresh_collection_properties()


@lru_cache(maxsize=1)
def get_vectordb() -> VectorStoreBackend:
    """Create and cache the LangChain VDMS vector store client."""
    logger.info(
        "Initializing VDMS backend for collection '%s' at '%s:%s'",
        settings.INDEX_NAME,
        settings.VDMS_VDB_HOST,
        settings.VDMS_VDB_PORT,
    )
    client = VDMS_Client(settings.VDMS_VDB_HOST, settings.VDMS_VDB_PORT)
    embeddings = EmbeddingAPI(
        api_url=settings.EMBEDDINGS_ENDPOINT,
        model_name=settings.EMBEDDING_MODEL_NAME,
    )
    vector_dimensions = embeddings.get_embedding_length()
    logger.debug("Resolved VDMS embedding dimension: %s", vector_dimensions)
    return VDMSBackend(
        client=client,
        embedding=embeddings,
        collection_name=settings.INDEX_NAME,
        distance_strategy=settings.DISTANCE_STRATEGY,
        embedding_dimensions=vector_dimensions,
        engine=settings.SEARCH_ENGINE,
    )


def check_ready() -> bool:
    """Validate VDMS backend readiness by initializing the store."""
    logger.debug("Running VDMS backend readiness initialization")
    _ = get_vectordb()
    return True
