#!/bin/bash
total=0
count=0
for cpu_freq_file in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq; do
    [ -f "$cpu_freq_file" ] || continue
    freq=$(cat "$cpu_freq_file")
    total=$((total + freq))
    count=$((count + 1))
done
if [ $count -gt 0 ]; then
    avg=$((total / count))
    echo "cpu_frequency_avg frequency=${avg}"
fi
