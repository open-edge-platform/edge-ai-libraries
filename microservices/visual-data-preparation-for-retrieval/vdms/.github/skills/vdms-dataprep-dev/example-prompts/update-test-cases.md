Update the pytest suite after changing the ingestion pipeline so the change is covered and the 80% coverage gate still passes.

- Add or extend tests under tests/ using the existing conftest.py fixtures (mocked MinIO, TestClient) so they run offline.
- Cover the changed endpoint or pipeline path. Add the SPDX header to any new test file.

Validate the change using the sanctioned entrypoint:
- source ./setup.sh test            (full suite + coverage gate)
- source ./setup.sh test tests/test_db.py   (single file while iterating)
- source ./setup.sh lint            (black + isort; add -a to apply)

Expected results:
- New/updated tests pass offline; total coverage stays at or above 80% so the gate does not fail.
- Lint is clean.
