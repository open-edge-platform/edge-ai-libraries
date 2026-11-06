<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Native metric migration for 2026.3.0

The unreleased 2026.3.0 native collectors use bytes, bytes/second, Hz, W and
degrees Celsius with explicit unit-bearing field names. This is a **breaking,
one-time contract migration** for the native Docker image. Old names are not
emitted as aliases. Upgrade collectors and dashboards together.

Standard Telegraf inputs (including powerstat, Turbostat, CPU, memory, network
and disk) are unchanged. So are the qmassa JSON input schema, engine/CPU
utilization percentages, counts, state/throttle flags, process RSS bytes and
`rapl_power_power_w`. Percentages remain 0–100 (or the existing multi-core/
multi-engine semantics), not newly introduced 0–1 ratios.

## Prometheus names and conversions

Multiply the previous value by the factor below to obtain the new value.
For GPU memory, `{...}` denotes the existing memory field names; all fields
from qmassa's device/client memory maps receive the `_bytes` suffix.
Tags, device/tile identities and collector selection behavior are preserved.

| Previous name | New name | Factor |
|---|---|---|
| `cpu_frequency_avg_frequency` | `cpu_frequency_avg_frequency_hz` | 1,000 |
| `cpu_core_class_frequency_avg` | `cpu_core_class_frequency_avg_hz` | 1,000 |
| `gpu_frequency` (legacy `value` alias) | `gpu_frequency_cur_freq_hz` | 1,000,000 |
| `gpu_frequency_{act,cur,min,max}_freq` | `gpu_frequency_{act,cur,min,max}_freq_hz` | 1,000,000 |
| `gpu_power` | `gpu_power_power_w` | 1 |
| `gpu_temperature` | `gpu_temperature_temperature_c` | 1 |
| `gpu_fan` (RPM) | `gpu_fan_speed_hz` (rotations/second) | 1/60 |
| `gpu_memory_{smem_total,smem_used,vram_total,vram_used}` | Same names with `_bytes` appended | 1 |
| `gpu_client_{smem_used,smem_rss,vram_used,vram_rss}` | Same names with `_bytes` appended | 1 |
| `npu_power` | `npu_power_w` | 1 |
| `npu_frequency` (already corrected Hz) | `npu_frequency_hz` | 1 |
| `npu_temperature` | `npu_temperature_c` | 1 |
| `npu_bandwidth` (decimal MB/s) | `npu_bandwidth_bytes_per_second` | 1,000,000 |
| `npu_memory_mb` (actually MiB) | `npu_memory_bytes` | 1,048,576 |
| `npu_frequency_max_mhz` | `npu_frequency_max_hz` | 1,000,000 |
| `memory_bandwidth_{read,write,total}_mibps` | `memory_bandwidth_{read,write,total}_bytes_per_second` | 1,048,576 |

Line-protocol measurement names stay unchanged; their fields are renamed
accordingly. For example, `npu` now has `frequency_hz` and `memory_bytes`;
`gpu_power` has `power_w` instead of `value`. There is no second GPU
`value` field repeating requested frequency.

The NPU frequency factor assumes the already-corrected native Hz calculation.
Earlier uncorrected builds reported values 1e6 too small and also used the
wrong Arrow Lake PLL formula; their historical data needs separate correction,
not just a rename. The current formulas remain MTL/ARL `ratio * 50e6 * 2/3`
and LNL/PTL `ratio * 50e6 / 2`.

## Display and query units

Convert raw metrics at the display or query boundary:

- Clocks: divide Hz by `1e6` for MHz or `1e9` for GHz.
- Memory sizes: divide bytes by `1048576` for MiB or `1073741824` for GiB.
- Whole-system DRAM throughput: divide bytes/s by `1e9` for decimal GB/s.
- NPU throughput: divide bytes/s by `1e6` for decimal MB/s.

Examples for external dashboards:

```promql
gpu_frequency_act_freq_hz / 1e6
npu_memory_bytes / 1048576
memory_bandwidth_total_bytes_per_second / 1e9
gpu_fan_speed_hz * 60
```

Do **not** apply `rate()` again to bandwidth metrics: they are already rates.
The memory-controller collector converts the sysfs MiB-per-event scale to
bytes before dividing by elapsed time. NPU bandwidth preserves actual sampling
interval and single 32-bit counter-wrap handling. Missing optional NPU data
stays absent; measured zeros stay zero. Memory is no longer rounded to two
decimal places of MiB before export.

## Upgrade checklist

1. Upgrade the native plugins for every producer read by your dashboards.
   Restart/recreate the selected services so old collector processes stop.
2. Replace old names in PromQL, recording/alert rules and custom ingestion
   clients. Rescale numeric thresholds using the table; do not splice old and
   new raw values into one history without conversion.
3. Merge new examples into locally retained configuration files. Mounted
   configurations are not automatically overwritten.
4. Verify the new metric families at `/metrics`, check device/tile labels and
   missing-data behavior, and compare dashboard values after display conversion.

## TUI configuration migration

Upgrade `mm-tui` with the native collectors. The
[terminal dashboard](./terminal-dashboard.md) performs display conversions;
do not pre-convert the Prometheus endpoint or it will scale the values twice.

For retained custom chart configuration, replace the old DRAM chart IDs
`memory.bandwidthMiBps`, `memory.readMiBps` and `memory.writeMiBps` with
`memory.bandwidthGBps`, `memory.readGBps` and `memory.writeGBps`. Use `GB/s`
as the display unit and convert any fixed MiB/s bounds by multiplying by
`1048576 / 1e9`. Merge the current examples rather than discarding local settings.
