# Unifying TCMI Hardware Telemetry into the Metrics Manager

## 1. Objective

Develop a **single, upstreamable, open-source hardware-telemetry tool** for robotics, Edge AI, and
physical-AI workloads on Intel platforms — by folding the TCMI framework's unique hardware coverage
into the existing **Metrics Manager** (`intel/metrics-manager`, OEP `edge-ai-libraries`) rather than
maintaining two parallel frameworks.

**Strategy decision (this proposal):** prefer **native Telegraf input plugins** for every metric a
plugin can cleanly cover. Port a TCMI Python reader as a Telegraf `execd` plugin **only** where no
native plugin exists, the metric is PTL/Xe/NPU-specific, or a native plugin would lose fidelity.
This keeps the result maximally upstream-friendly and low-maintenance.

**See also:** [architecture & data flow](architecture-tcmi-integration.md) · [ADR 0001 — why we collect things the way we do](adr/0001-tcmi-telemetry-collection.md) · [dashboards/](../dashboards)

---

## 1a. Where things stand

The native plugins, DRAM bandwidth , the extra execd readers , and the Grafana dashboard are all in the repo and have been tested end-to-end on the PTL box. Here's what landed:

| Change | File | Validated on PTL |
|--------|------|:-----------:|
| **Loader fix** — `telegraf.d/` drop-ins were never loaded (telegraf ran with `--config` only). Added `--config-directory /etc/telegraf/telegraf.d`. | [`supervisord.conf`](../supervisord.conf) | ✅ |
| CPU/DRAM RAPL power, per-core freq, C-states | [`telegraf.d/10-power.conf`](../telegraf.d/10-power.conf) (`intel_powerstat`) | ✅ `powerstat_package_*`, `powerstat_core_*` |
| Per-core / NVMe / board temperature | [`telegraf.conf`](../telegraf.conf) widened starlark filter (`inputs.temp`) | ✅ `temp_temp{sensor=coretemp_core_*/nvme_composite/acpitz}` |
| Disk I/O (util%, r/w MB/s) | [`telegraf.d/30-disk.conf`](../telegraf.d/30-disk.conf) (`diskio`) | ✅ `diskio_*` |
| Network I/O + per-NIC ethtool stats | [`telegraf.d/40-net.conf`](../telegraf.d/40-net.conf) (`net`, `ethtool`) | ✅ `net_*`, `ethtool_*` |
| IO interrupt rates (numeric device IRQs only) | [`telegraf.d/50-interrupts.conf`](../telegraf.d/50-interrupts.conf) (`interrupts`) | ✅ `interrupts_total` (45 device IRQs, 0 housekeeping) |
| **DRAM bandwidth (read/write/total GB/s)** — active | [`telegraf.d/20-dram-bw.conf`](../telegraf.d/20-dram-bw.conf) + [`scripts/dram_bw_reader.py`](../scripts/dram_bw_reader.py) (`perf` on IMC free-running counters) | ✅ `dram_bw_read_gbps`/`write_gbps`/`total_gbps` |
| **Platform (psys) + package RAPL power** — active | [`telegraf.d/90-tcmi-execd.conf`](../telegraf.d/90-tcmi-execd.conf) + [`scripts/rapl_reader.py`](../scripts/rapl_reader.py) | ✅ `rapl_power_power_w{domain=psys}` = 5.9 W idle |
| Turbostat R-dimension diagnostics — **opt-in, ships disabled** | [`telegraf.d/60-turbostat.conf.example`](../telegraf.d/60-turbostat.conf.example) + [`scripts/turbostat_reader.py`](../scripts/turbostat_reader.py) | idles (kernel-coupled binary; opt-in) |
| Collector toggles + startup gating | [`.env.example`](../.env.example), [`app/settings.py`](../app/settings.py), [`entrypoint.sh`](../entrypoint.sh), [`compose.yaml`](../compose.yaml) | ✅ gating log confirms |
| Drop-ins + `perf` baked into the image | [`Dockerfile`](../Dockerfile) (`COPY telegraf.d/`, `linux-perf`) | ✅ |
| Wiring regression tests | [`tests/test_telegraf_integration.py`](../tests/test_telegraf_integration.py) | — |

If the hardware or kernel can't supply a metric, the active `.conf` files just show "no data" instead
of erroring — same as the NPU/GPU readers already do. We saw this work on PTL: the DRAM-BW reader sat
idle while `perf` was missing, then started producing numbers once we installed it. The
`.conf.example` files aren't loaded by `--config-directory` at all, so shipping to a box without
turbostat won't break anything — you turn those on yourself (see §8-P2).

**PTL validation — DONE** (target Panther-Lake-Client, kernel 6.17.0-35):

| Probe | Result | Consequence |
|-------|--------|-------------|
| RAPL domains | `package-0`, `core`, `uncore`, `dram`, **`psys`** all present | `intel_powerstat` fully supported; **psys exists** → psys execd reader (P2) is viable |
| RAPL `energy_uj` | root-only (`-r--------`), increments under sudo | works in the `--privileged` container; not readable as the app user |
| `perf_event_paranoid` | `-1` | PMU access already open — no sysctl change needed |
| IMC PMU | `uncore_imc_0/1` + `uncore_imc_free_running_0/1`; `perf stat` counted 116.6/7.4 MiB in 1s | **DRAM BW via `intel_pmu` free-running counters** (type 27, `data_read` umask 0x20 / `data_write` 0x30, 64 B/count) |
| RDT / resctrl / pqos | **absent** | `intel_rdt` **ruled out** on PTL |
| Intel PCM | `/usr/bin/pcm` present | proven fallback available |
| turbostat | `2025.09.09` present | R-dimension diagnostics viable |
| CPU model | reports `Genuine Intel(R) 0000` (masked ES/QS) | ⚠️ `intel_pmu` **named** event lookup (perfmon JSON) may fail → use **raw** event codes or a `perf stat` execd wrapper |

So for PTL the DRAM-bandwidth question is settled: read the free-running IMC counters with perf (see
[`20-dram-bw.conf.example`](../telegraf.d/20-dram-bw.conf.example), Option A1), with PCM as a fallback
if we ever need it. The last runtime check was a full container smoke test on the box
(`curl -s localhost:9273/metrics | grep -E 'powerstat_|diskio_|interrupts_'`) once the image was built
there — which is done.

---

## 2. What the Metrics Manager already had

Here's what Telegraf was collecting before we started ([`telegraf.conf`](../telegraf.conf)):

| Dimension | Metric | Mechanism |
|-----------|--------|-----------|
| CPU | `cpu.usage_user/system/idle` | `inputs.cpu` |
| CPU | `cpu_frequency_avg.frequency` | `inputs.exec` → [`read_cpu_freq.sh`](../scripts/read_cpu_freq.sh) |
| Memory | `mem.used_percent/available_percent/total/used` | `inputs.mem` |
| Thermal | `temp` (**CPU package only**) | `inputs.temp` + starlark filter |
| GPU | `gpu_engine_usage.usage` (per engine rcs/ccs/vcs/bcs/vecs) | `execd` → [`qmassa_reader.py`](../scripts/qmassa_reader.py) |
| NPU | `npu.power/frequency/temperature/bandwidth/utilization/memory_mb/tile_config` | `execd` → [`npu_reader.py`](../scripts/npu_reader.py) |

The gap that stood out: **no CPU package power and no platform (psys) power at all.**

The good news is the image already had everything we needed to add the rest:
- **Telegraf is built from source** ([Dockerfile:75-130](../Dockerfile#L75-L130)), so every native
  input plugin is compiled in — turning one on is just config.
- **`execd`** readers (the same pattern `npu_reader.py` and `qmassa_reader.py` use): a long-running
  process that prints InfluxDB line protocol to stdout once per interval.
- **`/app/custom-metrics/*.{sh,py}`** — a drop-in folder that gets run every 10s.
- The container runs `--privileged` with `-v /sys` and `--pid host`, so we can get at RAPL, PMT, MSR,
  and perf.

---

## 3. Every TCMI metric, and how we get it into MM

We went through TCMI metric by metric and picked a path for each. Legend:
**✅ Already in MM** · **🟢 Native plugin (config only)** · **🟡 Port the TCMI reader (execd)** ·
**🔵 Extend a reader MM already has**

### T — Thermal & Power

| TCMI metric | Source | MM status | Recommended path |
|-------------|--------|-----------|------------------|
| `cpu_pkg_temp_c` | coretemp hwmon | ✅ (`inputs.temp`, filtered) | keep |
| `cpu_max_core_c` | coretemp per-core | 🟢 | widen starlark filter to keep `coretemp_core_*` |
| `nvme_temp_c` | nvme hwmon Composite | 🟢 | widen `inputs.temp` filter to keep `nvme_*` |
| `acpitz_c` | acpitz hwmon | 🟢 | `inputs.temp` (acpitz is a hwmon sensor) |
| `tcpu_zone_c`, `tcpu_pci_c` | `/sys/class/thermal/thermal_zone*` type=TCPU/TCPU_PCI | 🟡 | `inputs.temp` may not enumerate these zones → small `execd` (sysfs read); ~15 lines |
| `cpu_power_w` | RAPL pkg `intel-rapl:0/energy_uj` | **missing** → 🟢 | **`inputs.intel_powerstat`** (`powerstat_package.current_power_consumption_watts`) |
| `psys_power_w` | RAPL platform `intel-rapl:1/energy_uj` | **missing** → 🟡 | `intel_powerstat` exposes package + dram domains, **not psys** on most builds → small `execd` RAPL-delta reader for the `intel-rapl:1` domain |
| `npu_temp_c` | PMT SOC_TEMPERATURES | ✅ (`npu.temperature`) | keep |
| `npu_power_w` | PMT VPU_ENERGY delta | ✅ (`npu.power`) | keep |
| `npu_ddr_bw_mbs` | PMT VPU_MEMORY_BW delta | ✅ (`npu.bandwidth`) | keep |
| `npu_power_state` | accel `power_state` D0/D3hot | 🔵 | add one field to [`npu_reader.py`](../scripts/npu_reader.py) |
| `gpu_act_freq_mhz`, `gpu_driver_freq_mhz` | xe DRM `freq0/act_freq`,`cur_freq` | 🟡 | no native plugin for xe freq → small `execd`, or 🔵 add to `qmassa_reader.py` |
| `gpu_throttled`, `gpu_throttle_thermal` | xe DRM `throttle/status`,`reason_thermal` | 🟡 | same reader as above — **no native equivalent; important for the T envelope** |

### C — Compute

| TCMI metric | Source | MM status | Recommended path |
|-------------|--------|-----------|------------------|
| `cpu_busy_pct` | `/proc/stat` | ✅ (`inputs.cpu`) | keep |
| `cpu_freq_avg_mhz` | cpufreq | ✅ (`read_cpu_freq.sh`) | keep — or fold into `intel_powerstat` (`powerstat_core.cpu_frequency_mhz`) to consolidate |
| `gpu_busy_pct` (aggregate) | xe gtidle | ✅ **better** in MM (per-engine via qmassa) | drop the aggregate; MM's per-engine breakdown supersedes it |
| `npu_busy_pct` | accel `npu_busy_time_us` | ✅ (`npu.utilization`) | keep |
| `npu_freq_mhz` | accel | ✅ (`npu.frequency`) | keep |
| `npu_mem_alloc_mb` | accel | ✅ (`npu.memory_mb`) | keep |

### M — Memory

| TCMI metric | Source | MM status | Recommended path |
|-------------|--------|-----------|------------------|
| `mem_used_gb/avail_gb/total_gb` | `/proc/meminfo` | ✅ (`inputs.mem`) | keep |
| `dram_read_gbps`, `dram_write_gbps` | Intel PCM IMC | **missing** → 🟢 / 🟡 | **primary: `inputs.intel_pmu`** (IMC uncore `UNC_M_CAS_COUNT.RD/WR`) **or `inputs.intel_rdt`** (MBM). **Both are platform-gated** (see §5). Fallback: 🟡 port [`monitor_memory.py`](../../../../dev-170-system/ros2-intel-optimizations/tcmi/monitor_memory.py) PCM path as `execd` |

### I — I/O

| TCMI metric | Source | MM status | Recommended path |
|-------------|--------|-----------|------------------|
| `disk_util_pct`, `disk_r_mbs`, `disk_w_mbs` | iostat | **missing** → 🟢 | **`inputs.diskio`** (read/write bytes → MB/s; `io_time` delta → util%). Native, no iostat blocking-1s penalty |
| `net_rx_mbs`, `net_tx_mbs` | `/proc/net/dev` | **missing** → 🟢 | **`inputs.net`** (already stubbed, commented out in `telegraf.conf`) |
| `io_irq_per_sec` (per device), `io_irq_total` | `/proc/interrupts` | **missing** → 🟢 | **`inputs.interrupts`** + tagpass/regex to classify disk/usb/network. **Key for the I envelope** |
| per-NIC ring/error stats (future) | ethtool | — | **`inputs.ethtool`** — richer than TCMI has today; recommend adding |

### The handful of things that actually need code

Everything else is just plugin config. These are the only bits with no native plugin behind them:

1. **`psys_power_w`** — the RAPL platform domain (`intel-rapl:1`). One small `execd` reader.
2. **GPU xe freq + throttle reason** (`gpu_act_freq_mhz`, `gpu_driver_freq_mhz`, `gpu_throttled`,
   `gpu_throttle_thermal`) — one small `execd` reader, or fold it into `qmassa_reader.py`.
3. **TCPU/TCPU_PCI thermal zones** (board temps) — only if `inputs.temp` doesn't pick them up.
4. **`npu_power_state`** — a one-line addition to `npu_reader.py`.
5. **DRAM bandwidth fallback** — port `monitor_memory.py`'s PCM path, but only if a target SKU has
   neither the PMU counters nor RDT.

---

## 4. How `telegraf.d/` is laid out

Instead of touching the base `telegraf.conf`, the new stuff goes in drop-in files under
[`telegraf.d/`](../telegraf.d) (which is already mounted and merged in). Each one can be turned on or
off on its own, and any of them will quietly show "no data" on hardware that can't feed it — same as
the readers we already have.

```
telegraf.d/
├── 10-power.conf        # inputs.intel_powerstat  → cpu package power, per-core freq, c-states
├── 20-dram-bw.conf      # inputs.intel_pmu OR inputs.intel_rdt (platform-gated, §5)
├── 30-disk.conf         # inputs.diskio           → util%, read/write MB/s
├── 40-net.conf          # inputs.net + inputs.ethtool
├── 50-interrupts.conf   # inputs.interrupts + tagpass (disk/usb/network classification)
└── 90-tcmi-execd.conf   # execd: psys_power, gpu_throttle (residual gaps only)
```

The new Python readers sit next to the existing ones in `scripts/` and get into the image the same way
`npu_reader.py` does — `COPY`'d in the [Dockerfile](../Dockerfile) and run via `execd`.

**Example — `10-power.conf`:**
```toml
[[inputs.intel_powerstat]]
  package_metrics = ["current_power_consumption", "current_dram_power_consumption",
                     "thermal_design_power"]
  cpu_metrics = ["cpu_frequency", "cpu_c0_state_residency", "cpu_temperature"]
```

**Example — `50-interrupts.conf`.** The version we actually shipped keeps only the numbered IRQs
(those are always devices) and drops everything symbolic in one line — see the note below on why we
went this way instead of a denylist:
```toml
[[inputs.interrupts]]
  [inputs.interrupts.tagpass]
    irq = ["[0-9]*"]
```

The entries being dropped are the kernel's internal per-CPU interrupt counters from
`/proc/interrupts` — scheduler/CPU housekeeping, not actual device I/O. TCMI's
[`monitor_io.py`](../../../../dev-170-system/ros2-intel-optimizations/tcmi/monitor_io.py) filters them
out and we do the same here, since only the disk/usb/network device IRQs matter for the **I** side of
things:

| Symbol | Full form | What it counts |
|--------|-----------|----------------|
| `LOC`  | **Loc**al APIC timer interrupts | Per-CPU local-timer ticks (scheduler tick) |
| `NMI`  | **N**on-**M**askable **I**nterrupts | Hardware faults / watchdog / perf events that can't be masked |
| `IPI`  | **I**nter-**P**rocessor **I**nterrupts | One CPU signalling another (the `IPI*` glob also covers the specific IPI classes below) |
| `TLB`  | **TLB** (Translation Lookaside Buffer) shootdowns | Cross-CPU IPIs to invalidate stale virtual→physical address cache entries |
| `RES`  | **Res**cheduling interrupts | IPIs that kick a remote CPU to run the scheduler (load balancing / wakeups) |
| `CAL`  | Function **cal**l interrupts | IPIs invoking a function on another CPU (`smp_call_function`) |

There's a longer tail of these on some kernels too — `PMI` (perf monitoring), `THR` (thermal event),
`SPU` (spurious), `ERR` (APIC error), `MCP` (machine-check polls), `TRM` (thermal throttle),
`RTR`/`DFR` (threshold/deferred error APIC). That's exactly why we stopped trying to list them all: on
this PTL SoC alone there were eight extra ones beyond the classic set. Keeping only numbered IRQs
sidesteps the whole game — they're all devices, everything symbolic is noise.

---

## 5. DRAM bandwidth

This is the single metric where there isn't one obvious path — it depends on the box. So on each SKU,
work through these in order:

1. **`intel_pmu`** — first check the IMC uncore events are there:
   `ls /sys/bus/event_source/devices/uncore_imc_*`. If they are, read
   `UNC_M_CAS_COUNT.RD`/`.WR`, × 64 B ÷ interval → GB/s. This is the one to reach for — no external
   binary needed.
2. **`intel_rdt`** — if the platform does MBM (`mount -t resctrl` works and `pqos` is around),
   `inputs.intel_rdt` gives you `mbm_total_bytes`/`mbm_local_bytes`. Nice if you want per-core or
   per-workload attribution.
3. **PCM fallback (`execd`)** — port the PCM call from `monitor_memory.py`. Watch out for a few things
   when you do: it writes a `mktemp` file (which breaks on a read-only rootfs, so send it to a
   writable tmpfs path or just parse `pcm`'s stdout), it forces a ≥2s cadence, and it needs
   `perf_event_paranoid=-1`.

The plan: ship (1) as the default `20-dram-bw.conf`, and keep the PCM `execd` around as an opt-in
fallback behind an env flag (see §6).

**How it shook out on PTL:** the IMC free-running counters are there and counting (`perf stat` got
116.6/7.4 MiB in 1s), `perf_event_paranoid` is already `-1`, and RDT/resctrl/pqos aren't present. So
path (1) it is; (2) isn't an option here. The one PTL gotcha: the CPU model comes back masked
(`Genuine Intel(R) 0000`), which trips up the named `UNC_M_CAS_COUNT.*` events since those get looked
up in a model-keyed perfmon JSON. We work around it with the free-running sysfs aliases (the reader
ended up using `data_read`/`data_write`, which are the same counters and don't need the model). Full
notes in [`20-dram-bw.conf.example`](../telegraf.d/20-dram-bw.conf.example).

---

## 6. The knobs (all opt-in, all safe on hardware that lacks the source)

Same idea as the NPU/GPU readers: every new collector has an env switch, so a box without the hardware
(or without privilege) just stays quiet instead of erroring. These live in
[`.env.example`](../.env.example) and `settings.py`:

| Env var | Default | Effect |
|---------|---------|--------|
| `ENABLE_RAPL_POWER` | `true` | load `10-power.conf` |
| `ENABLE_DRAM_BW` | `auto` | `auto`→probe PMU→RDT→off; `pcm`→force PCM execd; `off` |
| `ENABLE_DISK_IO` | `true` | load `30-disk.conf` |
| `ENABLE_NET_IO` | `true` | load `40-net.conf` |
| `ENABLE_INTERRUPTS` | `true` | load `50-interrupts.conf` |
| `ENABLE_GPU_THROTTLE` | `auto` | xe throttle/freq execd (auto-detect `/sys/class/drm/*/device/.../throttle`) |

At startup `entrypoint.sh` reads these and enables/disables the matching `telegraf.d/*.conf`, so the
same image can run different profiles (AMR, industrial arm, plain headless server) without rebuilding.

---

## 7. What we're leaving in TCMI

The *collection* all moves into MM. But two TCMI features are really about sessions and reports, not
collecting metrics, so they stay where they are and just point at MM instead:

- **Session-aligned offline HTML report**
  ([`generate_platform_report.py`](../../../../dev-170-system/ros2-intel-optimizations/tcmi/generate_platform_report.py))
  — MM is live and continuous by design, but the portable-report use case is still useful. Keep the
  report generator, just have it query MM's Prometheus endpoint (`:9273`) for a time window instead of
  reading local CSVs. Same reports, no second collector.
- **ROS 2 KPI merge** (`monitor_stack.py` / `graph_timing.csv`) — push the per-topic latency/frequency
  numbers into MM with `POST /api/v1/metrics/simple`, so they land in the same Prometheus/Grafana as
  everything else.

The upshot: one collector (MM), two ways to consume it — live Grafana, or the TCMI report generator
running as a client against MM. Nothing gets collected twice.

---

## 8. The plan, phase by phase

| Phase | What's in it | Effort | What ships |
|-------|-------|--------|-------------------|
| **P0 — Native plugins, nothing risky** ✅ **DONE** | The loader fix (`--config-directory`) plus `intel_powerstat`, `diskio`, `net`, `ethtool`, and `interrupts` as `telegraf.d/` drop-ins; widened the `inputs.temp` filter to catch cores, nvme, and acpitz; drop-ins `COPY`'d into the image. The `.env`/`settings.py` toggles (§6) also landed. | Low (config-only) | 1 PR: `telegraf.d/` files + `.env` knobs + docs |
| **P1 — DRAM bandwidth** ✅ **DONE** | Promoted to active `20-dram-bw.conf` + `scripts/dram_bw_reader.py` (perf on the IMC free-running `data_read`/`data_write` aliases; model-independent, so it works on masked-model PTL silicon where native `intel_pmu` named events fail). Validated live: 0.4/0.06 GB/s r/w at idle. `intel_rdt` ruled out; PCM fallback documented. | Medium (platform validation) | 1 PR + a short "supported SKUs" doc |
| **P2 — Residual execd readers** ✅ **DONE (psys + turbostat)** | `psys_power` (`rapl_reader.py`, live: 5.9 W psys at idle) and **turbostat R-dimension parser** (`turbostat_reader.py`, opt-in) landed + wired in `90-tcmi-execd.conf` / `60-turbostat.conf.example`. Still TODO: xe GPU throttle/freq, TCPU zones (if `inputs.temp` misses them), `npu_power_state` one-liner. | Medium | 1 PR: `scripts/*.py` + `90-tcmi-execd.conf` |
| **P3 — Grafana + profiles** ✅ **DONE (dashboard + scrape job)** | Ported TCMI's dashboard to MM metric names as a generated model ([`dashboards/`](../dashboards)): uid `tcmi-mm-unified-v1`, 31 panels across **T/C/M/I + a new R (Real-Time Determinism)** row, adding psys power, DRAM bandwidth, per-device IRQ rate, and C0/IPC/SMI panels. Counters wrapped in `rate()`; every panel filtered by a `$host` template var. Shipped a drop-in [`prometheus-scrape-job.yml`](../dashboards/prometheus-scrape-job.yml) pointing Prometheus at MM's `:9273`. **Verified fully live on the PTL reference stack:** scrape job added + hot-reloaded (`promtool`-validated), the `metrics-manager` target is UP, and every panel query resolves through Grafana's datasource proxy against real data (psys 6.5 W, DRAM BW, 45 device IRQs, per-core C0 residency; `$host` = `ptl-system`). Still to do: the AMR / industrial-arm `compose` profiles (preset toggles per workload type). | Medium | Dashboard generator + JSON + scrape job + `compose` profile examples |
| **P4 — Report + ROS 2 bridge** | Point the TCMI report generator at MM's Prometheus; add a small client to push ROS 2 KPIs in. | Medium | Optional companion tool / contrib |

How we check each phase: `curl -s localhost:9273/metrics | grep <new_metric>` on a PTL box, plus the
existing pytest suite ([`tests/`](../tests)). Each phase is its own PR you can review on its own.