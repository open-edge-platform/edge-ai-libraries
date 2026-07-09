# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys
import types
from functools import lru_cache

import pytest

from src.retriever import backend_factory


@pytest.fixture(autouse=True)
def restore_backend_setting(monkeypatch):
    """Reset backend setting to default before each test."""
    monkeypatch.setattr(backend_factory.settings, "RETRIEVER_BACKEND", "vdms")


def test_check_ready_raises_for_unsupported_backend(monkeypatch):
    """Ensure unsupported backends fail readiness checks explicitly."""
    monkeypatch.setattr(backend_factory.settings, "RETRIEVER_BACKEND", "not-real")

    with pytest.raises(NotImplementedError):
        backend_factory.check_ready()


def test_factory_dispatches_to_registered_backend(monkeypatch):
    """Ensure factory delegates to callable paths declared in registry."""
    module_name = "tests._fake_backend_module"

    fake_module = types.SimpleNamespace(
        get_vectordb=lambda: {"name": "fake-store"},
        check_ready=lambda: True,
    )

    monkeypatch.setitem(sys.modules, module_name, fake_module)
    monkeypatch.setattr(
        backend_factory,
        "BACKEND_REGISTRY",
        {
            "fake": backend_factory.BackendSpec(
                backend_module_path=module_name,
                filters_module_path="tests._fake_filters_module",
            )
        },
    )
    monkeypatch.setattr(backend_factory.settings, "RETRIEVER_BACKEND", "fake")

    assert backend_factory.get_vectordb() == {"name": "fake-store"}
    assert backend_factory.check_ready() is True


def test_clear_vectordb_cache_dispatches_to_registered_backend(monkeypatch):
    """Cache clearing should call the registered backend's cached factory."""
    module_name = "tests._fake_cached_backend_module"
    instance_counter = {"count": 0}

    @lru_cache(maxsize=1)
    def cached_vectordb():
        instance_counter["count"] += 1
        return {"instance": instance_counter["count"]}

    fake_module = types.SimpleNamespace(
        get_vectordb=cached_vectordb,
        check_ready=lambda: True,
    )

    monkeypatch.setitem(sys.modules, module_name, fake_module)
    monkeypatch.setattr(
        backend_factory,
        "BACKEND_REGISTRY",
        {
            "fake": backend_factory.BackendSpec(
                backend_module_path=module_name,
                filters_module_path="tests._fake_filters_module",
            )
        },
    )
    monkeypatch.setattr(backend_factory.settings, "RETRIEVER_BACKEND", "fake")

    assert backend_factory.get_vectordb() == {"instance": 1}
    assert backend_factory.get_vectordb() == {"instance": 1}

    backend_factory.clear_vectordb_cache()

    assert backend_factory.get_vectordb() == {"instance": 2}


def test_filter_capabilities_include_primary_where_contract():
    """Capabilities should advertise primary where contract and operators."""
    capabilities = backend_factory.get_filter_capabilities()
    assert capabilities.backends
    first_backend = capabilities.backends[0]
    assert "where" in first_backend.top_level_fields
    assert "all" in first_backend.logical_blocks
    assert "any" in first_backend.logical_blocks
    assert "not" in first_backend.logical_blocks
    assert "contains_any" in first_backend.supported_operators
    assert "between" in first_backend.supported_operators


def test_filter_capabilities_can_be_scoped_to_single_backend():
    """Capabilities endpoint wrapper should support per-backend queries."""
    capabilities = backend_factory.get_filter_capabilities("milvus")
    assert len(capabilities.backends) == 1
    assert capabilities.backends[0].backend == "milvus"


def test_filter_capabilities_advertise_backend_specific_pushdown():
    """Shared grammar should still expose backend-specific pushdown behavior."""
    capabilities = backend_factory.get_filter_capabilities()
    by_backend = {backend.backend: backend for backend in capabilities.backends}

    assert by_backend["vdms"].pushdown_operators == ["gte"]
    assert by_backend["milvus"].pushdown_operators == ["eq", "in", "gte", "lte", "between"]
    assert by_backend["pgvector"].pushdown_operators == ["eq", "in", "gte", "lte", "between"]
    assert by_backend["faiss"].pushdown_operators == ["eq", "in", "gte", "lte", "between"]

    reference = by_backend["milvus"]
    for backend_name in ("vdms", "pgvector", "faiss"):
        backend = by_backend[backend_name]
        assert backend.top_level_fields == reference.top_level_fields
        assert backend.logical_blocks == reference.logical_blocks
        assert backend.supported_operators == reference.supported_operators
        assert backend.known_fields == reference.known_fields
