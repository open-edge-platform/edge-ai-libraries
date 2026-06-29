# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from functools import lru_cache
from importlib import import_module
from typing import Any
from urllib.parse import urlsplit

from src.common.logger import get_logger
from src.common.settings import settings
from src.retriever.backends.base import VectorStoreBackend
from src.retriever.embedding_client import EmbeddingAPI


logger = get_logger()


def _describe_milvus_target(uri: str) -> str:
    """Return a credential-free description of the Milvus target."""
    parsed = urlsplit(uri)
    if not parsed.scheme and not parsed.netloc:
        return uri

    host = parsed.hostname or "unknown-host"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{host}{path}"


def _register_milvus_orm_alias() -> None:
    """Work around a langchain_milvus + pymilvus 2.6.x compatibility issue.

    langchain_milvus 0.3.3 uses MilvusClient internally (new API) but the `col`
    property still uses the legacy ORM ``Collection(name, using=alias)``.  The
    MilvusClient creates its connection under a private alias (``cm-<id>``), which
    is *not* automatically registered in the ORM ``connections`` registry.  Any
    call path that accesses ``self.col`` (e.g. inside ``Milvus.__init__`` when the
    collection already exists, or during ``add_texts``) raises
    ``ConnectionNotExistException``.

    This function patches ``MilvusClient.__init__`` so that every new instance
    auto-registers its handler in the ORM registry. The patch is applied once and
    is idempotent (guarded by ``_orm_alias_patch_applied``).
    """
    try:
        from pymilvus import MilvusClient as _MC  # noqa: PLC0415
        from pymilvus import connections as _conn  # noqa: PLC0415

        if getattr(_MC, "_orm_alias_patch_applied", False):
            logger.debug("Milvus ORM alias compatibility patch already applied")
            return

        _orig_init = _MC.__init__

        def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
            _orig_init(self, *args, **kwargs)
            try:
                _conn._alias_handlers[self._using] = self._handler
            except Exception:  # noqa: BLE001
                pass

        _MC.__init__ = _patched_init
        _MC._orm_alias_patch_applied = True  # type: ignore[attr-defined]
        logger.debug("Applied Milvus ORM alias compatibility patch")
    except Exception:  # noqa: BLE001
        logger.debug(
            "Skipping Milvus ORM alias compatibility patch; ORM fallback path is unavailable",
            exc_info=True,
        )


class MilvusAdapter:
    """Normalizes Milvus search signature to the shared backend contract."""

    def __init__(self, store: Any) -> None:
        """Wrap a LangChain Milvus store instance."""
        self._store = store

    def _ensure_search_params(self) -> None:
        """Lazily populate search_params if the index wasn't ready at init time.

        The Milvus client's ``_create_search_params`` only fires when
        ``self.search_params is None``.  If the collection index was still
        building when the service started, the method would find no index and
        leave ``search_params`` as an empty list.  Reset it to ``None`` and
        retry so the guard condition triggers again.
        """
        store = self._store
        if not store.search_params:
            store.search_params = None
            store._create_search_params()

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter: Any = None,
        **kwargs: Any,
    ) -> list[tuple[Any, float]]:
        """Map generic `filter` argument to Milvus `expr` argument."""
        self._ensure_search_params()
        expr = filter if isinstance(filter, str) else None
        return self._store.similarity_search_with_score(query, k=k, expr=expr, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to wrapped Milvus store."""
        return getattr(self._store, name)


@lru_cache(maxsize=1)
def get_vectordb() -> VectorStoreBackend:
    """Create and cache the Milvus vector store client."""
    try:
        Milvus = getattr(import_module("langchain_milvus"), "Milvus")
    except ImportError as exc:
        raise ImportError(
            "Milvus backend requires 'langchain-milvus'. Install backend-milvus dependencies."
        ) from exc

    embeddings = EmbeddingAPI(
        api_url=settings.EMBEDDINGS_ENDPOINT,
        model_name=settings.EMBEDDING_MODEL_NAME,
    )

    connection_args: dict[str, Any] = {"uri": settings.MILVUS_URI}
    if settings.MILVUS_TOKEN:
        connection_args["token"] = settings.MILVUS_TOKEN
    if settings.MILVUS_DB_NAME:
        connection_args["db_name"] = settings.MILVUS_DB_NAME

    logger.info(
        "Initializing Milvus backend for collection '%s' at '%s'%s",
        settings.INDEX_NAME,
        _describe_milvus_target(settings.MILVUS_URI),
        f" (db='{settings.MILVUS_DB_NAME}')" if settings.MILVUS_DB_NAME else "",
    )
    _register_milvus_orm_alias()

    # When a dedicated metadata_field is configured (e.g. a JSON column),
    # disable dynamic fields so langchain-milvus actually honours it;
    # enable_dynamic_field=True causes metadata_field to be silently ignored.
    use_dynamic = not settings.MILVUS_METADATA_FIELD

    milvus_kwargs: dict[str, Any] = {
        "embedding_function": embeddings,
        "collection_name": settings.INDEX_NAME,
        "connection_args": connection_args,
        "index_params": {
            "index_type": settings.MILVUS_INDEX_TYPE,
            "metric_type": settings.MILVUS_METRIC_TYPE,
        },
        "enable_dynamic_field": use_dynamic,
        "text_field": settings.MILVUS_TEXT_FIELD,
    }
    if settings.MILVUS_METADATA_FIELD:
        milvus_kwargs["metadata_field"] = settings.MILVUS_METADATA_FIELD

    store = Milvus(**milvus_kwargs)

    return MilvusAdapter(store)


def check_ready() -> bool:
    """Validate Milvus backend readiness by initializing the store."""
    logger.debug("Running Milvus backend readiness initialization")
    _ = get_vectordb()
    return True
