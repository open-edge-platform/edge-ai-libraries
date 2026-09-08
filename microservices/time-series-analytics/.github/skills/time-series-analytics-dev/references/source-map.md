<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Source Map

## `src/main.py` (~900 lines) — FastAPI app, all routes

| Route | What it does |
|---|---|
| `GET /health` | Proxies Kapacitor's `/kapacitor/v1/ping`; 200 running / 503 not |
| `POST /input` | `DataPoint` (topic/tags/fields/timestamp) -> InfluxDB line protocol -> forwarded to Kapacitor |
| `GET /config` | Returns current in-memory `config` dict; `?restart=true` schedules `restart_kapacitor()` as a background task |
| `POST /config` | Handler `config_file_change`: validates payload (5 KB cap), checks the named UDF package's files exist on disk, writes `config.json`, (re)starts the classifier |
| `POST /udfs/package` | Handler `adds_udf_deployment_package`: multipart tar upload; `_scan_tar` checks for path traversal/symlink/tar-bomb/disallowed extensions, then extracts to `/tmp/<name>/` or `/tmp/$SAMPLE_APP/` |
| `POST /opcua_alerts` | Forwards an arbitrary message to the OPC UA server named in `config["alerts"]["opcua"]`, lazily (re)initializing `OpcuaAlerts` if the target changed |

The module-level `config` dict is the single source of truth the other two
files read from; `POST /config` is the only writer at runtime.

## `src/classifier_startup.py` (~550 lines) — Kapacitor lifecycle

`classifier_startup(config)` is the entry point `main.py` calls
(`start_kapacitor_service` -> here) whenever the classifier needs to
(re)start. In order:

1. `delete_old_subscription` — drops stale InfluxDB subscriptions from a
   prior run.
2. Loads `config/kapacitor_devmode.conf` or `kapacitor.conf` (mode via
   `SECURE_MODE` env var), rewrites its `[udf.functions.<name>]` table from
   `config['udfs']` (prog, args pointing at the extracted UDF `.py`, env:
   `PYTHONPATH`, `MODEL_PATH`, `DEVICE`), and its `[[mqtt]]` block from
   `config['alerts']['mqtt']` if present.
3. `KapacitorClassifier.check_udf_package` — verifies
   `/tmp/<dir_name>/udfs/<name>.py`, `.../tick_scripts/<name>.tick`, and (if
   `udfs.models` is set) a matching file under `.../models/` all exist.
4. `install_udf_package` — `pip install --target` for an optional
   `udfs/requirements.txt`.
5. `start_kapacitor` — spawns `kapacitord` as a subprocess inside this same
   container (not a separate container) and reaps it on exit.
6. `enable_classifier_task` — `kapacitor define`/`kapacitor enable` via the
   Kapacitor CLI once the daemon's port is open, retrying up to 5 times.

`device` resolution (`config['udfs'].get("device")`): `"CPU"/"cpu"` ->
`"auto"`; `"GPU"/"gpu"` or `"GPU:N"/"gpu:N"` passed through as-is; anything
else raises `ValueError`.

## `src/opcua_alerts.py` (~210 lines) — OPC UA client

`OpcuaAlerts` wraps `asyncua` to connect to the server named in
`config["alerts"]["opcua"]["opcua_server"]` and write to the configured
`node_id`/`namespace`. `main.py`'s `/opcua_alerts` route owns the
lazy-(re)initialization logic when the target server/node changes between
calls — that logic lives in the route handler, not in this class.

## Kapacitor itself

Not part of this repo's Python code: the `kapacitor_python` UDF agent
library is vendored at image build time via a sparse git checkout of
`influxdata/kapacitor` (see the `Dockerfile`'s builder stage), and the
`kapacitord` binary is installed from a `.deb` release, not built from
source. If a bug looks like it's inside Kapacitor itself rather than this
service's Python glue, it's out of scope for a code change here.
