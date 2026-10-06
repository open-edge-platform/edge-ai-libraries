#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
echo 0 | tee /sys/devices/system/cpu/cpu*/power/energy_perf_bias
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
sudo systemctl disable ondemand
echo 20 > "/sys/kernel/debug/dri/0000:00:02.0/gt0/pf/exec_quantum_ms"
echo 20000 > "/sys/kernel/debug/dri/0000:00:02.0/gt0/pf/preempt_timeout_us"
