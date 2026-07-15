Update the pytest suite after changing the ingestion pipeline so the change is covered.

- Add or extend tests under tests/ using the existing conftest.py fixtures (mocked MinIO, TestClient) so they run offline.
- Cover the changed endpoint or pipeline path. Add the SPDX header to any new test file.

Validate the change with the Poetry-managed tools:
- `poetry run coverage run --rcfile ./pyproject.toml -m pytest tests`
- `poetry run coverage report -m`
- `poetry run coverage run --rcfile ./pyproject.toml -m pytest tests/test_db.py`
- `poetry run black --check src tests && poetry run isort --check-only src tests`

Expected results:
- New/updated tests pass offline and the measured coverage is reported honestly.
- Lint is clean.
