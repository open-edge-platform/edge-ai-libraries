#! /bin/bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation

echo "Setting up..."

# Setting up User Mode access to PMU
echo "Setting up User Mode access to PMU..."
echo 2 > /sys/bus/event_source/devices/cpu/rdpmc

# Setting up PMU events for CPU Core #1, running RT workload
echo "Setting up PMU evnets..."
# MEM_LOAD_RETIRED.L2_HIT
wrmsr -p 1 0x186 0x4302d1
# MEM_LOAD_RETIRED.L2_MISS
wrmsr -p 1 0x187 0x4310d1
# MEM_LOAD_RETIRED.L3_HIT
wrmsr -p 1 0x188 0x4304d1
# MEM_LOAD_RETIRED.L3_MISS
wrmsr -p 1 0x189 0x4320d1

echo "Done"