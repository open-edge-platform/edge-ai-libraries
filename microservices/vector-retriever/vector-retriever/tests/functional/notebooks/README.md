# Backend functional notebooks

These notebooks are the interactive companion to the backend functional suites under `tests/functional`. Each notebook reproduces one backend-specific filter-parity run, but in a step-by-step Jupyter workflow so you can inspect requests, responses, and backend behavior between steps.

They are intentionally self-contained: each notebook is expected to bring up its backend stack, wait for `vector-retriever` readiness, seed the canonical fixture set from `tests/functional/data.py`, verify the service endpoints, execute the filter scenarios, and tear the stack back down.

## How the notebooks map to the functional suites

The notebook set mirrors the current Python suite layout:

| Notebook | Backend | Matching functional suite | Compose overlay | Local retriever port |
| --- | --- | --- | --- | --- |
| `01_vdms_functional_walkthrough.ipynb` | VDMS | `tests/functional/test_vdms_filters.py` | `docker/compose.vdms.yaml` | `6101` |
| `02_milvus_functional_walkthrough.ipynb` | Milvus | `tests/functional/test_milvus_filters.py` | `docker/compose.milvus.yaml` | `6102` |
| `03_pgvector_functional_walkthrough.ipynb` | PGVector | `tests/functional/test_pgvector_filters.py` | `docker/compose.pgvector.yaml` | `6103` |
| `04_faiss_functional_walkthrough.ipynb` | FAISS | `tests/functional/test_faiss_filters.py` | `docker/compose.faiss.yaml` | `6104` |

This mirrors the current functional-test architecture:

- `tests/functional/conftest.py` owns backend lifecycle, readiness polling, seeding, verification, and teardown.
- `tests/functional/data.py` owns the shared fixture documents and filter matrix.
- `tests/functional/filter_assertions.py` owns the shared API-level assertions used across all backends.
- Each backend module (`test_<backend>_filters.py`) selects one backend and reuses the same matrix.

## Prerequisites

Before opening the notebooks, make sure you have:

- A Python `3.11`/`3.12` environment that can import this project.
- The project dependencies installed for the backend you want to exercise, plus Jupyter in that same environment.
- Docker with `docker compose` available.
- Access to launch Jupyter from the repository root:
  `microservices/vector-retriever/vector-retriever`

Launching Jupyter from the service root matters because the notebook flow is expected to use repository-relative compose files such as `docker/compose.yaml` and import helpers from `tests.functional`.

Typical setup from this directory:

```bash
poetry install --only "main,backend-vdms,backend-milvus,backend-pgvector,backend-faiss,dev" --no-root
poetry run jupyter lab
```

If Jupyter is installed outside Poetry, use the same project-aware Python environment and still start it from this directory.

## Backend service expectations

The notebooks are meant to reproduce the live, Docker-backed functional tests rather than mock them. Each notebook should expect:

- `vector-retriever` to be started with `docker compose -f docker/compose.yaml -f docker/compose.<backend>.yaml up -d --build`
- `GET /ready` to return `{"status": "ready"}` before any query checks run
- `POST /query` to see the canonical fixture set after seeding
- `GET /capabilities/filters` to report the active backend and supported operators
- CPU embedding configuration, consistent with the functional suite (`EMBEDDING_DEVICE=CPU`)
- The default embedding model fallback from the suite when `EMBEDDING_MODEL_NAME` is unset (`CLIP/clip-vit-b-32`)

## Notebook workflow

Each notebook should follow the same sequence as `tests/functional/conftest.py` and the backend test modules:

1. **Start services** using the base compose file plus the backend overlay.
2. **Wait for readiness** by polling `GET /ready` until the retriever reports `ready`.
3. **Seed data** by inserting the deterministic documents from `tests/functional/data.py` into the selected backend.
4. **Verify endpoints** before the full matrix run:
   - `GET /ready`
   - `GET /capabilities/filters`
   - `POST /query` seed-visibility check
   - batch-query and `explain_filters` spot checks as needed
5. **Run filter scenarios** from `FILTER_CASES`, covering operator, logical, legacy-alias, and edge-case behavior.
6. **Teardown** with `docker compose ... down -v --remove-orphans` so the next notebook run starts cleanly.

Notes that matter when reproducing the current suite behavior:

- VDMS, Milvus, and FAISS currently need a `vector-retriever` restart after seeding so the running service reloads backend state exactly the way the pytest fixtures do.
- FAISS uses an isolated `FAISS_INDEX_PATH` per run, so cleanup is part of keeping reruns deterministic.
- The notebooks should validate the same API contract as the pytest suite, not backend internals.

## What each notebook covers

- `01_vdms_functional_walkthrough.ipynb`: interactive reproduction of the VDMS filter matrix and API checks.
- `02_milvus_functional_walkthrough.ipynb`: interactive reproduction of the Milvus filter matrix and API checks.
- `03_pgvector_functional_walkthrough.ipynb`: interactive reproduction of the PGVector filter matrix and API checks.
- `04_faiss_functional_walkthrough.ipynb`: interactive reproduction of the FAISS filter matrix and API checks.

Across all four notebooks, the expected scenarios match `tests/functional/data.py`:

- scalar operators such as `eq`, `in`, `contains`, `starts_with`, `gt`, `gte`, `lt`, `lte`, and `between`
- collection operators such as `contains_any` and `contains_all`
- field presence checks with `exists` and `missing`
- logical composition through `all`, `any`, and `not`
- legacy request aliases: `tags`, `time_filter`, and `filters`
- regression-style checks such as zero-result filters, nested `all`, batch queries, `top_k`, and `explain_filters`
- image query input: base64-encoded image search, image with `where` filter, and mutual exclusivity validation with `query`

## Rerun and cleanup guidance

For a clean rerun:

1. Restart the notebook kernel.
2. Rerun the notebook from the first cell so the stack, seed data, and assertions are recreated in order.
3. If a previous run was interrupted, manually tear down the backend stack from the repository root before rerunning.

Example cleanup commands:

```bash
# VDMS
docker compose -f docker/compose.yaml -f docker/compose.vdms.yaml down -v --remove-orphans

# Milvus
docker compose -f docker/compose.yaml -f docker/compose.milvus.yaml down -v --remove-orphans

# PGVector
docker compose -f docker/compose.yaml -f docker/compose.pgvector.yaml down -v --remove-orphans

# FAISS
docker compose -f docker/compose.yaml -f docker/compose.faiss.yaml down -v --remove-orphans
```

If you want the notebook to match the pytest suite as closely as possible, always start from a fully torn-down state instead of reusing containers or seeded data from an earlier session.
