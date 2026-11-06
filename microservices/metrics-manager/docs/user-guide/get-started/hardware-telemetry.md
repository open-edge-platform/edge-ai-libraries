<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Hardware Telemetry Collectors

> [!IMPORTANT]
> This page documents the legacy Python-reader images and their configuration,
> retained for users of older images and charts. For the native Docker image
> in 2026.3.0, use [Native Docker Collectors](./native-docker-collectors.md)
> and the [metric migration guide](./native-metric-migration.md).
> The legacy `ENABLE_*` switches below are not the native image's interface.

Besides the default CPU, memory, temperature, GPU, and NPU metrics, Metrics Manager can
collect a set of additional Intel hardware metrics: package and platform power,
DRAM bandwidth, per-core frequency and C-state residency, interrupts, disk and network
I/O, GPU throttle state, and (opt-in) turbostat diagnostics.

These collectors cover what **TCMI** (**T**hermal, **C**ompute, **M**emory, **I/O**)
measures. TCMI describes the four areas of hardware behavior that matter for robotics and
physical-AI workloads on Intel platforms. Each collector is a separate, opt-in switch, so
you incur only the cost of the collectors you enable.

> [!NOTE]
> **Everything on this page is off by default.** With no `ENABLE_*` variable set, the
> container produces the same metrics as before these collectors existed. This also holds
> when you mount your own `telegraf.conf`.

## Collectors at a Glance

| Variable              | Default | Telegraf drop-in       | Source                                      | Main series (Prometheus names)                                                   |
| --------------------- | ------- | ---------------------- | ------------------------------------------- | -------------------------------------------------------------------------------- |
| `ENABLE_RAPL_POWER`   | `false` | `10-power.conf`        | `inputs.intel_powerstat`                    | `powerstat_package_*`, `powerstat_core_*`                                        |
| `ENABLE_PSYS_POWER`   | `false` | `90-rapl-psys.conf`    | `rapl_reader.py` (RAPL sysfs)               | `rapl_power_power_w{domain="psys"\|"package-0"}`                                 |
| `ENABLE_DRAM_BW`      | `false` | `20-dram-bw.conf`      | `dram_bw_reader.py` (`perf stat`)           | `dram_bw_read_gbps`, `dram_bw_write_gbps`, `dram_bw_total_gbps`                  |
| `ENABLE_DISK_IO`      | `false` | `30-disk.conf`         | `inputs.diskio`                             | `diskio_*`                                                                       |
| `ENABLE_NET_IO`       | `false` | `40-net.conf`          | `inputs.net`, `inputs.ethtool`              | `net_*`, `ethtool_*`                                                             |
| `ENABLE_INTERRUPTS`   | `false` | `50-interrupts.conf`   | `inputs.interrupts`                         | `interrupts_total{irq,type,device}`                                              |
| `ENABLE_TEMP_STATS`   | `false` | `70-temp-stats.conf`   | `inputs.temp` at 100 ms + aggregator        | `temp_highres_temp_min`, `_max`, `_mean`                                         |
| `ENABLE_GPU_THROTTLE` | `false` | `91-gpu-throttle.conf` | `gpu_throttle_reader.py` (Intel `xe` sysfs) | `gpu_throttle_act_freq_mhz`, `gpu_throttle_throttled`, `gpu_throttle_throttle_*` |
| `ENABLE_TURBOSTAT`    | `false` | `60-turbostat.conf`    | `inputs.turbostat`                          | `turbostat_*` (IPC, SMI, per-core temperature, ...)                              |

The NPU `power_state` field (`npu_power_state`) is not behind a toggle; it is part of the
existing NPU reader. Accepted "on" values are `true`, `1`, `yes`, `on`, and `auto`
(case-insensitive). The table above lists the legacy collector variables;
the [current variable reference](./environment-variables.md) describes native images.

## Quick Start: The TCMI Preset

To turn on the set of collectors TCMI users typically need on an Intel host, add this to
your `.env` (copy it from `.env.example`):

```bash
# .env
ENABLE_RAPL_POWER=true
ENABLE_PSYS_POWER=true
ENABLE_DRAM_BW=auto        # also needs an image built with INSTALL_PERF=true (see below)
ENABLE_DISK_IO=true
ENABLE_NET_IO=true         # sees host NICs only with the host-nic-telemetry profile
ENABLE_INTERRUPTS=true
ENABLE_GPU_THROTTLE=true   # Intel xe driver only
```

`ENABLE_TEMP_STATS` and `ENABLE_TURBOSTAT` are left out on purpose: they are for
specific tuning work and add sampling load. Enable them separately.

Then recreate the container:

```bash
docker compose up -d
```

> [!WARNING]
> Changing any `ENABLE_*` variable takes effect only after the container is recreated.
> There is no hot reload.

Check what was loaded:

```bash
docker compose logs metrics-manager | grep -E "^\[(INFO|WARN)\]  "
```

```text
[INFO]   10-power: ENABLED
[INFO]   20-dram-bw: ENABLED
[INFO]   30-disk: ENABLED
...
[INFO]   60-turbostat: disabled
```

A collector that was requested but cannot work is skipped with a `[WARN]` line (for
example turbostat without a usable binary, or `ENABLE_DRAM_BW=auto` without `perf` in
the image). The rest of Telegraf keeps running.

## Supported Hardware and Expected Series Count

Collectors never disrupt core metrics: on hardware that lacks a data source they emit
nothing and log why (see [Troubleshooting](#troubleshooting)). Plan for the following:

| Collector             | Where it gives no or partial data                                                                                                                                                                                                                 |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ENABLE_DRAM_BW`      | No data on CPUs without the IMC free-running PMU, for example Skylake-SP (Intel® Xeon® 8176), which exposes only `uncore_imc_0..5`. The reader idles.                                                                                             |
| `ENABLE_GPU_THROTTLE` | Intel `xe` driver only. It idles on `i915`, which is still the default driver on some client GPUs (for example Intel® Core™ Ultra Series 1 and Intel® Core™ Ultra Series 2).                                                                      |
| `ENABLE_RAPL_POWER`   | Intel® Core™ Ultra Series 2 and Intel® Core™ Ultra Series 3 (formerly codenamed as Panther Lake) client parts: no `cpu_temperature` and no C1/C6 residency, only frequency and C0. Skylake-SP: one `uncore_frequency` error is logged at startup. |
| `ENABLE_NET_IO`       | In the default bridge deployment it reports only the container's own interface. See [Network metrics](#network-metrics-and-the-host-nic-profile).                                                                                                 |

Some collectors scale with the number of CPU cores or devices. Measured per Prometheus
scrape on a 112-thread Intel® Xeon® Platinum 8176:

| Collector           | Lines per scrape (112 threads) | Notes                                                                         |
| ------------------- | ------------------------------ | ----------------------------------------------------------------------------- |
| `ENABLE_RAPL_POWER` | about 650                      | Per-core frequency, temperature, and C-state series scale with core count.    |
| `ENABLE_INTERRUPTS` | about 150 (21 KB)              | One `interrupts_total` series per device IRQ, not per CPU.                    |
| `ENABLE_TURBOSTAT`  | about 2,050 per sample         | Per-core diagnostics. Use it for engineering work, not continuous monitoring. |

On smaller client systems the same collectors produce far fewer lines. Measured per
scrape on a 6-CPU Intel® Core™ Ultra Series 3 and a 16-CPU Intel® Core™ Ultra Series 2 system:
`ENABLE_INTERRUPTS` 40 and 57 lines, `ENABLE_TURBOSTAT` 266 and 612 lines, and the full TCMI
preset about 167 and 202 lines in total (3.5 KB without any collector).

> [!NOTE]
> Every Telegraf sample is also forwarded to each `/metrics/stream` Server-Sent Events
> (SSE) client every 500 ms, so large collectors increase the size of every stream frame.
> Enable only what you use.

## Requirements and Behavior per Collector

### Power: `ENABLE_RAPL_POWER` and `ENABLE_PSYS_POWER`

- Need the privileged container (the compose default), `/sys` mounted read-only, and
  `pid: host`. Running Average Power Limit (RAPL) `energy_uj` is readable by root only;
  without privilege the readers find nothing readable and idle.
- Kernel modules: `intel_rapl_common`, `msr`, `cpufreq`, `intel-uncore-frequency`.
- `ENABLE_PSYS_POWER` adds the RAPL platform (`psys`) domain, the best Linux proxy for
  whole-board power (CPU, iGPU, NPU, and memory). `intel_powerstat` does not expose it.
- Package and psys power are gauges in watts. DRAM RAPL power is not collected by
  default because client SoCs have no DRAM subzone.

### DRAM Bandwidth: `ENABLE_DRAM_BW`

The reader runs `perf stat` on the integrated memory controller (IMC) free-running counters
and reports ready-to-use GB/s. Telegraf's native `inputs.intel_pmu` plugin is not used for
three reasons:

- It needs per-model perfmon event JSON files (from the `intel/perfmon` project) that the
  image does not ship, and the files must match the CPU model.
- On an Intel® Core™ Ultra Series 1 CPU (Intel® Core™ Ultra 5 125H, Telegraf 1.39.3) the
  `UNC_M_CAS_COUNT_RD/WR` events did work under memory load: about 11.0 GB/s read and 5.5 GB/s
  write, against 10.6 and 5.6 GB/s from `perf stat` over the same period (single samples). The
  plugin returns raw per-IMC cache-line counts, so you must multiply by 64 bytes and take a
  rate yourself. The counters are also multiplexed, so the values are scaled estimates.
- The `*_CAS_COUNT_FREERUN` events read zero under the same load. On CPUs whose model is
  not in the perfmon event tables the plugin cannot be used at all.

`inputs.intel_pmu` is a reasonable alternative if you already maintain the event files.

- `perf` comes from the `linux-perf` Debian package (GPL-2.0), which is **not** in the
  published image. Build your own image with it:

  ```bash
  INSTALL_PERF=true make build
  # or: docker compose build --build-arg INSTALL_PERF=true metrics-manager
  ```

  It adds about 150 MB to the image.
- Set `ENABLE_DRAM_BW=auto`. If `perf` is missing, the entrypoint logs
  `ENABLE_DRAM_BW=auto but perf not installed` and skips the drop-in.
- Needs `perf_event_paranoid` at `0` or lower (`cat /proc/sys/kernel/perf_event_paranoid`)
  and the performance monitoring unit (PMU) to be exposed
  (`ls /sys/bus/event_source/devices/uncore_imc_free_running*`).
- Sampling window: `DRAM_BW_INTERVAL` (seconds, default `1`).

### Interrupts: `ENABLE_INTERRUPTS`

Emits one `interrupts_total` series per numbered (device) IRQ, with `irq`, `type`, and
`device` tags. Kernel housekeeping counters (`LOC`, `NMI`, `IPI`, ...) and the per-CPU
breakdown are dropped. Keeping per-CPU fields would produce about 16,000 lines per
scrape on a 112-thread host. If you need per-CPU affinity, remove
`fieldinclude = ["total"]` in `telegraf.d/50-interrupts.conf` and accept the cardinality.
It is a counter, so query it with `rate()`.

### Disk I/O: `ENABLE_DISK_IO`

Collects whole physical disks only. The default device filter is
`nvme[0-9]*n[0-9]`, `sd[a-z]`, `vd[a-z]`, and `mmcblk[0-9]`. It skips loop, RAM, and
device-mapper devices and partitions. It also misses the 27th SCSI disk onward
(`sdaa`, ...) and NVMe namespaces 10 and above. The series are counters.

### Network Metrics and the Host-NIC Profile

`ENABLE_NET_IO` loads `inputs.net` and `inputs.ethtool`. In the default bridge
deployment they see only the container's own interface (usually `eth0`), not the host's
NICs. To report the host's physical NICs, opt in to the `host-nic-telemetry` Compose
profile. It runs the same image with `network_mode: host` and enables `ENABLE_NET_IO` by
default:

```bash
docker compose stop metrics-manager
docker compose --profile host-nic-telemetry up -d metrics-manager-host-nic
```

> [!WARNING]
> This changes the networking model for clients that connect through the
> `metrics-manager` service name, and the API and metrics ports bind directly on the
> host. Always name `metrics-manager-host-nic` explicitly: starting the profile without
> a service name also starts the default service. Switch back with:
>
> ```bash
> docker compose --profile host-nic-telemetry stop metrics-manager-host-nic
> docker compose up -d metrics-manager
> ```

### GPU Throttle: `ENABLE_GPU_THROTTLE`

Reads the Intel `xe` DRM sysfs tree for the achieved GPU frequency and throttle reasons
(thermal, PL1, PL2, PROCHOT). It complements the existing GPU metrics, which report the
requested frequency but not the achieved one. A requested frequency above the achieved
frequency together with a non-zero throttle flag means the hardware held the GPU back.
Hosts using the `i915` driver produce no data.

### Turbostat: `ENABLE_TURBOSTAT`

Turbostat is an engineering diagnostic. It adds instructions per cycle (IPC), which
distinguishes busy from stalled; system management interrupt (SMI) counts, a common hidden
cause of latency spikes; per-core temperature; and per-core interrupts. The summary row
carries `core="-"`, so filter per-core queries with `core!="-"`.

- The image ships **no** turbostat binary because it is coupled to the kernel version.
  Compose bind-mounts the host's kernel-matched binary from `TURBOSTAT_BIN`. When you use
  `make up` with `ENABLE_TURBOSTAT=true` (in the environment or `.env`), the Makefile
  resolves it for you. When you run `docker compose` directly, set it yourself:

  ```bash
  export TURBOSTAT_BIN=$( [ -x /usr/lib/linux-tools/$(uname -r)/turbostat ] \
    && echo /usr/lib/linux-tools/$(uname -r)/turbostat || command -v turbostat )
  docker compose up -d
  ```

- Do not write a kernel-specific path into `.env`; it breaks on the next kernel update.
- Needs model-specific register (MSR) access (`msr` module, privileged container). Before
  loading the drop-in the entrypoint checks that the binary is a runnable file and that
  `/dev/cpu/0/msr` can be opened. If either check fails, it logs `[WARN]  60-turbostat: ...`
  and skips the collector instead of letting turbostat restart in a loop.
- `TURBOSTAT_INTERVAL` sets the sampling cadence in seconds (default `5`).
- The Helm chart has no turbostat bind-mount. Turbostat is a Docker Compose feature
  in this release.

### High-Frequency Temperature: `ENABLE_TEMP_STATS`

Adds `temp_highres_*` series sampled every 100 ms and aggregated to per-second
minimum, maximum, and mean for the CPU package sensors. The default `temp` input keeps its
1-second cadence.

## Using Your Own `telegraf.conf`

You can still mount your own `telegraf.conf` with `TELEGRAF_CONFIG`. The container
always starts Telegraf with `--config-directory /etc/telegraf/active.d`, which holds only
the collectors you enabled. With every toggle off that directory is empty, so your
configuration runs unchanged. Native images use the separate
[native collector selection](./native-docker-collectors.md) interface instead.

## Querying the Metrics

Metrics Manager exposes everything on `:9273` in Prometheus format; it does not ship
dashboards. A scrape-job snippet is in `dashboards/prometheus-scrape-job.yml`. The Helm
chart can create a `ServiceMonitor` (see [Helm Deployment](./deploy-with-helm.md)).

Prometheus appends the field name to the measurement name, so `rapl_power` with field
`power_w` becomes `rapl_power_power_w`. Counters need `rate()`; gauges are queried directly:

```promql
# Gauges
rapl_power_power_w{domain="psys"}                       # platform power (W)
powerstat_package_current_power_consumption_watts       # CPU package power (W)
dram_bw_read_gbps                                       # DRAM read bandwidth (GB/s)
gpu_throttle_act_freq_mhz                               # achieved GPU frequency
temp_highres_temp_max{sensor=~"coretemp_package_id_.*"} # needs ENABLE_TEMP_STATS
turbostat_ipc{core!="-"}                                # needs ENABLE_TURBOSTAT

# Counters
rate(diskio_io_time[1m]) / 10                           # disk utilization %
rate(net_bytes_recv[1m])                                # network receive (bytes/s)
rate(interrupts_total[1m])                              # interrupts per second

# NPU PCI power state: -1 unknown, D0=0, D1=1, D2=2, D3hot=3, D3cold=4
npu_power_state
```

> [!NOTE]
> Telegraf's Prometheus output serves only the last collected value. Scrape at an
> interval no longer than Telegraf's 1 s collection interval, or intermediate samples are
> lost.

## Troubleshooting

**A metric is missing.** Check the startup log first, then the reader's trace log. The
readers park themselves instead of exiting when their data source is absent, so a missing
metric is usually a logged reason, not an error:

```bash
docker compose logs metrics-manager | grep -E "WARN|disabled"
docker exec metrics-manager tail -n 20 /app/rapl_reader_trace.log
docker exec metrics-manager tail -n 20 /app/dram_bw_reader_trace.log
docker exec metrics-manager tail -n 20 /app/gpu_throttle_reader_trace.log
```

A line such as `entering idle mode: perf could not count IMC free-running events` names the
cause. To confirm the readers are running:

```bash
docker exec metrics-manager ps -ef | grep -E 'rapl_reader|dram_bw_reader|gpu_throttle_reader|npu_reader'
```

**Turbostat is skipped.** Read the `[WARN]  60-turbostat` line: it distinguishes a missing
binary, a wrapper script or kernel mismatch, and missing MSR access.

**`ENABLE_DRAM_BW=auto` does nothing.** The image has no `perf`. Rebuild with
`INSTALL_PERF=true`.

**Too many series.** Disable the collector, or for interrupts keep the default per-IRQ
total. See [Expected Series Count](#supported-hardware-and-expected-series-count).

## Supporting Resources

- [Environment Variables](./environment-variables.md)
- [How It Works](../how-it-works.md)
- [Helm Deployment](./deploy-with-helm.md)
- [System Requirements](./system-requirements.md)
- [Troubleshooting](../troubleshooting.md)

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0
