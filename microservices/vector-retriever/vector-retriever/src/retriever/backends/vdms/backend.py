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
