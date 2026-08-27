---
name: time-series-analytics-dev
description: >
  Develop the Time Series Analytics microservice itself (FastAPI + Kapacitor)
  — build and deploy it locally via Docker Compose or Helm, run the mocked
  unit test suite (tests/run_tests.sh) and the slower Docker/Helm end-to-end
  functional suite (tests-functional/), navigate and modify src/main.py
  (routes), src/classifier_startup.py (Kapacitor/UDF lifecycle), and
  src/opcua_alerts.py, and follow this service's release conventions
  (CHANGELOG.md, image-tag bump locations, Dockerfile build args). Use when
  modifying, testing, debugging, or releasing this service's own code. Not
  for merely deploying the prebuilt image to build a new UDF-based use case
  on top of it — that is time-series-analytics-user.
---

# Time Series Analytics — Dev

Work on the service's source. **This skill assumes a repo clone** of
`edge-ai-libraries` with this microservice at
`microservices/time-series-analytics/`; if there is no clone, clone the
repo first.
Run all commands from the microservice root.

## When to Use

- Add, modify, or remove a REST route in `src/main.py`
- Change Kapacitor/UDF lifecycle behavior in `src/classifier_startup.py`
- Run or extend the unit test suite, or the Docker/Helm functional suite
- Build the image from source, debug a running container, or tune GPU/core-pinning behavior
- Cut a release: bump the version consistently across the files that track it

## Example Prompts

Sample problem-solving scenarios this skill handles end-to-end:

| Example | Problem it solves |
|---|---|
| [add-udf-list-endpoint.md](./example-prompts/add-udf-list-endpoint.md) | Add a new REST route with test coverage |
| [debug-udf-not-starting.md](./example-prompts/debug-udf-not-starting.md) | Diagnose a deployed UDF that silently isn't processing data |

## Reference Lookup

| File | Load when… |
|---|---|
| [`references/source-map.md`](./references/source-map.md) | locating where a route, config field, or lifecycle step lives before editing |
| [`references/testing.md`](./references/testing.md) | writing new tests, running a subset, or avoiding the import-time Kapacitor-startup trap |
| [`references/build-and-deploy.md`](./references/build-and-deploy.md) | building the image, GPU/core-pinning setup, Helm deployment |
| [`references/release-conventions.md`](./references/release-conventions.md) | bumping the version, updating CHANGELOG.md, touching Dockerfile build args |

## The one gotcha to know first

`src/main.py` imports `classifier_startup` at module load, and importing
*that* for real starts an actual Kapacitor daemon subprocess. Any test that
imports `main` must mock `classifier_startup` in `sys.modules` **before**
the import — `tests/test_main.py` already does this; reuse its pattern
rather than re-importing `main` fresh in a new test module. Details:
[`references/testing.md`](./references/testing.md).

## Environment setup

```bash
python3 -m venv env && source env/bin/activate
pip install -r requirements.txt -r tests/requirements.txt
```

## Test / verify loop

```bash
./tests/run_tests.sh                       # full unit suite + coverage (see references/testing.md)
PYTHONPATH=./src pytest tests -k <name> -v  # fast iteration on one test
```

Functional (slow — builds the image / stands up Helm):
```bash
cd tests-functional && pip install -r requirements.txt
pytest -q -vv --self-contained-html --html=./test_report/report.html .
```

## Source map (summary)

- `src/main.py` (~900 lines) — every route: ingestion, config, UDF package
  upload/validation, OPC UA alerts. The module-level `config` dict is the
  single source of truth; `POST /config` is the only writer at runtime.
- `src/classifier_startup.py` (~550 lines) — Kapacitor daemon lifecycle:
  rewrites `kapacitor.conf`'s `[udf.functions.*]`/`[[mqtt]]` sections from
  `config`, validates the extracted UDF package's files exist, starts
  `kapacitord` as a subprocess, enables the Kapacitor task via its CLI.
- `src/opcua_alerts.py` (~210 lines) — `asyncua`-based OPC UA client used by
  the `/opcua_alerts` route.
- Full annotated map: [`references/source-map.md`](./references/source-map.md).

## Build & deploy from source

```bash
cd docker && docker compose build && docker compose up -d
```

GPU driver setup, CPU core-pinning (`CORE_PINNING` env var), Helm chart
values, and the `/dev/dri`-mount gotcha on GPU-less hosts:
[`references/build-and-deploy.md`](./references/build-and-deploy.md).

## Debug a running instance

1. `docker logs -f ia-time-series-analytics-microservice` — startup,
   Kapacitor task enable/retry, request logs.
2. `curl -sf http://localhost:5000/health` (503 = Kapacitor daemon not
   running, not just "process not ready").
3. Kapacitor-internal errors aren't in the container's top-level log:
   `docker exec -it ia-time-series-analytics-microservice bash` then
   `cat /tmp/log/kapacitor/kapacitor.log | grep -i error`.

## Contribution gotchas

| Gotcha | Consequence |
|---|---|
| `classifier_startup` starts a real Kapacitor daemon on import | tests must mock it in `sys.modules` before importing `main` (see above) |
| The three UDF names (`config.json`'s `udfs.name`, `.py` filename, `.tick` filename, tick script's `@name()` node) must be identical | a mismatch fails silently at the pipeline level, not loudly — worth checking first when a "deployment succeeded but nothing happens" bug report comes in |
| `kapacitord` runs as a subprocess *inside this same container*, not a sidecar | don't assume container-to-container networking semantics when tracing a startup failure |
| Compose unconditionally mounts `/dev/dri` | fails container startup on hosts with no Intel iGPU — see `references/build-and-deploy.md` |
| A version bump touches `docker/.env`, `helm/values.yaml`, and `README-dockerhub.md` together | see `references/release-conventions.md` — don't bump only one |
| Every new source/config/doc file needs the SPDX header | matches the existing files' `Apache v2 license` / `Copyright (C) 2026 Intel Corporation` / `SPDX-License-Identifier: Apache-2.0` block |
