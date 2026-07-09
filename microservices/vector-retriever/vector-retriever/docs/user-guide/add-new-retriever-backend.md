# Add New Retriever Backend

This guide explains how to add a new vector database backend to the retriever service.

## Design contract

Each backend owns two modules under `src/retriever/backends/<backend_name>/`:

- `backend.py`
  - `get_vectordb()`
  - `check_ready()`
- `filters.py`
  - `build_filters(tags, time_filter, filters, property_name)`

The backend registry (`src/retriever/backends/registry.py`) dynamically loads these callables and advertises backend filter capabilities.

The runtime calls `similarity_search_with_score(query, k, fetch_k=..., filter=...)` on the object returned by `get_vectordb()`. For image queries, the runtime calls `similarity_search_with_score_by_vector(embedding, k, ...)` with a pre-computed embedding vector. The filter keyword varies by backend (`filter` for most, `expr` for Milvus).

## Step-by-step

1. Create a backend folder from template.

```bash
cp -r src/retriever/backends/_template src/retriever/backends/<backend_name>
```

2. Implement vector store wiring in `backend.py`.

    Required behavior:

    - Return an object implementing `similarity_search_with_score(query, k, **kwargs)` and `similarity_search_with_score_by_vector(embedding, k, **kwargs)`.
    - Ensure compatibility with keyword arguments used by the service (`fetch_k`, `filter` or `expr`).
    - Perform lazy imports for optional dependencies.
    - Raise clear `ImportError` messages when an optional package is missing.
    - Use `@lru_cache(maxsize=1)` where appropriate to avoid repeated client initialization.

3. Implement filter translation in `filters.py`.

    Map these inputs to backend-native filters:

    - `tags`
    - `time_filter`
    - dynamic `filters` (`eq`, `in`, `gte`, `lte`, `between`)

    Return one of:

    - `dict` for document-style filters
    - `str` for expression-style filters (for example Milvus `expr`)
    - `None` when no filters apply

    > **_NOTE:_** The primary request grammar is `where`. Backends currently receive a pushdown-safe subset translated into `tags`, `time_filter`, and legacy `filters`; unsupported clauses are handled in the service fallback path.

4. Register backend in `src/retriever/backends/registry.py`.

    Add a `BACKEND_REGISTRY` entry:

    ```python
    "<backend_name>": BackendSpec(
        backend_module_path="src.retriever.backends.<backend_name>.backend",
        filters_module_path="src.retriever.backends.<backend_name>.filters",
    )
    ```

    Update `BACKEND_PUSHDOWN_OPERATORS` in `src/retriever/backends/registry.py` for the new backend.

5. Add environment variables in `src/common/settings.py`.
    Include connection and backend-specific tuning fields.

6. Add dependency group in `pyproject.toml`.
    Follow current pattern using `backend-<backend_name>` groups.

7. Add compose overlay file `docker/compose.<backend_name>.yaml` for local stack bring-up and functional tests.

8. Update backend-aware startup wiring in `setup.sh` and `docker/Dockerfile`.

    - `setup.sh`: backend validation list, required env checks (`validate_required_env_vars`), optional `--up-with-<backend_name>` flow, and any backend-specific `.env` defaults.
    - `docker/Dockerfile`: allow `RETRIEVER_BACKEND=<backend_name>` in the backend allowlist used during poetry install.

9. Update API and user-facing docs.

    - Update OpenAPI schema in `docs/user-guide/api-docs/openapi.yaml` for any request/response/filter capability changes.
    - Update user guides that mention supported backends, required env vars, and startup flows.

10. Add tests.

    Minimum unit coverage:

    - registry dispatch for new backend
    - filter translation behavior for supported pushdown operators
    - readiness path (or controlled mock)
    - request/schema and service compatibility when applicable

    Existing unit examples:

    - `tests/test_backend_factory.py`
    - `tests/test_filters.py`
    - `tests/test_schema.py`
    - `tests/test_service.py`

    Functional coverage:

    - Create `tests/functional/test_<backend_name>_filters.py` with a `backend_name` fixture and call `assert_filter_matrix`.
    - Add per-backend port configuration in `tests/functional/conftest.py` (`PORT_MAP`).
    - Ensure `docker/compose.<backend_name>.yaml` exists and supports seeded test data setup.

11. Validate.

    ```bash
    poetry install --only "main,backend-<backend_name>,dev" --no-root
    PYTHONPATH=. poetry run pytest -q tests --ignore=tests/functional
    ```

12. Run backend functional checks (manual run):

    ```bash
    RUN_FUNCTIONAL_BACKEND_TESTS=1 PYTHONPATH=. poetry run pytest -q tests/functional/test_<backend_name>_filters.py
    ```

## Implementation checklist

    [ ] backend folder created
    [ ] `backend.py` implemented
    [ ] `filters.py` implemented
    [ ] registry updated
    [ ] settings updated
    [ ] dependency group updated
    [ ] compose overlay added (`docker/compose.<backend_name>.yaml`)
    [ ] setup and Docker backend allowlists updated
    [ ] OpenAPI schema updated (`docs/user-guide/api-docs/openapi.yaml`)
    [ ] tests added/updated
    [ ] docs updated

## Common pitfalls

- Not translating filters to backend-native syntax correctly
- Not updating backend pushdown operator capabilities in `registry.py`
- Missing optional dependency guards
- Forgetting to register backend in registry
- Missing compose overlay and functional-test port map entry
- Forgetting to update `docs/user-guide/api-docs/openapi.yaml` after request/response changes
- Missing `MULTIMODAL_EMBEDDING_ENDPOINT`/`EMBEDDINGS_ENDPOINT` and `EMBEDDING_MODEL_NAME` at runtime
- Inconsistent score/filter behavior across backends

## Supporting Resources

- [Overview and Architecture](overview-architecture.md)
- [API Reference](api-reference.md)
- [Retriever backend source notes](../../src/retriever/backends/README.md)
