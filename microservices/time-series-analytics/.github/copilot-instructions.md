<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Time Series Analytics Microservice — AI agents

## Canonical Instructions

Use this file as the canonical router for coding agents. Keep tool-specific
files such as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and
`.cursor/rules/time-series-analytics.mdc` as short pointers to this file.

## What This Service Is

Time Series Analytics is a FastAPI + Kapacitor microservice for real-time
analysis of time series data through user-defined functions (UDFs) written
in Python, optionally accelerated with the Intel® Extension for
Scikit-learn*. It ingests JSON data points, converts them to InfluxDB line
protocol, and streams them through a Kapacitor TICKscript pipeline that runs
the configured UDF (e.g. anomaly detection), with optional OPC UA alerting.
UDFs can process points individually (stream mode) or in time windows via a
`|window()` TICKscript node (batch mode). A prebuilt image is published as
`intel/ia-time-series-analytics-microservice` on Docker Hub. Deeper user
docs live under [`docs/user-guide/`](../docs/user-guide/); this file is the
agent-facing map.

## Run Interfaces

- Deploy: `cd docker && docker compose up -d` (reads `docker/.env`). Host
  port **5000** maps to the FastAPI app (`src/main.py`); Kapacitor listens
  internally on `KAPACITOR_PORT` (default **9092**).
- The container filesystem is `read_only: true` in compose — only `/tmp`
  (a tmpfs volume) is writable, which is where UDF deployment packages get
  extracted.
- GPU use mounts `/dev/dri` and requires the host's `render` group GID to be
  in `group_add` (values for Ubuntu 20.04/22.04/24.04 are pre-listed).
- Helm chart under [`helm/`](../helm/) for Kubernetes deployment.
- Unit tests: `./tests/run_tests.sh` (creates a venv, installs
  `requirements.txt` + `tests/requirements.txt`, runs Pytest with coverage).
- Functional tests: `cd tests-functional && pip3 install -r
  requirements.txt && pytest -q -vv --self-contained-html
  --html=./test_report/report.html .` (exercises the Docker and Helm
  deployments end-to-end).

## API Surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Proxies Kapacitor's `/kapacitor/v1/ping`; 200 running / 503 not running |
| POST | `/input` | Ingest a data point (JSON) → InfluxDB line protocol → Kapacitor |
| GET | `/config` | Current `udfs`/`alerts` config; `?restart=true` schedules a background Kapacitor restart |
| POST | `/config` | Replace config (≤5 KB payload); validates UDF deployment package files exist |
| POST | `/udfs/package` | Upload a `.tar` UDF deployment package (multipart `file` field) |
| POST | `/opcua_alerts` | Forward an alert message to the configured OPC UA server |

Full schema: [`docs/user-guide/api-reference.md`](../docs/user-guide/api-reference.md)
and [`_assets/openapi.json`](../docs/user-guide/_assets/openapi.json).

## Repository Map

| Path | Contents |
|---|---|
| `src/main.py` | FastAPI app + all routes (~900 lines): ingestion, config, UDF package upload, OPC UA. |
| `src/classifier_startup.py` | Kapacitor UDF task lifecycle: start/stop/deploy TICKscripts. |
| `src/opcua_alerts.py` | OPC UA client used to forward alerts (`asyncua`). |
| `udfs/temperature_classifier.py` | Sample UDF (Kapacitor Python UDF agent) — anomaly classification example. |
| `tick_scripts/temperature_classifier.tick` | Sample TICKscript wiring the UDF into a Kapacitor stream task. |
| `config.json` | Active UDF/alert configuration loaded at startup. |
| `config/kapacitor*.conf` | Kapacitor daemon configuration (prod / devmode). |
| `docker/` | `docker-compose.yml`, `.env`, `run.sh`, `detect-cores.sh`. |
| `helm/` | Helm chart for Kubernetes deployment. |
| `simulator/temperature_input.py` | Sample data generator posting to `/input`. |
| `tests/` | Pytest unit suite (`run_tests.sh`, coverage via `.coveragerc`). |
| `tests-functional/` | End-to-end Pytest suite against Docker/Helm deployments. |
| `docs/user-guide/` | get-started, how-it-works, how-to-configure, how-to-access-api, api-reference. |

## Tech Stack

Python 3.13, FastAPI + Uvicorn, Kapacitor 1.8.6 (TICKscript engine; its
Python UDF agent is vendored at image build time via a sparse git checkout
of `influxdata/kapacitor`, not pip-installed), InfluxDB line protocol,
`asyncua` for OPC UA, Intel® Extension for Scikit-learn* for UDF
acceleration, Docker Compose / Helm for deployment.

## Conventions

- Run commands from this microservice's root unless a doc says otherwise.
- Every new source/config/doc file carries the repo SPDX header
  (`SPDX-FileCopyrightText: (C) 2026 Intel Corporation` /
  `SPDX-License-Identifier: Apache-2.0`).
- A UDF deployment package is a `.tar` with a required `udfs/` folder
  (at least one `.py`) and `tick_scripts/` folder (at least one `.tick`);
  `models/` is optional. Allowed member extensions are a fixed allowlist
  (`.py .tick .txt .cb .pkl .json .joblib .xml .bin .onnx .pt .pth`).
- `GET /health` reports Kapacitor daemon health (it may be 503 until after a successful `POST /config` starts Kapacitor on a fresh volume). Use it to confirm processing readiness; `POST /udfs/package` and `POST /config` can still be used while `/health` is 503.
- Destructive operations (`docker compose down -v`, deleting the tmpfs
  volume) need explicit user confirmation.

## Skills

Reusable workflow skills live under [`.github/skills/`](skills/). Use
[`skills-catalog.json`](skills/skills-catalog.json) to pick the relevant skill,
then read that skill's `SKILL.md`.

| User intent | Skill |
|---|---|
| Build a new UDF-based use case on the deployed service (consume it) | `time-series-analytics-user` |
| Build from source, run tests, navigate/modify the code, cut a release | `time-series-analytics-dev` |

## Skill Loading Rules

- Load only the skill needed for the current request.
- Open a skill's linked docs or `references/` files only when its `SKILL.md`
  points to them.
- Run commands yourself when the harness permits it and relay the result.

## Path Conventions

All paths in the skill catalog are relative to this microservice's root
(`microservices/time-series-analytics/`). The skills live in
`.github/skills` as the shared location for Codex, Copilot CLI, Claude
Code, Cursor, and local agent scripts. Skills also work without a repo
clone — the `-user` skill fetches the same compose files and templates from
GitHub and uses the prebuilt image.

## Gotchas

- `/health` reflects the Kapacitor daemon's health, not the FastAPI
  process — a 200 from `/health` does not guarantee the UDF pipeline is
  correctly configured.
- `GET /config?restart=true` returns the **pre-restart** config; the
  restart itself runs as a background task after the response is sent.
- `POST /config` payloads are capped at 5 KB; `POST /udfs/package` uploads
  are capped by `UDF_MAX_FILE_SIZE_MB` (default 100 MB).
- Uploaded tar archives are security-scanned before extraction (path
  traversal, symlinks, encrypted payloads, tar-bomb expansion, disallowed
  extensions) — a well-formed tar can still be rejected on these grounds.
- Extraction destination depends on the `SAMPLE_APP` env var: if set,
  files land in `/tmp/<SAMPLE_APP>/`; otherwise `/tmp/<tar_filename>/`.
- `KAPACITOR_LOGGING_LEVEL` controls both the FastAPI app's and Kapacitor's
  log verbosity.
- A batch UDF (`info.wants = BATCH`) paired with a `|window()` TICKscript
  node will silently receive no data if the tick script omits `|window()`;
  conversely, a stream UDF (`info.wants = STREAM`) paired with `|window()`
  will cause Kapacitor to error on task enable.
