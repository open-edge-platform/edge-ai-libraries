#!/bin/bash

set -euo pipefail

OUTPUT_FILE="./.collector-signals/.collector.out"
RUN_FILE="./.collector-signals/.collector.run"
GPU_LOG="qmassa_output.json"
TURBOSTAT_LOG="turbostat_output.log"
FREE_LOG="free_output.log"

command_exists() {
    command -v "$1" >/dev/null 2>&1 || {
        echo >&2 "Error: $1 is not installed."
        exit 1
    }
}

# Check for required commands
command_exists turbostat
command_exists free
command_exists qmassa
command_exists jq

# Check turbostat version
TURBOSTAT_EXIT_CODE=0
turbostat -v || TURBOSTAT_EXIT_CODE=$?
if [ $TURBOSTAT_EXIT_CODE -eq 2 ]; then
    echo "Reinstalling turbostat"
    apt-get update && \
    apt-get install --yes \
        linux-tools-$(uname -r) \
        linux-cloud-tools-$(uname -r)
    command_exists turbostat
fi

while true; do
    # Wait for the .collector.run file to be created
    while [ ! -f "$RUN_FILE" ]; do
        echo "Waiting for $RUN_FILE"
        sleep 1
    done

    # Remove any existing logs
    rm -f "$TURBOSTAT_LOG" "$FREE_LOG" "$GPU_LOG" "$OUTPUT_FILE"

    # Launch turbostat
    turbostat --show Avg_MHz,Busy%,PkgTmp,PkgWatt --interval 2 > "$TURBOSTAT_LOG" &
    TURBOSTAT_PID=$!

    # Launch free
    free -s 2 -h > "$FREE_LOG" &
    FREE_PID=$!

    # Launch qmassa
    qmassa -x -t "$GPU_LOG" &
    QMASSA_PID=$!

    # Wait for the .collector.run file to be removed
    while [ -f "$RUN_FILE" ]; do
        sleep 1
    done

    # Kill all background processes
    kill $TURBOSTAT_PID
    kill $FREE_PID
    kill $QMASSA_PID

    # Ensure $GPU_LOG exists before proceeding
    while [ ! -f "$GPU_LOG" ]; do
        echo "Waiting for $GPU_LOG to be generated..."
        sleep 1
    done

    # Validate if JSON data is available
    if ! jq -e '.states[-1].timestamps, .states[-1].devs_state[-1].dev_stats.eng_usage' "$GPU_LOG" > /dev/null; then
        echo "Error: Missing timestamps or engine utilization data in $GPU_LOG"
        continue
    fi

    # Extract timestamps as an array
    GPU_TIMESTAMPS=$(jq -r '[.states[-1].timestamps[]] | @csv' "$GPU_LOG")

    # Extract and rename each engine's utilization (prefixing with `gpu_`)
    GPU_ENGINE_UTILS=$(jq -r '
      .states[-1].devs_state[-1].dev_stats.eng_usage
      | to_entries[]
      | "gpu_engine_\(.key): [" + (.value | map(tostring) | join(", ")) + "]"
    ' "$GPU_LOG")

    # Extract GPU Power Usage
    GPU_POWER_USAGE=$(jq -c '[.states[-1].devs_state[-1].dev_stats.power[].gpu_cur_power]' qmassa_output.json)

    # Extract GPU Frequency
    GPU_FREQ=$(jq -c '[.states[-1].devs_state[-1].dev_stats.freqs[][0].cur_freq]' qmassa_output.json)

    # Extract CPU metrics from turbostat
    CPU_FREQ=$(awk '$1 ~ /^[0-9.]+/ && $2 ~ /^[0-9.]+/ {sum+=$1*$2; busy+= $2} END {if (busy > 0) print sum/busy; else print "N/A"}' "$TURBOSTAT_LOG")
    CPU_UTIL=$(awk '$2 ~ /^[0-9.]+/ {sum+=$2; count++} END {if (count>0) print sum/count; else print "N/A"}' "$TURBOSTAT_LOG")
    CPU_TEMP=$(awk '$3 ~ /^[0-9.]+/ {sum+=$3; count++} END {if (count>0) print sum/count; else print "N/A"}' "$TURBOSTAT_LOG")
    PKG_POWER=$(awk '$4 ~ /^[0-9.]+/ {sum+=$4; count++} END {if (count>0) print sum/count; else print "N/A"}' "$TURBOSTAT_LOG")
    
    # Extract memory utilization from free
    MEM_UTIL=$(awk '/Mem:/ { used+=$3; total+=$2; count++ } END { if (count > 0) print (used/total) * 100 }' "$FREE_LOG")
    
    # Extract system temperature from thermal_zone0
    SYS_TEMP=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null | awk '{print $1/1000}')

    # Write all data to $OUTPUT_FILE
    {
        printf "=== System Performance Metrics ===\n"
        printf "CPU Frequency: %.2f MHz\n" "$CPU_FREQ"
        printf "CPU Utilization: %.2f %%\n" "$CPU_UTIL"
        printf "Memory Utilization: %.2f %%\n" "$MEM_UTIL"
        printf "Package Power: %.2f W\n" "$PKG_POWER"
        printf "CPU Temperature: %.2f C\n" "$CPU_TEMP"
        printf "System Temperature: %.2f C\n" "$SYS_TEMP"
        printf "GPU_Timestamps: %s\n" "$GPU_TIMESTAMPS"
        printf "GPU Power Usage: %s W\n" "$GPU_POWER_USAGE"
        printf "GPU Frequency: %s MHz\n" "$GPU_FREQ"
        printf "%s\n" "$GPU_ENGINE_UTILS"
    } > "$OUTPUT_FILE"

    echo "Metrics saved to $OUTPUT_FILE"

done
