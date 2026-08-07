<!--
Copyright (C) 2025-2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ADR 0001 — How we collect Intel hardware telemetry in Metrics Manager

## The situation

**TCMI** — **T**hermal · **C**ompute · **M**emory · **I/O** — is a hardware-telemetry framework for
Intel Core Platforms. It's a pile of Python scripts that read Intel hardware telemetry — power, thermals,
memory bandwidth, I/O — alongside a ROS 2 workload without touching it. Metrics Manager already runs Telegraf
plus a FastAPI relay in one container, and it's the thing we're upstreaming. Running both meant two collectors,
two config surfaces, and no shared dashboard. So the goal was: one collector, keep all of TCMI's coverage, and
get the metrics into Grafana instead of reading them off `curl`. (That T/C/M/I split is exactly why the dashboard has those
rows — plus the new R for real-time determinism.)

## 1. Use Telegraf plugins by default; write a reader only for the gaps

The native plugins (`intel_powerstat`, `diskio`, `net`, `interrupts`, `temp`, and — for the R
dimension — `turbostat`) cover most of what TCMI did. For the two things none of them can reach, we
wrote small long-running `execd` readers that print InfluxDB line protocol:

- **psys power** — `intel_powerstat` gives you package and DRAM power, but not the RAPL platform
  (psys) domain. psys is the whole-board number, which is the one that matters for a power budget.
- **DRAM bandwidth** — the reference PTL chip reports a masked CPU model
  ("Genuine Intel(R) 0000"), and `intel_pmu` looks up named events by model, so it comes up empty.
  Reading the IMC free-running counters through `perf` doesn't depend on the model.

We *don't* write a reader for turbostat. We used to — but `[[inputs.turbostat]]` landed in Telegraf
v1.36.0, and this image builds 1.38.4, so the native plugin is already compiled in and covers the same
IPC/SMI/per-core signals. Using it drops us from three custom scripts to two. It stays opt-in (ships
disabled) because turbostat is tied to the kernel version and needs MSR access.

**What we didn't do, and why:** Intel PCM (a heavy external binary, more CVE surface to worry about);
`inputs.intel_pmu` (dead on arrival because of the masked model); leaving the TCMI scripts as a
separate stack (which is the whole thing we were trying to get rid of).

**The catch:** two scripts to maintain. But each one is model-independent and fails soft — if the
tool, counter, or permission isn't there, the reader parks itself instead of hot-looping under execd.

## 2. Turn collectors on and off with `ENABLE_*` env vars

`entrypoint.sh` renames `.conf` ↔ `.conf.disabled` at startup (and copies `.conf.example` for the
opt-in ones), based on `ENABLE_*` env vars that show up in `.env.example` and `settings.py`.
`--config-directory` then loads only what's enabled.

**Why bother:** the collectors need different things from the platform — turbostat wants a
kernel-matched `linux-tools`, DRAM bandwidth wants perf and an exposed PMU. One switch per collector
means a missing dependency can't take down the whole config, and you can pick a profile per deployment
without editing Telegraf files by hand.

**The catch:** startup does a little file shuffling. It's idempotent, so restarts are fine. The
alternative — one big static config — fails hard the moment a box is missing a dependency.

## 3. Filter interrupts by "is it numeric," not by a denylist

`50-interrupts.conf` keeps only the numbered IRQ lines (`irq = ["[0-9]*"]`). On x86, device interrupts
are numbered; the kernel's internal housekeeping counters are symbolic (LOC/NMI/IPI and a bunch of
arch-specific ones). We started with a denylist of those symbols and it turned into whack-a-mole — this
PTL SoC alone had eight extras beyond the usual set. Keeping only the numbered lines gets exactly the
device IRQs on any x86 box, with nothing to maintain per chip.

## 4. Generate the Grafana dashboard from a script

`dashboards/generate_dashboard.py` spits out the dashboard JSON instead of us hand-editing ~700 lines.
The old→new metric mapping and the panel layout math live in one readable place, and you can retarget a
different datasource UID with `--ds-uid`.

**The catch:** if someone edits panels in the Grafana UI and someone else edits the generator, they'll
drift apart. The generator is the source of truth — regenerate the JSON, don't hand-patch it.

## 5. Know which metrics are counters and which are gauges

Counters (`diskio_*`, `net_bytes_*`, `interrupts_total`) get wrapped in `rate(...[1m])`; gauges
(power, temperature, frequency, DRAM bandwidth, memory) get queried straight. Get this backwards and
you'll see lines that only ever climb instead of an actual rate — calling it out here so nobody wires a
new panel the wrong way.
