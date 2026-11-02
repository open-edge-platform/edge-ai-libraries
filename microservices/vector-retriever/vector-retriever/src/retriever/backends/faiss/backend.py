# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from functools import lru_cache
from importlib import import_module
from pathlib import Path

from src.common.logger import get_logger
from src.common.settings import settings
from src.retriever.backends.base import VectorStoreBackend
from src.retriever.embedding_client import EmbeddingAPI


logger = get_logger()


@lru_cache(maxsize=1)
def get_vectordb() -> VectorStoreBackend:
    """Create and cache the FAISS vector store instance.

    Loads a persisted local index when `FAISS_INDEX_PATH` is provided and
    exists, otherwise creates an in-memory index.
    """
    try:
        faiss = import_module("faiss")
        InMemoryDocstore = getattr(
            import_module("langchain_community.docstore.in_memory"),
            "InMemoryDocstore",
        )
        FAISS = getattr(import_module("langchain_community.vectorstores"), "FAISS")
    except ImportError as exc:
        raise ImportError(
            "FAISS backend requires 'faiss-cpu' and 'langchain-community'. Install backend-faiss dependencies."
        ) from exc

    embeddings = EmbeddingAPI(
        api_url=settings.EMBEDDINGS_ENDPOINT,
        model_name=settings.EMBEDDING_MODEL_NAME,
    )

    index_path = (settings.FAISS_INDEX_PATH or "").strip()
    if index_path:
        path = Path(index_path)
        if path.exists():
            logger.info("Loading FAISS index from '%s'", path)
            return FAISS.load_local(
                index_path,
                embeddings,
                allow_dangerous_deserialization=True,
            )
        logger.warning(
            "FAISS index path '%s' does not exist; creating an in-memory index instead",
            path,
        )

    dimensions = embeddings.get_embedding_length()
    logger.info("Creating in-memory FAISS index with dimension %s", dimensions)
    index = faiss.IndexFlatL2(dimensions)
    return FAISS(
        embedding_function=embeddings,
        index=index,
        docstore=InMemoryDocstore(),
        index_to_docstore_id={},
    )


def check_ready() -> bool:
    """Validate FAISS backend readiness by initializing the store."""
    logger.debug("Running FAISS backend readiness initialization")
    _ = get_vectordb()
    return True
