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
* **A generated Grafana dashboard** + a Prometheus scrape job to visualize it all.

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
* **`linux-perf`** — added to the image by this recent changes, used by the DRAM-bandwidth
  reader.
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
├── 10-power.conf              intel_powerstat  → CPU/DRAM RAPL power, per-core freq/temp, C-states
├── 20-dram-bw.conf            execd dram_bw_reader.py (perf on IMC free-running counters)
├── 20-dram-bw.conf.example    documented native intel_pmu / intel_rdt alternatives (not loaded)
├── 30-disk.conf               diskio           → util%, read/write MB/s
├── 40-net.conf                net + ethtool    → throughput, per-NIC stats
├── 50-interrupts.conf         interrupts       → per-device IRQ rates
├── 60-turbostat.conf.example  turbostat        → IPC/SMI/per-core (opt-in, ships DISABLED)
└── 90-tcmi-execd.conf         execd rapl_reader.py (psys) + gpu_throttle_reader.py

scripts/
├── rapl_reader.py             psys / platform power
├── dram_bw_reader.py          DRAM bandwidth via perf
├── gpu_throttle_reader.py     xe GPU freq + throttle reasons
└── npu_reader.py              (extended) adds npu power_state

dashboards/
├── generate_dashboard.py      generates the Grafana JSON
├── tcmi-hardware-telemetry.json   the dashboard (uid tcmi-mm-unified-v1)
└── prometheus-scrape-job.yml  scrape block for prometheus.yml
```

### Environment variables (collector toggles)

Accepted "on" values are case-insensitive: `true` / `1` / `yes` / `on` / `auto`.

| Env var | Default | Effect |
|---|---|---|
| `ENABLE_RAPL_POWER` | `true` | load `10-power.conf` (CPU/DRAM power, per-core freq/temp, C-states) |
| `ENABLE_DRAM_BW` | `auto` | `auto` = load the perf reader and self-probe; `off` = disable; `pcm` = reserved for PCM fallback |
| `ENABLE_DISK_IO` | `true` | load `30-disk.conf` |
| `ENABLE_NET_IO` | `true` | load `40-net.conf` |
| `ENABLE_INTERRUPTS` | `true` | load `50-interrupts.conf` |
| `ENABLE_PSYS_POWER` | `true` | load `90-tcmi-execd.conf` (psys power + GPU throttle execd readers) |
| `ENABLE_TURBOSTAT` | `false` | activate `60-turbostat.conf` from its `.example` (opt-in) |
| `TURBOSTAT_INTERVAL` | `5` | turbostat sampling cadence in seconds |
| `TURBOSTAT_BIN` | *(auto)* | host path to the kernel-matched turbostat binary (bind-mounted in). **`make up` resolves this dynamically** from the running kernel — you normally don't set it. See §5. |
| `METRICS_MANAGER_HOSTNAME` | kernel hostname | stable `host=` tag stamped on every metric |

---

## 3. Setup and Installation (from a clean environment)

### Step 0 — Clone the Repo

```bash
git clone https://github.com/mutra-vamsi/edge-ai-libraries.git
cd edge-ai-libraries/microservices/metrics-manager
git checkout vamsi-tcmi-hw-telemetry
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

The build compiles Telegraf from source and installs `linux-perf`, so the first
build takes a while.

```bash
make build          # → metrics-manager:2026.1.0  (reads VERSION)
# or, directly:
docker compose build metrics-manager
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

**Expected** — the entrypoint prints one line per collector:

```
[INFO] Configuring hardware-telemetry collectors:
[INFO]   10-power: ENABLED
[INFO]   20-dram-bw: ENABLED
[INFO]   30-disk: ENABLED
[INFO]   40-net: ENABLED
[INFO]   50-interrupts: ENABLED
[INFO]   90-tcmi-execd: ENABLED
[INFO]   60-turbostat: disabled
[INFO] Initialization complete
```

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

# Widened temperatures (package, per-core, nvme, board)
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

> **Important:** Metrics Manager does **not** bundle Prometheus or Grafana into
> its own service — it only *exposes* metrics on `:9273`. You need a Prometheus
> (to scrape and store) and a Grafana (to visualize):
> * **Don't have them?** Use the bundled convenience stack — **5a-i**. One command,
>   nothing to configure, then jump to "View the live dashboard."
> * **Already run your own Grafana/Prometheus?** Add the scrape job (**5a-ii**) and
>   wire the datasource + dashboard by hand (**5b–5e**).

#### 5a-i. Don't have Prometheus/Grafana? Use the bundled convenience stack

The repo ships a ready-made Prometheus + Grafana stack under
[`observability/`](../observability) that's **pre-wired** to scrape MM and load
the TCMI dashboard — datasource UID already pinned to match, so there's nothing to
configure and nothing to regenerate:

```bash
# from the metrics-manager directory, with MM already running (make up):
docker compose -f observability/compose.yaml up -d
```

That's it. It brings up:
* **Prometheus** on host port **9091**, scraping MM's `:9273`.
* **Grafana** on host port **3000**, with the Prometheus datasource and the TCMI
  dashboard auto-provisioned.

If this covers you, **skip straight to "View the live dashboard"** at the end of
this step — 5b–5e are only needed when you wire up your *own* Grafana by hand.
See [`observability/README.md`](../observability/README.md) for details and
customization (proxy, ports, password, same-network setups).

#### 5a-ii. Already have Prometheus? Just add the scrape job

Copy the block from `dashboards/prometheus-scrape-job.yml` into `scrape_configs:`
in your existing `prometheus.yml`, then reload:

```bash
curl -s -X POST http://<prometheus>:9090/-/reload    # needs --web.enable-lifecycle
# no lifecycle flag? just: docker restart <prometheus-container>
```

> **5b–5e are the manual path** — only for wiring up your **own** Grafana. If you
> used the bundled stack (5a-i), the datasource and dashboard are already
> provisioned; skip to "View the live dashboard."

#### 5b. Log in and add the Prometheus datasource in Grafana

1. Open your Grafana.
2. Log in — Grafana's default first-run credentials are **`admin` / `admin`**
   (it forces a password reset on first login). Use your own if already set up.
3. **Configuration → Data sources → Add data source → Prometheus.**
   * URL: your Prometheus address (e.g. `http://<prometheus-host>:9090`).
   * **Save & test** — you want "Data source is working."

#### 5c. Get the datasource UID (this is your `PROM_DS_UID`)

You do **not** invent this value — Grafana generates it for each datasource. Find
it one of two ways:

* **UI:** open the datasource you just added; the UID is the last path segment of
  the browser URL, e.g. `…/datasources/edit/`**`PBFA97CFB590B2093`**.
* **API:**
  ```bash
  curl -s -u admin:<your-password> http://localhost:3000/api/datasources \
    | python3 -c 'import sys,json; [print(d["name"], d["uid"]) for d in json.load(sys.stdin)]'
  ```

#### 5d. Load the dashboard

The shipped JSON is built against the reference stack's UID (`PBFA97CFB590B2093`).
If **your** UID matches, load it as-is; if not, regenerate first (see 5e):

```bash
# Option A — file provisioning (if Grafana provisions a dashboards folder)
cp dashboards/tcmi-hardware-telemetry.json /path/to/grafana/dashboards/

# Option B — import via the Grafana HTTP API
python3 - <<'PY'
import json
d = json.load(open("dashboards/tcmi-hardware-telemetry.json")); d.pop("id", None)
json.dump({"dashboard": d, "overwrite": True}, open("/tmp/imp.json", "w"))
PY
curl -s -u admin:<your-password> -X POST \
  http://localhost:3000/api/dashboards/db \
  -H 'Content-Type: application/json' --data-binary @/tmp/imp.json
```

#### 5e. If your datasource UID differs, regenerate the dashboard

```bash
python3 dashboards/generate_dashboard.py --ds-uid <PROM_DS_UID>   # from 5c
# then load the regenerated dashboards/tcmi-hardware-telemetry.json via 5d
```

#### View the live dashboard

Open Grafana → **Dashboards** → **TCMI Hardware Telemetry** (uid
`tcmi-mm-unified-v1`), or go straight to
**http://localhost:3000/d/tcmi-mm-unified-v1**. Pick your host from the `$host`
dropdown at the top.

**Expected:** the `metrics-manager` target is green on Prometheus'
`/targets` page within one scrape interval, and the dashboard's T / C / M / I rows
show live data (the R row stays empty unless turbostat is enabled — see §5).

### Step 6 — (Optional) run the test suite

```bash
make test        # builds the test image and runs pytest inside it
```

---

## 5. Configuration

### Where configuration lives

1. **`.env`** (copied from `.env.example`) — read by `docker compose`. This is
   where you set the `ENABLE_*` toggles, ports, hostname tag, etc.
2. **`compose.yaml`** — passes the `ENABLE_*` variables into the container and
   defines the privileged runtime, `/sys` mount, `pid: host`, and the turbostat
   bind-mount.
3. **`telegraf.d/*.conf`** — the per-collector Telegraf drop-ins. You normally
   don't edit these; you toggle them with env vars.
4. **`app/settings.py`** — mirrors the toggles as type-validated fields so the app
   can report the active collector set.
5. **`Makefile`** — `make up`/`make build` resolve the kernel-matched
   `TURBOSTAT_BIN` dynamically and export it into the compose environment, so you
   never pin a kernel version in `.env`.

### The collector toggles

All optional (defaults work out of the box). Uncomment in `.env` to change:

```bash
# .env
ENABLE_RAPL_POWER=true      # CPU/DRAM power, per-core freq/temp, C-states
ENABLE_DRAM_BW=auto         # auto | off | pcm
ENABLE_DISK_IO=true
ENABLE_NET_IO=true
ENABLE_INTERRUPTS=true
ENABLE_PSYS_POWER=true      # platform (psys) power + GPU throttle readers
ENABLE_TURBOSTAT=false      # opt-in R-dimension diagnostics
TURBOSTAT_INTERVAL=5
```

After changing any toggle: `docker compose up -d` (recreates the container; the
entrypoint re-gates the `.conf` files — the operation is idempotent).

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

### Command-line options for the dashboard generator

```bash
python3 dashboards/generate_dashboard.py --ds-uid <PROM_DS_UID> [--out PATH]
```

* `--ds-uid` — the **Grafana Prometheus datasource UID** the dashboard's panels
  query. This is **not a value you make up** — Grafana assigns it when you add the
  datasource. Get it from §4 Step 5c (Grafana UI URL, or the
  `/api/datasources` endpoint). Defaults to the reference stack's UID
  `PBFA97CFB590B2093`; you only need `--ds-uid` when yours differs.
* `--out` — where to write the JSON (defaults to
  `dashboards/tcmi-hardware-telemetry.json`).

Regenerate rather than hand-editing the JSON — the generator is the source of
truth. After regenerating, load the new JSON into Grafana (§4 Step 5d).

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
| Widened temps | `temp_temp` | `coretemp_core_*`, `nvme_composite`, `acpitz` |

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
git clone <your-fork-url> edge-ai-libraries
cd edge-ai-libraries/microservices/metrics-manager
git checkout vamsi-tcmi-hw-telemetry

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
#   10-power: ENABLED ... 90-tcmi-execd: ENABLED ... 60-turbostat: disabled

# --- 6. Verify the service and the new metrics -----------------------------
curl http://localhost:9090/health
curl -s http://localhost:9273/metrics | grep '^rapl_power'    # psys ≈ 5.9 W idle
curl -s http://localhost:9273/metrics | grep '^dram_bw'       # read/write GB/s
curl -s http://localhost:9273/metrics | grep '^powerstat_'
curl -s http://localhost:9273/metrics | grep -E '^diskio_|^net_|^interrupts_'

# --- 7. If something reads "no data", find out why -------------------------
docker exec metrics-manager sh -c 'tail /app/rapl_reader_trace.log'
docker exec metrics-manager sh -c 'tail /app/dram_bw_reader_trace.log'

# --- 8. visualize (bundled Prometheus + Grafana, pre-wired) ----------------
docker compose -f observability/compose.yaml up -d
# then open http://localhost:3000/d/tcmi-mm-unified-v1  (login admin / admin)
# already run your own Prometheus/Grafana? see §4 Step 5a-ii / 5b-5e instead.

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
