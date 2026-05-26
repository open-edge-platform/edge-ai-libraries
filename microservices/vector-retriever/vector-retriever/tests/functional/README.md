# Backend Functional Test Suite

This suite validates retrieval filtering behavior across all vector backends:

- `vdms`
- `milvus`
- `pgvector`
- `faiss`

## Structure

- `conftest.py`: Docker lifecycle, readiness, seeding, teardown.
- `data.py`: canonical fixture documents and exhaustive filter cases.
- `filter_assertions.py`: shared matrix assertion helper.
- `test_vdms_filters.py`: VDMS-specific module.
- `test_milvus_filters.py`: Milvus-specific module.
- `test_pgvector_filters.py`: PGVector-specific module.
- `test_faiss_filters.py`: FAISS-specific module.

To add a new backend later, add one new `test_<backend>_filters.py` file with a `backend_name` fixture and reuse the `@pytest.mark.parametrize` pattern with `FILTER_CASES` and the API-level assertion helpers.

## What It Covers

- Brings up backend stack with Docker Compose overlay per backend.
- Waits for `vector-retriever` readiness.
- Seeds deterministic fixture documents directly into the active backend store.
- Verifies seeded records are visible from the API before filter assertions.
- Executes exhaustive filter matrix through `POST /query`.
- Verifies matched `video_id` sets per filter case.

MME is forced to CPU for this suite (`EMBEDDING_DEVICE=CPU`).

Filter coverage includes:

- Operators: `eq`, `in`, `contains`, `starts_with`, `gt`, `gte`, `lt`, `lte`, `between`, `contains_any`, `contains_all`, `exists`, `missing`
- Logical composition: `all`, `any`, `not` (including `not` at top-level and nested `all`)
- Legacy aliases: `tags`, `time_filter`, `filters`
- Edge cases: zero-result filter, time range via `where`, nested `all`

API-level assertions per backend:

- `GET /ready` → `{"status": "ready"}`
- `GET /capabilities/filters` → active backend present, operator lists populated
- Batch query → 2 queries in one request, both results correct
- `explain_filters=True` → `compiled_backend_filter` present in response
- `top_k` limiting → `top_k=2` returns exactly 2 items
- Image query → base64 image input returns results; image with `where` filter works; mutual exclusivity with `query` returns `422`

## Run

```bash
cd microservices/vector-retriever/vector-retriever
RUN_FUNCTIONAL_BACKEND_TESTS=1 PYTHONPATH=. poetry run pytest -q tests/functional
```

By default these tests are skipped unless `RUN_FUNCTIONAL_BACKEND_TESTS=1` is set.
This suite is intended for manual execution.
When `EMBEDDING_MODEL_NAME` is unset, the suite defaults it to `CLIP/clip-vit-b-32`.

## Notes

- This suite is intentionally heavyweight because each backend stack is started with `docker compose up -d --build`.
- Per-backend port and index-name isolation is used to avoid collisions.
- FAISS uses a unique `FAISS_INDEX_PATH` per run and stack teardown uses `docker compose down -v --remove-orphans` to clean test collateral.
