# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Thin wrappers around the shared backend registry for the active retriever."""

from src.common.settings import settings
from src.common.schema import FilterCapabilitiesResponse
from src.retriever.backends.registry import (
    BACKEND_REGISTRY,
    check_ready as _check_ready,
    clear_vectordb_cache as _clear_vectordb_cache,
    get_filter_capabilities as _get_filter_capabilities,
    get_backend_spec as _get_backend_spec,
    get_vectordb as _get_vectordb,
)
from src.retriever.backends.base import BackendSpec, VectorStoreBackend


def get_backend_spec(backend_name: str | None = None) -> BackendSpec:
    """Resolve backend metadata from the shared registry."""
    return _get_backend_spec(backend_name, registry=BACKEND_REGISTRY)


def get_vectordb() -> VectorStoreBackend:
    """Create (or retrieve cached) vector store client for active backend."""
    return _get_vectordb(settings.RETRIEVER_BACKEND, registry=BACKEND_REGISTRY)


def clear_vectordb_cache() -> None:
    """Evict the cached vector store, forcing reconnection on next call.

    Use this when a backend connection has been lost so that the next
    ``get_vectordb()`` call recreates the client against the (restarted) backend.
    """
    _clear_vectordb_cache(settings.RETRIEVER_BACKEND, registry=BACKEND_REGISTRY)


def check_ready() -> bool:
    """Run backend readiness checks for the configured backend."""
    return _check_ready(settings.RETRIEVER_BACKEND, registry=BACKEND_REGISTRY)


def get_filter_capabilities(backend_name: str | None = None) -> FilterCapabilitiesResponse:
    """Return filter capabilities for all backends or one selected backend."""
    return _get_filter_capabilities(backend_name=backend_name, registry=BACKEND_REGISTRY)
