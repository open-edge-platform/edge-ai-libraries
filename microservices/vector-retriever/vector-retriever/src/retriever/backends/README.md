# Retriever Backends

The `backends/` package is the primary extension point for vector database support.

## Layout

Each backend lives in its own folder:

- `backend.py`: vector store wiring (`get_vectordb`, `check_ready`)
- `filters.py`: query filter translation (`build_filters`)
- `__init__.py`: lightweight re-exports

Current backends:

- `vdms`
- `milvus`
- `pgvector`
- `faiss`

## Add a New Backend

For a comprehensive step-by-step guide, see [Add New Retriever Backend](../../../docs/user-guide/add-new-retriever-backend.md).

Quick start:

1. Copy `backends/_template` to `backends/<backend_name>`.
2. Implement `get_vectordb()` and `check_ready()` in `backend.py`.
3. Implement `build_filters(...)` in `filters.py`.
4. Add `<backend_name>` to `BACKEND_REGISTRY` in `registry.py`.
5. Add tests for:
   - factory dispatch
   - filter translation behavior

`build_filters(...)` receives the pushdown-safe subset of the normalized request filters; any
unsupported clauses are enforced later in the service fallback path.

This folder is now the single source of truth for backend-specific code.
