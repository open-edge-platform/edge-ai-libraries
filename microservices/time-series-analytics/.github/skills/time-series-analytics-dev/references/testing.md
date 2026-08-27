<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Testing — Time Series Analytics

Two independent suites: fast mocked unit tests, and slow end-to-end tests
that actually stand up the service via Docker or Helm.

## Unit tests (`tests/`)

```bash
./tests/run_tests.sh
```

This creates a venv, installs `requirements.txt` + `tests/requirements.txt`,
runs pytest twice (once verbose to `/tmp/report.txt`, once with coverage
summary to `/tmp/unit-test-results.txt`), and writes an HTML coverage report
to `/tmp/htmlcov`. To iterate faster while editing, activate the venv once
and run pytest directly:

```bash
source env/bin/activate
PYTHONPATH=./src python3 -m pytest tests -v
PYTHONPATH=./src python3 -m pytest tests -k test_health_check -v
```

`tests/pytest.ini` sets `asyncio_mode = auto`; `tests/.coveragerc` scopes
coverage to `src` and excludes `tests/`/`env/`.

### The import-time trap

`tests/test_main.py` mocks `classifier_startup` in `sys.modules` **before**
`import main` — `main.py` imports `classifier_startup` at module load, and
without the mock, importing it for real would try to start an actual
Kapacitor daemon:

```python
sys.modules["classifier_startup"] = mock.Mock()
import main
client = TestClient(main.app)
```

Any new test module that imports `main` needs the same guard, or needs to
reuse `test_main.py`'s already-imported `client`/`main` rather than
re-importing.

### Test conventions already in the suite

| File | Coverage | Pattern worth reusing |
|---|---|---|
| `test_main.py` | All FastAPI routes | `patch_config` autouse fixture resets `main.config` before each test; `monkeypatch` for `requests`/`os.environ` |
| `test_classifier_startup.py` | Kapacitor lifecycle, UDF package checks, device resolution | Hand-rolled `DummyLogger` (records `(level, message)` tuples) instead of mocking the logging module — assert against `logger.messages` |
| `test_opcua_alerts.py` | `OpcuaAlerts` client, `/opcua_alerts` route | `pytest-asyncio` for the async OPC UA client methods; `AsyncMock` for the `asyncua` client itself |

## Functional tests (`tests-functional/`)

```bash
cd tests-functional
pip3 install -r requirements.txt
pytest -q -vv --self-contained-html --html=./test_report/report.html .
```

These actually build the Docker image, bring it up (`test_docker.py`,
port 5000) or install the Helm chart (`test_helm.py`, release name
`time-series-analytics-microservice`, namespace `apps`, port 30002), then
exercise the REST API end-to-end via `rest_api_utils.py` helpers. Both
modules `pytest.skip` if the expected `../` microservice directory isn't
found — they assume they're run from inside a checkout, not standalone.
Expect these to be slow (image build + container/Helm bring-up); don't run
them for every small change, but do run the relevant one before a release
or after touching `docker/`, `helm/`, or the REST routes.

## Adding a test for a new route or config field

1. Add it to `tests/test_main.py`, reusing the existing `client` and
   `patch_config` fixture rather than building a new `TestClient`.
2. If it touches Kapacitor lifecycle (new config key affecting
   `classifier_startup`), add coverage in `tests/test_classifier_startup.py`
   using the `DummyLogger` pattern rather than mocking `logging` directly.
3. Run `./tests/run_tests.sh` and check `/tmp/htmlcov` for lines you added
   that coverage didn't reach.
4. Only extend `tests-functional/` if the change is observable from outside
   the container (a new route's actual HTTP behavior, a new deploy-time
   config option) — internal refactors don't need it.
