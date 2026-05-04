# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Registry-based dispatch for retriever backends.

To add a new backend:
1) Add src/retriever/backends/<name>/backend.py with get_vectordb/check_ready.
2) Add src/retriever/backends/<name>/filters.py with build_filters.
3) Register <name> in BACKEND_REGISTRY below.
"""

from importlib import import_module
from typing import Any, Callable, Mapping

from src.common.logger import get_logger
from src.common.schema import (
    BackendFilterCapabilities,
    FILTER_LOGICAL_BLOCKS,
    FILTER_OPERATORS,
    FilterCapabilitiesResponse,
    FilterCondition,
    MAX_WHERE_CLAUSES,
    MAX_WHERE_DEPTH,
    MAX_WHERE_LIST_SIZE,
    TimeRange,
)
from src.common.settings import settings
from src.retriever.backends.base import BackendSpec, VectorStoreBackend


logger = get_logger()


BACKEND_REGISTRY: dict[str, BackendSpec] = {
    "vdms": BackendSpec(
        backend_module_path="src.retriever.backends.vdms.backend",
        filters_module_path="src.retriever.backends.vdms.filters",
    ),
    "milvus": BackendSpec(
        backend_module_path="src.retriever.backends.milvus.backend",
        filters_module_path="src.retriever.backends.milvus.filters",
    ),
    "pgvector": BackendSpec(
        backend_module_path="src.retriever.backends.pgvector.backend",
        filters_module_path="src.retriever.backends.pgvector.filters",
    ),
    "faiss": BackendSpec(
        backend_module_path="src.retriever.backends.faiss.backend",
        filters_module_path="src.retriever.backends.faiss.filters",
    ),
}

KNOWN_FILTER_FIELDS = {
    "tags": "array<string>",
    "created_at": "datetime",
}

# Operators that the service can reliably compile into backend-native filters
# for the primary `where` contract. Other operators remain valid at the API
# level but are enforced in the fallback path against returned metadata.
BACKEND_PUSHDOWN_OPERATORS: dict[str, list[str]] = {
    "vdms": ["gte"],
    "milvus": ["eq", "in", "gte", "lte", "between"],
    "pgvector": ["eq", "in", "gte", "lte", "between"],
    "faiss": ["eq", "in", "gte", "lte", "between"],
}


def list_supported_backends(registry: Mapping[str, BackendSpec] | None = None) -> list[str]:
    """Return sorted list of registered backend names."""
    return sorted((registry or BACKEND_REGISTRY).keys())


def get_backend_name(backend_name: str | None = None) -> str:
    """Resolve effective backend name from explicit value or settings."""
    return (backend_name or settings.RETRIEVER_BACKEND).strip().lower()


def get_backend_spec(
    backend_name: str | None = None,
    registry: Mapping[str, BackendSpec] | None = None,
) -> BackendSpec:
    """Resolve backend spec and raise when backend is unsupported."""
    selected_backend = get_backend_name(backend_name)
    specs = registry or BACKEND_REGISTRY
    spec = specs.get(selected_backend)
    if spec is None:
        supported = ", ".join(list_supported_backends(specs))
        logger.error(
            "Unsupported retriever backend '%s' requested. Supported backends: %s",
            selected_backend,
            supported,
        )
        raise NotImplementedError(
            f"Retriever backend '{selected_backend}' is not implemented. Supported backends: {supported}."
        )
    return spec


def _load_callable(module_path: str, attr_name: str) -> Callable[..., Any]:
    """Import a callable attribute from a module path."""
    logger.debug("Loading backend callable '%s' from '%s'", attr_name, module_path)
    module = import_module(module_path)
    attr = getattr(module, attr_name, None)
    if not callable(attr):
        raise AttributeError(
            f"Module '{module_path}' does not define callable '{attr_name}'."
        )
    return attr


def get_vectordb(
    backend_name: str | None = None,
    registry: Mapping[str, BackendSpec] | None = None,
) -> VectorStoreBackend:
    """Load and return vector backend instance for the selected backend."""
    selected_backend = get_backend_name(backend_name)
    spec = get_backend_spec(selected_backend, registry=registry)
    logger.debug("Retrieving vector store for backend '%s'", selected_backend)
    get_store = _load_callable(spec.backend_module_path, spec.get_vectordb_attr)
    try:
        store = get_store()
    except Exception:
        logger.exception("Retriever backend '%s' failed to initialize", selected_backend)
        raise
    logger.debug("Retriever backend '%s' initialized successfully", selected_backend)
    return store


def clear_vectordb_cache(
    backend_name: str | None = None,
    registry: Mapping[str, BackendSpec] | None = None,
) -> None:
    """Evict the cached vector store so the next call to get_vectordb() reconnects.

    Each backend's ``get_vectordb`` is decorated with ``@lru_cache(maxsize=1)``.
    Calling this clears that cache, forcing a fresh connection on the next query.
    This is used by the service-level retry path to recover from dropped connections.
    """
    selected_backend = get_backend_name(backend_name)
    spec = get_backend_spec(selected_backend, registry=registry)
    get_store = _load_callable(spec.backend_module_path, spec.get_vectordb_attr)
    if hasattr(get_store, "cache_clear"):
        logger.info("Clearing cached vector store for backend '%s'", selected_backend)
        get_store.cache_clear()
        return
    logger.debug(
        "Backend '%s' get_vectordb callable does not expose cache_clear()", selected_backend
    )


def check_ready(
    backend_name: str | None = None,
    registry: Mapping[str, BackendSpec] | None = None,
) -> bool:
    """Execute readiness callable for the selected backend."""
    selected_backend = get_backend_name(backend_name)
    spec = get_backend_spec(selected_backend, registry=registry)
    logger.info("Checking readiness for retriever backend '%s'", selected_backend)
    ready_fn = _load_callable(spec.backend_module_path, spec.check_ready_attr)
    try:
        ready = bool(ready_fn())
    except Exception:
        logger.exception("Retriever backend '%s' readiness check failed", selected_backend)
        raise
    logger.info("Retriever backend '%s' readiness result: %s", selected_backend, ready)
    return ready


def build_filters(
    backend: str | None,
    tags: list[str] | None,
    time_filter: TimeRange | None,
    filters: dict[str, FilterCondition] | None,
    property_name: str = "created_at",
    registry: Mapping[str, BackendSpec] | None = None,
) -> dict[str, Any] | str | None:
    """Build backend-native filter payload from normalized query filters."""
    try:
        spec = get_backend_spec(backend, registry=registry)
    except NotImplementedError as exc:
        raise ValueError(f"Unsupported backend for filter construction: {backend}") from exc

    build_filter_fn = _load_callable(spec.filters_module_path, spec.build_filters_attr)
    return build_filter_fn(
        tags=tags,
        time_filter=time_filter,
        filters=filters,
        property_name=property_name,
    )


def _build_backend_capabilities(backend_name: str) -> BackendFilterCapabilities:
    """Build advertised filter capabilities for one backend."""
    return BackendFilterCapabilities(
        backend=backend_name,
        top_level_fields=["query", "top_k", "where"],
        logical_blocks=list(FILTER_LOGICAL_BLOCKS),
        supported_operators=list(FILTER_OPERATORS),
        pushdown_operators=BACKEND_PUSHDOWN_OPERATORS.get(backend_name, []),
        known_fields=KNOWN_FILTER_FIELDS,
        max_where_depth=MAX_WHERE_DEPTH,
        max_where_clauses=MAX_WHERE_CLAUSES,
        max_where_list_size=MAX_WHERE_LIST_SIZE,
    )


def get_filter_capabilities(
    backend_name: str | None = None,
    registry: Mapping[str, BackendSpec] | None = None,
) -> FilterCapabilitiesResponse:
    """Return filter capabilities for all backends or one selected backend."""
    backend_names = list_supported_backends(registry)
    if backend_name:
        selected = get_backend_name(backend_name)
        if selected not in backend_names:
            supported = ", ".join(backend_names)
            raise NotImplementedError(
                f"Retriever backend '{selected}' is not implemented. Supported backends: {supported}."
            )
        backend_names = [selected]

    capabilities = [_build_backend_capabilities(name) for name in backend_names]
    return FilterCapabilitiesResponse(
        active_backend=get_backend_name(),
        backends=capabilities,
    )
