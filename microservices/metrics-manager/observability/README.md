<!--
Copyright (C) 2025-2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Convenience observability stack (Prometheus + Grafana)

Metrics Manager exposes metrics on `:9273` but does **not** bundle Prometheus or
Grafana. This optional stack stands both up, **pre-wired** so the shipped TCMI
dashboard works with zero manual setup:

* Prometheus is configured to scrape MM on `:9273`.
* Grafana auto-provisions the Prometheus datasource with the **exact UID**
  (`PBFA97CFB590B2093`) the dashboard expects — so no regeneration, no UID lookup.
* The dashboard JSON (`../dashboards/tcmi-hardware-telemetry.json`) is
  auto-loaded on startup.

It runs as a separate compose project, so it never collides with the main
`make up` / `compose.yaml`.

## Usage

```bash
# From the metrics-manager directory:

# 1. Make sure Metrics Manager is already running (exposes :9273)
make up

# 2. Bring up Prometheus + Grafana
docker compose -f observability/compose.yaml up -d

# 3. Open the dashboard
#    Grafana:    http://localhost:3000        (login: admin / admin)
#    Dashboard:  http://localhost:3000/d/tcmi-mm-unified-v1
#    Prometheus: http://localhost:9091/targets  (metrics-manager should be UP)

# Tear down (keeps stored data in named volumes):
docker compose -f observability/compose.yaml down

# Tear down and wipe stored metrics/dashboard state:
docker compose -f observability/compose.yaml down -v
```

> Run the command **from the `metrics-manager` directory** (not from inside
> `observability/`) so compose reads the parent `.env` — that's how corporate
> proxy settings reach the Prometheus/Grafana containers.

## Ports

| Service | Host port | Why |
|---|---|---|
| Grafana | `3000` | UI |
| Prometheus | `9091` | its own `9090` clashes with MM's API on the host, so it's mapped to `9091` |

## What's in here

| File | Purpose |
|---|---|
| `compose.yaml` | The Prometheus + Grafana services |
| `prometheus.yml` | Scrape config (the `metrics-manager` job → `:9273`) |
| `grafana/provisioning/datasources/prometheus.yml` | Datasource with the pinned UID |
| `grafana/provisioning/dashboards/tcmi.yml` | Tells Grafana to load `../dashboards/*.json` |

## Customizing

* **Different Grafana password:** set `GRAFANA_ADMIN_PASSWORD` in `.env` (or your
  shell) before `up`.
* **MM on the same docker network instead of the host:** change the target in
  `prometheus.yml` from `host.docker.internal:9273` to `metrics-manager:9273` and
  attach both stacks to the same network.
* **Changed the dashboard's datasource UID:** keep the datasource `uid` in
  `grafana/provisioning/datasources/prometheus.yml` in sync with
  `DEFAULT_DS_UID` in `../dashboards/generate_dashboard.py`.
