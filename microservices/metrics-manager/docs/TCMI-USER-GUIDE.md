<!--
Copyright (C) 2025-2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# TCMI Hardware Telemetry in Metrics Manager — End-User Guide

## 1. Overview

**TCMI** stands for **T**hermal · **C**ompute · **M**emory · **I/O** — the four
"envelopes" of hardware behaviour that matter for robotics, Edge AI, and
physical-AI workloads on Intel platforms. TCMI was originally a separate pile of
Python scripts that read Intel hardware telemetry (power, temperatures, memory
bandwidth, disk/network/interrupt activity) next to a running workload.

This PR **folds all of TCMI's hardware coverage into the existing Metrics
Manager service**, so there is now **one collector instead of two**. Metrics
Manager already ran Telegraf plus a small FastAPI relay in a single container and
exposed everything in Prometheus format on port `:9273`. This work adds the
hardware metrics TCMI collected — and a few TCMI never had — into that same
pipeline.

### What it actually adds

* **New telemetry** that Metrics Manager could not show before:
  * CPU **package** power and, crucially, **platform (psys) power** — the total
    whole-board power number (CPU + iGPU + NPU + memory).
  * **DRAM bandwidth** (read / write / total GB/s).
  * **Per-device interrupt (IRQ) rates**, disk utilization, and per-NIC network
    stats.
  * Per-core frequency, per-core temperature, C-state residency, and (opt-in)
    turbostat IPC/SMI diagnostics — a new **R (Real-Time Determinism)** row.
  * NPU `power_state` and GPU throttle/frequency signals.
* **A design principle:** prefer **native Telegraf input plugins** for anything a
  plugin can cover; write a small custom Python `execd` reader **only** for the
  handful of metrics no plugin can reach (psys power, DRAM bandwidth via `perf`,
  GPU xe throttle state).
* **On/off switches:** each collector is gated by an `ENABLE_*` environment
  variable, so one image serves different hardware profiles (AMR, industrial arm,
  headless server) with **no rebuild**.
* A reference **Prometheus scrape job** snippet (`dashboards/prometheus-scrape-job.yml`) to help wire existing Prometheus deployments.

### The design in one diagram

```
Kernel / hardware sources                 metrics-manager container
  /sys RAPL (incl. psys)  ─┐
  IMC free-running PMU     ─┤   ┌─ Telegraf ─────────────────────────┐
  /proc interrupts,        ─┼──▶│ native plugins  execd readers      │
  diskstats, net           ─┤   │ (powerstat,     (rapl_reader,      │
  NPU PMT sysfs            ─┤   │  diskio, net,    dram_bw_reader,    │
  Intel GPU (qmassa/xe)    ─┤   │  interrupts,     gpu_throttle,      │
  turbostat (opt-in)       ─┘   │  temp,           npu, qmassa)       │
                                │  turbostat)                        │
              entrypoint.sh ────┼─ turns .conf files on/off          │
              (ENABLE_* env)    │  from ENABLE_* env                 │
                                └──────────┬─────────────────────────┘
                                           │ prometheus_client :9273
                                           ▼
                             Prometheus (scrape :9273) ──▶ Grafana
                                                          (tcmi-mm-unified-v1)
```

---

## 2. Prerequisites

### Hardware

| Requirement | Why | If missing |
|---|---|---|
| Intel platform (Core / Core Ultra; validated on **Panther Lake Client, PTL**) | RAPL, IMC counters, NPU/GPU sysfs are Intel-specific | non-Intel metrics simply show "no data" |
| Intel iGPU (xe driver) | GPU frequency / throttle + qmassa engine util | GPU panels idle |
| Intel NPU | NPU power / freq / temp / utilization / power_state | NPU panels idle |
| NVMe / SATA disk, physical NIC | disk I/O, network I/O, IRQ metrics | those panels idle |

None of the above is strictly *required* — you get whatever your box can supply.
CPU/RAM/temperature metrics work almost everywhere.

### Software / OS

| Requirement | Notes |
|---|---|
| **Linux** | RAPL, IMC PMU, `/proc/interrupts`, sysfs are Linux-only |
| Recent kernel | validated on **6.17.0-35** (PTL) and **7.0.0-28-generic**; needs `intel_rapl_common`, `msr`, `cpufreq`, `intel-uncore-frequency` modules |
| `perf_event_paranoid` ≤ 0 | needed for DRAM bandwidth via `perf` (PTL ships `-1`; no change needed there). Check: `cat /proc/sys/kernel/perf_event_paranoid` |
| IMC free-running PMU exposed | check: `ls /sys/bus/event_source/devices/uncore_imc_*` |
| **Docker** + **Docker Compose v2** | primary deployment path |
| Prometheus + Grafana | to scrape and visualize; not needed just to collect |
| kernel-matched **turbostat** | only if you enable the R-dimension diagnostics; `apt install linux-tools-$(uname -r)` |

### Dependencies baked into the image (you don't install these)

* **Telegraf built from source (1.38.4)** — every native input plugin is compiled
  in (`intel_powerstat`, `diskio`, `net`, `ethtool`, `interrupts`, `temp`,
  `turbostat`). Turning one on is pure config.
* **`linux-perf`** — installed only when the image is built with `INSTALL_PERF=true` (default: `false`). Required only for DRAM-bandwidth collection (`ENABLE_DRAM_BW=auto`). Set `--build-arg INSTALL_PERF=true` when building if you need DRAM bandwidth.
* `dmidecode`, `pciutils`, `supervisor`, the FastAPI app, and the `execd` reader
  scripts.

### Permissions / runtime

The container must run **`--privileged`** (compose default `PRIVILEGED=true`) with:

* `-v /sys:/sys:ro` — RAPL, IMC PMU, xe/NPU sysfs, thermal zones
* `--pid host` (compose `pid: host`) — so `/proc` reflects the host
* `/dev/dri` mapped — GPU access

RAPL `energy_uj` is root-readable only; privileged mode covers that. As a
non-root/unprivileged user the psys reader finds nothing readable and idles.

### Files this feature introduces (for reference)

```
telegraf.d/
├── 10-power.conf        intel_powerstat  → CPU/DRAM RAPL power, per-core freq/temp, C-states
├── 20-dram-bw.conf      execd dram_bw_reader.py (perf on IMC free-running counters)
├── 30-disk.conf         diskio           → util%, read/write MB/s
├── 40-net.conf          net + ethtool    → throughput, per-NIC stats
├── 50-interrupts.conf   interrupts       → per-device IRQ rates
├── 60-turbostat.conf    turbostat        → IPC/SMI/per-core (opt-in, ENABLE_TURBOSTAT=false)
├── 90-tcmi-execd.conf   execd rapl_reader.py (psys / platform RAPL power)
└── 91-gpu-throttle.conf execd gpu_throttle_reader.py (xe GPU freq + throttle reasons)

scripts/
├── rapl_reader.py           psys / platform power
├── dram_bw_reader.py        DRAM bandwidth via perf
├── gpu_throttle_reader.py   xe GPU freq + throttle reasons
└── npu_reader.py            (extended) adds npu power_state

dashboards/
└── prometheus-scrape-job.yml   scrape block for prometheus.yml
```

### Environment variables (collector toggles)

Accepted "on" values are case-insensitive: `true` / `1` / `yes` / `on` / `auto`.

| Env var | Default | Effect |
|---|---|---|
| `ENABLE_RAPL_POWER` | **`false`** | load `10-power.conf` (CPU/DRAM power, per-core freq/temp, C-states). Requires `--privileged`; adds per-core series. |
| `ENABLE_DRAM_BW` | `auto` | `auto` = load the perf reader and self-probe; `off` = disable; `pcm` = reserved for PCM fallback. Requires image built with `INSTALL_PERF=true`. |
| `ENABLE_DISK_IO` | `true` | load `30-disk.conf` (cheap, universally useful) |
| `ENABLE_NET_IO` | `true` | load `40-net.conf` (cheap, universally useful) |
| `ENABLE_INTERRUPTS` | **`false`** | load `50-interrupts.conf`. Emits one series per device IRQ — significant cardinality increase on many hosts. |
| `ENABLE_PSYS_POWER` | **`false`** | load `90-tcmi-execd.conf` (psys / platform RAPL power execd reader). Requires `--privileged`. |
| `ENABLE_GPU_THROTTLE` | **`false`** | load `91-gpu-throttle.conf` (xe GPU frequency + throttle-reason execd reader). Idles silently on non-Intel-GPU hosts. |
| `ENABLE_TURBOSTAT` | `false` | load `60-turbostat.conf` (IPC/SMI/per-core diagnostics, opt-in). Requires kernel-matched turbostat binary. |
| `TURBOSTAT_INTERVAL` | `5` | turbostat sampling cadence in seconds |
| `TURBOSTAT_BIN` | *(auto)* | host path to the kernel-matched turbostat binary (bind-mounted in). **`make up` resolves this dynamically** from the running kernel — you normally don't set it. See §5. |
| `METRICS_MANAGER_HOSTNAME` | kernel hostname | stable `host=` tag stamped on every metric |

> **⚠️ Restart required:** toggling any `ENABLE_*` variable takes effect **only after a container restart** (`docker compose up -d`). There is no hot-reload.

---

## 3. Setup and Installation (from a clean environment)

### Step 0 — Clone the Repo

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/microservices/metrics-manager
```

### Step 1 — Create a `.env`

```bash
cp .env.example .env
# edit .env only if you need to change a default (see §5)
```

> **Note:** Docker Compose automatically reads `.env` at startup and substitutes
> those values into `compose.yaml` (e.g. `${ENABLE_DRAM_BW:-auto}`). Every
> variable still has a working default baked into `compose.yaml`, so this step is
> not strictly required — but starting from a copy of the template gives you a
> documented place to change collector toggles, the host tag, ports, or proxy
> settings.

### Step 2 — Build the image

The build compiles Telegraf from source, so the first build takes a while.

```bash
make build          # → metrics-manager:2026.1.0  (reads VERSION)
# or, directly:
docker compose build metrics-manager

# To enable DRAM bandwidth collection, install linux-perf into the image:
docker compose build --build-arg INSTALL_PERF=true metrics-manager
```

### Step 3 — Start the stack

```bash
make up             # docker compose up -d metrics-manager
# or:
docker compose up -d
```

That's the whole install. The container runs privileged, mounts `/sys` read-only,
uses the host PID namespace, and `entrypoint.sh` enables/disables each collector
based on the `ENABLE_*` variables before starting supervisord (which starts
Telegraf, then the FastAPI app).

### Prometheus + Grafana

Only needed to visualize. See §4 Step 5 and §5.

---

## 4. Usage Guide

### Step 1 — Confirm the collectors were gated at startup

```bash
make logs        # or: docker compose logs -f metrics-manager
```

**Expected** (default settings — DISK/NET enabled, rest off unless you opt in):

```
[INFO] Configuring hardware-telemetry collectors:
[INFO]   10-power: disabled
[INFO]   20-dram-bw: ENABLED
[INFO]   30-disk: ENABLED
[INFO]   40-net: ENABLED
[INFO]   50-interrupts: disabled
[INFO]   90-tcmi-execd: disabled
[INFO]   91-gpu-throttle: disabled
[INFO]   60-turbostat: disabled
[INFO] Initialization complete
```

Enable hardware-specific collectors by setting the relevant `ENABLE_*` variables to `true` in `.env` and running `docker compose up -d`.

### Step 2 — Health check the API

```bash
curl http://localhost:9090/health
```

**Expected:** a JSON body with `"status": "ok"` (or similar) and a version field.

### Step 3 — Confirm Telegraf is exposing metrics at all

```bash
curl -s http://localhost:9273/metrics | head
```

**Expected:** Prometheus-format lines (baseline `cpu_*`, `mem_*`, `temp_*`).

### Step 4 — Confirm the NEW TCMI metrics are flowing

Pick the ones your hardware supports:

```bash
# Platform (psys) + package power  — from rapl_reader.py
curl -s http://localhost:9273/metrics | grep '^rapl_power'

# CPU / DRAM package power, per-core freq/temp, C-states — intel_powerstat
curl -s http://localhost:9273/metrics | grep '^powerstat_'

# DRAM bandwidth (read/write/total GB/s) — dram_bw_reader.py
curl -s http://localhost:9273/metrics | grep '^dram_bw'

# Disk / network / interrupts
curl -s http://localhost:9273/metrics | grep -E '^diskio_|^net_|^interrupts_'

# CPU package temperature (coretemp_package_id_* sensors only)
curl -s http://localhost:9273/metrics | grep '^temp_temp'

# NPU (with the new power_state field) — NPU hosts only
curl -s http://localhost:9273/metrics | grep '^npu_'

# GPU xe throttle/freq — Intel-GPU hosts only
curl -s http://localhost:9273/metrics | grep '^gpu_throttle'
```

**Expected (example, from a live box at idle).** Note the Prometheus output
suffixes the field name onto the measurement (`rapl_power` → `rapl_power_power_w`)
and renders tags as labels:

```
rapl_power_power_w{domain="psys",host="..."} 8.095
rapl_power_power_w{domain="package-0",host="..."} 1.529
npu_power_state{host="..."} 3
dram_bw_read_gbps{host="..."} 0.4
interrupts_total{irq="120",...} ...        # numbered device IRQs only
```

### Step 5 — wire up Prometheus + Grafana (optional visualization)

> **Note:** Metrics Manager only *exposes* metrics on `:9273`. You need your own
> Prometheus and Grafana to scrape and visualize them. This section covers three
> paths — pick whichever fits your setup.

#### Option A — Quick-start: spin up Prometheus + Grafana with Docker Compose

The fastest way if you have no existing stack. Create a minimal
`prometheus.yml` and a `docker-compose.viz.yaml` alongside your Metrics Manager
checkout, then start both together.

**Step 5a-1 — Create `prometheus.yml`**

```yaml
# prometheus.yml  (place next to your metrics-manager directory)
global:
  scrape_interval: 5s

scrape_configs:
  - job_name: metrics-manager
    static_configs:
      - targets:
          # Use the MM container name when both stacks share a Docker network,
          # or host.docker.internal if Prometheus runs on a separate network.
          - metrics-manager:9273
```

**Step 5a-2 — Create `docker-compose.viz.yaml`**

```yaml
# docker-compose.viz.yaml
# Pinned image versions — update deliberately, not on every pull.
services:
  prometheus:
    image: prom/prometheus:v3.4.1
    container_name: prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports:
      - "9091:9090"   # host:9091 → avoid clash with MM API on :9090
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --web.enable-lifecycle       # enables POST /-/reload
    networks:
      - metric-network               # same network as metrics-manager
    restart: unless-stopped

  grafana:
    image: grafana/grafana:12.1.0
    container_name: grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=changeme   # change before exposing externally
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
    networks:
      - metric-network
    restart: unless-stopped

volumes:
  grafana-data:

networks:
  metric-network:
    external: true    # reuse the network created by metrics-manager's compose.yaml
    name: metrics-manager_metric-network
```

**Step 5a-3 — Start the visualization stack**

```bash
# Metrics Manager must already be running (make up) before this step.
docker compose -f docker-compose.viz.yaml up -d

# Verify both containers are up:
docker compose -f docker-compose.viz.yaml ps

# Verify Prometheus is scraping MM (look for metrics-manager job = UP):
open http://localhost:9091/targets
```

**Step 5a-4 — Log in to Grafana**

Open `http://localhost:3000` — default login `admin / changeme` (or whatever you
set in `GF_SECURITY_ADMIN_PASSWORD`). Grafana prompts a password change on first
login.

**Step 5a-5 — Add Prometheus as a data source**

1. **Home → Connections → Data sources → Add new data source → Prometheus**
2. URL: `http://prometheus:9090` (container-to-container on the same network)
3. **Save & test** → expect "Successfully queried the Prometheus API."

**Step 5a-6 — Create a dashboard**

Use **Explore** or create a new dashboard with panels. Example PromQL queries for
the TCMI metrics (§4 Step 4):

```promql
# Platform (psys) power — needs ENABLE_PSYS_POWER=true
rapl_power_power_w{domain="psys"}

# CPU package power — needs ENABLE_RAPL_POWER=true
powerstat_package_current_power_consumption_watts

# DRAM bandwidth (read / write GB/s) — needs ENABLE_DRAM_BW=auto + INSTALL_PERF=true
dram_bw_read_gbps
dram_bw_write_gbps

# Disk I/O utilization %
rate(diskio_io_time[1m]) / 10

# Network throughput (bytes/s)
rate(net_bytes_recv[1m])
rate(net_bytes_sent[1m])

# IRQ rates — needs ENABLE_INTERRUPTS=true
rate(interrupts_total[1m])

# GPU frequency and throttle state — needs ENABLE_GPU_THROTTLE=true
gpu_throttle_act_freq_mhz
gpu_throttle_throttled

# CPU package temperature
temp_temp{sensor=~"coretemp_package_id_.*"}

# CPU usage
100 - cpu_usage_idle

# Memory used %
100 - mem_available_percent

# NPU power state (0=off, 1=on, 3=busy) — NPU hosts only
npu_power_state

# Turbostat IPC / SMI — needs ENABLE_TURBOSTAT=true
turbostat_ipc{core!="-"}
turbostat_smi{core="-"}    # system-wide SMI count
```

**Stop the visualization stack:**

```bash
docker compose -f docker-compose.viz.yaml down
# To also remove grafana-data volume:
docker compose -f docker-compose.viz.yaml down -v
```

---

#### Option B — Add MM to an existing Prometheus

Copy the scrape block from `dashboards/prometheus-scrape-job.yml` into your
`prometheus.yml` under `scrape_configs:`, then reload:

```bash
# Hot-reload (needs --web.enable-lifecycle on Prometheus):
curl -s -X POST http://<prometheus-host>:9090/-/reload

# Or restart:
docker restart <prometheus-container>
```

Then add Grafana panels using the PromQL queries listed in Option A Step 5a-6.

---

#### Option C — Kubernetes / Helm (Prometheus Operator)

The Helm chart ships a `ServiceMonitor` resource. Enable it in `values.yaml`:

```yaml
serviceMonitor:
  enabled: true
  interval: 5s
  namespace: monitoring    # namespace where Prometheus Operator runs
```

This auto-registers the MM Telegraf endpoint (`:9273`) as a scrape target.
No manual `prometheus.yml` edit is needed.

---

**Expected:** once scraping is active, the `metrics-manager` target shows **UP**
on Prometheus `/targets`, and panels resolve within one `scrape_interval`.

### Step 6 — (Optional) run the test suite

```bash
make test        # builds the test image and runs pytest inside it
```

---

## 5. Configuration

### Where configuration lives

1. **`.env`** (copied from `.env.example`) — read by `docker compose`. Set `ENABLE_*` toggles, ports, hostname tag, etc. here.
2. **`compose.yaml`** — passes the `ENABLE_*` variables into the container and defines the privileged runtime, `/sys` mount, `pid: host`, and the turbostat bind-mount.
3. **`telegraf.d/*.conf`** — the per-collector Telegraf drop-ins. Toggle with env vars; don't edit these directly.
4. **`Makefile`** — `make up`/`make build` resolve the kernel-matched `TURBOSTAT_BIN` dynamically and export it into the compose environment, so you never pin a kernel version in `.env`.

### The collector toggles

All optional (defaults work out of the box). Uncomment in `.env` to change:

```bash
# .env  (copy from .env.example, uncomment what you need)
#
# Always-on (cheap, universally useful):
ENABLE_DISK_IO=true
ENABLE_NET_IO=true

# Off by default — enable for Intel hardware telemetry:
# ENABLE_RAPL_POWER=true       # CPU/DRAM power, per-core freq/temp, C-states
# ENABLE_DRAM_BW=auto          # auto | off  (requires INSTALL_PERF=true at build time)
# ENABLE_INTERRUPTS=true       # per-device IRQ rates (high cardinality — see note below)
# ENABLE_PSYS_POWER=true       # platform (psys) RAPL power execd reader
# ENABLE_GPU_THROTTLE=true     # Intel xe GPU frequency + throttle reasons
# ENABLE_TURBOSTAT=false       # R-dimension: IPC/SMI/per-core diagnostics (opt-in)
# TURBOSTAT_INTERVAL=5
```

> **Note on `ENABLE_INTERRUPTS`:** emits one Prometheus series per device IRQ
> (e.g. 45 on a PTL box). Enable deliberately — the cardinality increase is real
> for every existing Prometheus deployment.

After changing any toggle: **`docker compose up -d`** (recreates the container; no hot-reload).

### Enabling the opt-in turbostat (R-dimension) diagnostics

**Where do I enable it?** In your **`.env`** file — the same place as every other
`ENABLE_*` toggle (§"The collector toggles" above). It ships `false`; set it to
`true`. There is nothing to uncomment in `compose.yaml` — compose already forwards
`ENABLE_TURBOSTAT` / `TURBOSTAT_INTERVAL` / `TURBOSTAT_BIN` from `.env`.

turbostat is **kernel-coupled**, so the image ships **no** turbostat binary. The
host's kernel-matched binary is bind-mounted into the container via
`TURBOSTAT_BIN`. **Never hardcode this path in `.env`** — it encodes the kernel
version (`/usr/lib/linux-tools/<uname -r>/turbostat`), so a literal value breaks
the next time you upgrade the kernel. (`.env` is read *literally* by Docker
Compose — it can't expand `$(uname -r)` — which is exactly why the path can't
live there.)

**If you use `make up` (recommended), there is nothing to set.** The Makefile
resolves the kernel-matched binary dynamically and passes it in. Just enable the
toggle:

```bash
# 1. Install turbostat for the running kernel (if not already present)
sudo apt install linux-tools-$(uname -r)

# 2. Enable the toggle in .env
echo "ENABLE_TURBOSTAT=true" >> .env

# 3. Recreate so the new bind-mount + toggle take effect
make up
```

The Makefile resolves the path with the **correct precedence — kernel-matched
first, then `$PATH`**:

```make
TURBOSTAT_BIN ?= $(shell [ -x /usr/lib/linux-tools/$(uname -r)/turbostat ] \
                  && echo /usr/lib/linux-tools/$(uname -r)/turbostat \
                  || command -v turbostat)
```

> **Why that ordering matters.** A bare `command -v turbostat` often resolves to
> the distro's *generic* `/usr/bin/turbostat`, which **refuses to run against a
> mismatched kernel** (exits with `turbostat not found for kernel …`) — so the R
> panels stay empty even though a binary "exists". Checking the kernel-matched
> `/usr/lib/linux-tools/$(uname -r)/turbostat` **first** avoids that trap.

**If you run `docker compose up` directly** (not via `make`), Compose won't run
the Makefile, so export the variable yourself first — using the same precedence:

```bash
export TURBOSTAT_BIN=$( [ -x /usr/lib/linux-tools/$(uname -r)/turbostat ] \
  && echo /usr/lib/linux-tools/$(uname -r)/turbostat || command -v turbostat )
docker compose up -d
```

If the binary and kernel don't match, turbostat refuses to read the MSRs and the
R panels stay empty (no crash — just no data).

### Runtime knobs worth knowing

| Variable | Default | Purpose |
|---|---|---|
| `METRICS_MANAGER_HOSTNAME` | kernel hostname | stable `host=` tag so Grafana `$host` stays constant across restarts |
| `HOST_METRICS_PORT` | `9090` | host port for the API + SSE |
| `HOST_TELEGRAF_PORT` | `9273` | host port for the Prometheus endpoint |
| `PRIVILEGED` | `true` | set `false` only if you want CPU/RAM/temp and nothing hardware-privileged |
| `DRAM_BW_INTERVAL` | `1` | perf sampling window (seconds) for DRAM bandwidth |

### Prometheus scrape job

A reference scrape-job snippet lives at `dashboards/prometheus-scrape-job.yml`.
Copy the `scrape_configs` block into your `prometheus.yml` and reload Prometheus.

---

## 6. Validation

### A. Startup gating log (fastest check)

`docker compose logs metrics-manager | grep "ENABLED\|disabled"` — you should see
each collector's decision. This proves the env → entrypoint wiring works even
before any metric flows.

### B. The metric actually appears

The definitive test: `curl -s localhost:9273/metrics | grep <metric>`. Sample
new-metric names and what a healthy PTL box shows:

| Check | Command grep | Healthy example |
|---|---|---|
| psys power present | `rapl_power` with `domain=psys` | `power_w≈5.9` at idle |
| CPU package power | `powerstat_package_current_power_consumption_watts` | non-zero |
| DRAM bandwidth | `dram_bw` | `read_gbps≈0.4, write_gbps≈0.06` at idle |
| Device IRQs only | `interrupts_total` | numbered IRQs present, no `LOC/NMI/IPI` symbols |
| CPU package temp | `temp_temp` | `coretemp_package_id_*` sensors |

### C. The reader processes are running

```bash
docker exec metrics-manager ps -ef | grep -E 'rapl_reader|dram_bw_reader|gpu_throttle_reader|npu_reader'
```

### D. Reader trace logs (why something is idle)

Each execd reader writes a trace log inside the container:

```bash
docker exec metrics-manager sh -c 'tail -n 20 /app/rapl_reader_trace.log'
docker exec metrics-manager sh -c 'tail -n 20 /app/dram_bw_reader_trace.log'
docker exec metrics-manager sh -c 'tail -n 20 /app/gpu_throttle_reader_trace.log'
```

A line like `entering idle mode: perf could not count IMC free-running events`
tells you exactly why a metric is missing — this is the intended, non-fatal
behaviour, not an error.

### E. End-to-end via Grafana

The `metrics-manager` Prometheus target is green on `/targets`, and every panel in
the T/C/M/I rows resolves. On PTL this was verified live: psys ~6.5 W, DRAM
bandwidth, 45 device IRQs, per-core C0 residency, with `$host = ptl-system`.

### F. Wiring regression tests

```bash
make test
```

`tests/test_telegraf_integration.py` asserts the drop-ins ship, the readers exist
and honor the hostname/idle contract, the entrypoint gates every toggle, and
`--config-directory` is wired.

---

## 7. Example Workflow (end to end)

A complete run on a fresh Intel box (PTL-class), collection only, then Grafana.

```bash
# --- 1. Get the code -------------------------------------------------------
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
cd edge-ai-libraries/microservices/metrics-manager

# --- 2. (optional) sanity-check the host can feed the new metrics ----------
cat /proc/sys/kernel/perf_event_paranoid          # want <= 0
ls /sys/bus/event_source/devices/uncore_imc_*      # IMC PMU present?
ls /sys/class/powercap/intel-rapl:*                # RAPL zones (incl. :1 = psys)?

# --- 3. Configure (optional — defaults are fine) ---------------------------
cp .env.example .env
# leave the ENABLE_* defaults; optionally set a stable host tag:
#   METRICS_MANAGER_HOSTNAME=ptl-system

# --- 4. Build & start ------------------------------------------------------
make build
make up

# --- 5. Watch the gating log ----------------------------------------------
docker compose logs metrics-manager | grep -E "ENABLED|disabled"
#   10-power: disabled  20-dram-bw: ENABLED  30-disk: ENABLED  40-net: ENABLED
#   50-interrupts: disabled  90-tcmi-execd: disabled  91-gpu-throttle: disabled
#   60-turbostat: disabled  (enable collectors in .env, then: docker compose up -d)

# --- 6. Verify the service and the new metrics -----------------------------
curl http://localhost:9090/health
curl -s http://localhost:9273/metrics | grep '^rapl_power'    # psys ≈ 5.9 W idle
curl -s http://localhost:9273/metrics | grep '^dram_bw'       # read/write GB/s
curl -s http://localhost:9273/metrics | grep '^powerstat_'
curl -s http://localhost:9273/metrics | grep -E '^diskio_|^net_|^interrupts_'

# --- 7. If something reads "no data", find out why -------------------------
docker exec metrics-manager sh -c 'tail /app/rapl_reader_trace.log'
docker exec metrics-manager sh -c 'tail /app/dram_bw_reader_trace.log'

# --- 8. visualize — add the scrape job to your own Prometheus/Grafana -----
# Copy dashboards/prometheus-scrape-job.yml into your prometheus.yml, then:
curl -s -X POST http://<prometheus>:9090/-/reload
# Create panels in Grafana using the PromQL queries listed in §4 Step 5d.

# --- 9. enable the R-dimension microscope -----------------------
sudo apt install linux-tools-$(uname -r)
echo "ENABLE_TURBOSTAT=true" >> .env    # do NOT set TURBOSTAT_BIN here — see §5
make up                                 # resolves the kernel-matched turbostat binary for you
curl -s http://localhost:9273/metrics | grep -E 'turbostat_(ipc|smi)'

# --- 10. (optional) run the wiring tests -----------------------------------
make test
```

At the end you have a single privileged container collecting the full T/C/M/I(+R)
envelope, exposed on `:9273`, optionally scraped by Prometheus and rendered in the
`tcmi-mm-unified-v1` Grafana dashboard.

---
