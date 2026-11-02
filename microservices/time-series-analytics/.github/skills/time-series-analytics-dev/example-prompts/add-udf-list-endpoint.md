Add a new `GET /udfs` endpoint to the Time Series Analytics microservice that lists the UDF deployment packages currently extracted under `/tmp/`, so operators can see what's deployed without shelling into the container.

- Add the route to `src/main.py` alongside the existing routes; return each package's name and whether its `udfs/`, `tick_scripts/`, and `models/` subfolders are present.
- Follow the existing route conventions: FastAPI response model or plain dict, SPDX header already present in the file (don't duplicate it), logging via the module-level `logger`.
- Add unit test coverage in `tests/test_main.py` reusing the existing `client` and `patch_config` fixture pattern.

Validate the application using:
- `./tests/run_tests.sh` (or a direct `pytest tests/test_main.py -k udfs -v` while iterating) passing with the new test included.
- A manual check after `docker compose up -d`: `curl -s http://localhost:5000/udfs` returns the currently-deployed package(s).

Expected results:
- The new route is discoverable in the Swagger UI at `/docs`.
- Coverage report (`/tmp/htmlcov`) shows the new route's lines covered.
- No existing test broken by the change.
