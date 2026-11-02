# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from functools import lru_cache
from urllib.parse import urlsplit

from src.common.logger import get_logger
from src.common.settings import settings
from src.retriever.backends.base import VectorStoreBackend
from src.retriever.embedding_client import EmbeddingAPI


logger = get_logger()


def _describe_connection_target(connection_string: str) -> str:
    """Return a credential-free description of the PGVector target."""
    parsed = urlsplit(connection_string)
    host = parsed.hostname or "unknown-host"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    database = parsed.path.lstrip("/") or "default"
    return f"{host}/{database}"


@lru_cache(maxsize=1)
def get_vectordb() -> VectorStoreBackend:
    """Create and cache the PGVector vector store client."""
    try:
        from langchain_postgres import PGVector
    except ImportError as exc:
        raise ImportError(
            "PGVector backend requires 'langchain-postgres'. Install backend-pgvector dependencies."
        ) from exc

    if not settings.PGVECTOR_CONNECTION_STRING:
        raise ValueError(
            "PGVECTOR_CONNECTION_STRING is required when RETRIEVER_BACKEND=pgvector"
        )

    embeddings = EmbeddingAPI(
        api_url=settings.EMBEDDINGS_ENDPOINT,
        model_name=settings.EMBEDDING_MODEL_NAME,
    )
    logger.info(
        "Initializing PGVector backend for collection '%s' on '%s'",
        settings.INDEX_NAME,
        _describe_connection_target(settings.PGVECTOR_CONNECTION_STRING),
    )

    return PGVector(
        embeddings=embeddings,
        collection_name=settings.INDEX_NAME,
        connection=settings.PGVECTOR_CONNECTION_STRING,
        use_jsonb=True,
    )


def check_ready() -> bool:
    """Validate PGVector backend readiness by initializing the store."""
    logger.debug("Running PGVector backend readiness initialization")
    _ = get_vectordb()
    return True
