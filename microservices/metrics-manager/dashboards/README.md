<!--
Copyright (C) 2025-2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# TCMI hardware telemetry — Grafana + Prometheus

This is the Grafana side of the TCMI → Metrics Manager work (P3 in
`docs/TCMI-INTEGRATION-PROPOSAL.md`). The point is simple: instead of SSHing in and reading numbers off
a `curl` of the metrics endpoint, you get a live dashboard. Prometheus scrapes the Metrics Manager's
`:9273`, and Grafana reads Prometheus.

The dashboard is laid out in five rows:

| Row | What's in it | Some of the panels |
|-----|--------------|--------------------|
| **T** | Thermal & power | CPU package/DRAM power, **platform (psys) power**, CPU/NVMe/board temps, NPU power |
| **C** | Compute | CPU/GPU/NPU busy %, per-core & GPU frequency, per-engine GPU util |
| **M** | Memory | **DRAM bandwidth (read/write/total)**, RAM used/available |
| **I** | I/O | disk util %, disk & network throughput, **per-device IRQ rate** |
| **R** | Real-time determinism *(new)* | C0-state residency; IPC / SMI (turbostat, opt-in) |

The **bold** panels are things MM couldn't show before this work — psys power, DRAM bandwidth, the IRQ
rates, and the whole R row.

## What's in this folder

| File | What it is |
|------|------------|
| `generate_dashboard.py` | Generates the dashboard JSON. This is where the "old TCMI name → new MM name" mapping lives, plus all the panel layout math. |
| `tcmi-hardware-telemetry.json` | The generated dashboard (uid `tcmi-mm-unified-v1`, 31 panels). |
| `prometheus-scrape-job.yml` | The scrape block to drop into your `prometheus.yml` so Prometheus pulls from MM's `:9273`. |

If you need to point the dashboard at a different Prometheus datasource, regenerate it rather than
hand-editing the JSON:

```bash
python3 dashboards/generate_dashboard.py --ds-uid <YOUR_PROM_DS_UID>
```

## Getting it running

### 1. Tell Prometheus about MM

Copy the block from `prometheus-scrape-job.yml` into `scrape_configs:` in your `prometheus.yml`, then
reload (or restart) Prometheus:

```bash
curl -s -X POST http://<prometheus>:9090/-/reload   # only works if Prometheus was started with --web.enable-lifecycle
# no lifecycle flag? just: docker restart <prometheus-container>
```

Give it a scrape interval or two, then check the `metrics-manager` target is green on Prometheus'
`/targets` page. One thing that trips people up: if Prometheus runs in a container and MM runs on the
host, MM is reached as `host.docker.internal:9273` — and that name only resolves if the Prometheus
service has `extra_hosts: ["host.docker.internal:host-gateway"]`. If MM is on the same Docker network,
just use its service name (`metrics-manager:9273`).

### 2. Load the dashboard into Grafana

**Easiest if you're doing GitOps — file provisioning.** Drop the JSON into a folder Grafana
provisions and it loads on its own (and stays in sync):

```bash
cp tcmi-hardware-telemetry.json /path/to/grafana/dashboards/
```

The dashboard's default datasource UID is `PBFA97CFB590B2093` (that's what the reference stack uses).
If yours is different, regenerate with `--ds-uid` (see above).

**No filesystem access to Grafana? Use the HTTP API instead:**

```bash
FID=$(curl -s -u <user>:<pass> http://<grafana>/api/folders \
        -H 'Content-Type: application/json' \
        -d '{"title":"TCMI Hardware Telemetry"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
python3 - <<PY
import json
d=json.load(open("tcmi-hardware-telemetry.json")); d.pop("id",None)
json.dump({"dashboard":d,"folderId":$FID,"overwrite":True}, open("/tmp/imp.json","w"))
PY
curl -s -u <user>:<pass> -X POST http://<grafana>/api/dashboards/db \
     -H 'Content-Type: application/json' --data-binary @/tmp/imp.json
```

## A couple of things worth knowing

- **Counters vs gauges.** `diskio_*`, `net_bytes_*`, and `interrupts_total` count up forever, so the
  dashboard wraps them in `rate(...[1m])`. Power, temperature, frequency, DRAM bandwidth, and memory
  are plain gauges and get queried directly. If a panel ever shows a line that only climbs, that's the
  tell you forgot the `rate()`.
- **The host dropdown.** Every panel filters on a `$host` variable, which is populated from
  `label_values(mem_used_percent, host)`.
- **"No data" on the R row is normal** unless you've turned turbostat on (`ENABLE_TURBOSTAT=true`,
  which needs the kernel-matched `linux-tools`). The C0-residency panel is the exception — that one's
  always live from `intel_powerstat`.
