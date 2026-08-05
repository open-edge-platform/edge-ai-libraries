Update the pytest suite after changing a current ingestion, backend, or
observability path.

- Add or extend the closest focused test module under `tests/`.
- Mock model, network, vector-store, and storage boundaries for unit tests.
- Reset cached storage/vector-store factories when changing backend settings.
- Use `MILVUS_IT_URI` only for the opt-in real-Milvus integration test.
- Add the SPDX header to new test files.

Validate with:

- `poetry run python -m pytest <focused-test-files>`
- `poetry run coverage run --rcfile ./pyproject.toml -m pytest tests`
- `poetry run coverage report -m`
- `poetry run black --check src tests`
- `poetry run isort --check-only src tests`

Report pre-existing collection failures separately. In the current checkout,
the legacy `test_db.py` and `test_prep_data.py` files still reference removed
modules and must not be presented as tests of the new backend architecture.
