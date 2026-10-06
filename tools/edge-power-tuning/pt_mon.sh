#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# pt_mon.sh - Power and thermal monitor for the CPU package and platform.
#
# Uses Intel's turbostat to print a periodic summary of package temperature and
# the RAPL power domains, so you can watch the effect of a power profile (e.g.
# one applied by set_power_profile.sh) under load.
#
# This script is provided as a REFERENCE monitor. You are free to use any other
# power-monitoring tool instead (e.g. turbostat directly, powertop,
# intel_gpu_top, a BMC/OEM utility, or reading /sys/class/powercap/intel-rapl*).
#
# Usage: ./pt_mon.sh          # sample every 2 s until Ctrl-C
#
# Columns shown (all powers in watts, temp in degrees C):
#   PkgTmp   - package temperature
#   SysWatt  - whole-platform (psys) power         [RAPL psys / MSR 0x65C]
#   PkgWatt  - package power: CPU + iGPU + uncore   [RAPL package / MSR 0x610]
#   CorWatt  - CPU cores power
#   GFXWatt  - integrated GPU power
#   RAMWatt  - DRAM / memory controller power
#
# Notes:
#   * -S / --Summary prints one aggregate row per interval (no per-CPU rows).
#   * Requires root (turbostat reads MSRs); hence sudo below.
#
# Why SysWatt can read 0.00 ("not showing actual power"):
#   turbostat derives power as delta(energy) / delta(time). The platform
#   (psys) energy counter lives in MSR 0x65C. On some Intel Core Ultra
#   platforms (e.g. Core Ultra 5 335 / Arrow Lake) this register EXISTS and is
#   readable, but the firmware/PCU never updates it -- it stays frozen at a
#   static placeholder value. A frozen counter means every delta is 0, so
#   turbostat prints SysWatt = 0.00. This is a firmware/OEM limitation, not a
#   turbostat or script bug, and there is no software switch to enable it.
#   Confirm with: `grep -r . /sys/class/powercap/intel-rapl*/name` -- if there
#   is no domain named "psys", the platform domain is unavailable. In that case
#   use PkgWatt (CPU package = cores + iGPU + uncore) as the effective power
#   figure, or measure whole-system power from the battery discharge rate
#   (/sys/class/power_supply/BAT*/power_now).
#   The check_psys() helper below detects the frozen-counter case and warns.

set -x

# check_psys - warn if the platform (psys) energy counter is frozen/unavailable,
# which is why SysWatt would print 0.00. Best-effort; never aborts monitoring.
check_psys() {
    if ! grep -qs psys /sys/class/powercap/intel-rapl*/name; then
        echo "[pt_mon] NOTE: no 'psys' RAPL domain on this platform -> SysWatt will read 0.00 (use PkgWatt instead)" >&2
        return
    fi
    if command -v rdmsr >/dev/null 2>&1; then
        sudo modprobe msr 2>/dev/null || true
        local a b
        a=$(sudo rdmsr -f 31:0 -d 0x65C 2>/dev/null) || return
        sleep 1
        b=$(sudo rdmsr -f 31:0 -d 0x65C 2>/dev/null) || return
        if [ -n "$a" ] && [ "$a" = "$b" ]; then
            echo "[pt_mon] NOTE: psys energy counter (MSR 0x65C) is frozen at $a -> SysWatt will read 0.00 (firmware limitation; use PkgWatt)" >&2
        fi
    fi
}

check_psys
# --interval 2  : refresh every 2 seconds
# --show ...    : restrict output to the temperature + power columns of interest
sudo turbostat -S --interval 2 --show PkgTmp,PkgWatt,CorWatt,GFXWatt,RAMWatt,SysWatt | tee pt_mon.txt
