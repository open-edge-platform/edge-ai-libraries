#!/bin/bash
# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Entrypoint script for Metrics Manager
# Initializes required directories and files, then starts supervisor

set -e

echo "[INFO] Starting Metrics Manager..."

# Ensure directories exist
mkdir -p /app/custom-metrics

# Ensure named pipe for qmassa exists
if [ ! -p /app/qmassa.fifo ]; then
    mkfifo /app/qmassa.fifo 2>/dev/null || true
fi
chmod 666 /app/qmassa.fifo 2>/dev/null || true

# Check if custom telegraf config is mounted
if [ -n "$TELEGRAF_CONFIG_PATH" ] && [ -f "$TELEGRAF_CONFIG_PATH" ]; then
    echo "[INFO] Using Telegraf config: $TELEGRAF_CONFIG_PATH"
else
    echo "[INFO] Using default Telegraf config"
fi

# -----------------------------------------------------------------------------
# TCMI collector gating
# -----------------------------------------------------------------------------
# Telegraf is launched with --config-directory /etc/telegraf/telegraf.d, which
# loads only files ending in `.conf`. We gate each hardware-telemetry drop-in on
# an ENABLE_* env var by toggling its extension:
#   enabled  -> <name>.conf            (loaded)
#   disabled -> <name>.conf.disabled   (ignored by --config-directory)
# Opt-in drop-ins ship as `<name>.conf.example` and are activated by copying.
# This lets one image serve AMR / Industrial-Arm / headless profiles with no
# rebuild — flip the env var and restart. Every collector also idles gracefully
# on hardware that lacks its source, so a wrong toggle degrades to "no data",
# never a crash.
TELEGRAF_D=/etc/telegraf/telegraf.d

# is_enabled VALUE — treat true/1/yes/on/auto as enabled (case-insensitive).
# `auto` counts as enabled: the reader itself probes the hardware and idles if
# absent, so "auto" == "load it and let it self-detect".
is_enabled() {
    case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        true|1|yes|on|auto) return 0 ;;
        *) return 1 ;;
    esac
}

# gate_conf ENV_VALUE BASENAME — enable or disable a shipped <BASENAME>.conf.
gate_conf() {
    local value="$1" base="$2"
    local on="$TELEGRAF_D/$base.conf" off="$TELEGRAF_D/$base.conf.disabled"
    if is_enabled "$value"; then
        [ -f "$off" ] && mv "$off" "$on"
        echo "[INFO]   $base: ENABLED"
    else
        [ -f "$on" ] && mv "$on" "$off"
        echo "[INFO]   $base: disabled"
    fi
}

# gate_example ENV_VALUE BASENAME — activate an opt-in <BASENAME>.conf.example
# by copying it to <BASENAME>.conf when enabled; remove the copy when disabled.
gate_example() {
    local value="$1" base="$2"
    local ex="$TELEGRAF_D/$base.conf.example" on="$TELEGRAF_D/$base.conf"
    if is_enabled "$value"; then
        [ -f "$ex" ] && cp "$ex" "$on"
        echo "[INFO]   $base: ENABLED (from .example)"
    else
        [ -f "$on" ] && [ -f "$ex" ] && rm -f "$on"
        echo "[INFO]   $base: disabled"
    fi
}

echo "[INFO] Configuring hardware-telemetry collectors:"
gate_conf    "${ENABLE_RAPL_POWER:-true}"  "10-power"
gate_conf    "${ENABLE_DRAM_BW:-auto}"     "20-dram-bw"
gate_conf    "${ENABLE_DISK_IO:-true}"     "30-disk"
gate_conf    "${ENABLE_NET_IO:-true}"      "40-net"
gate_conf    "${ENABLE_INTERRUPTS:-true}"  "50-interrupts"
gate_conf    "${ENABLE_PSYS_POWER:-true}"  "90-tcmi-execd"
# Opt-in engineering diagnostics (ship disabled; default off).
gate_example "${ENABLE_TURBOSTAT:-false}"  "60-turbostat"

echo "[INFO] Initialization complete"
echo "       - Metrics API port: ${METRICS_PORT:-9090}"
echo "       - Telegraf Prometheus port: ${TELEGRAF_PORT:-9273}"
echo "       - Custom metrics directory: ${CUSTOM_METRICS_DIR:-/app/custom-metrics}"

# Start supervisor to manage all processes
exec supervisord -c /etc/supervisor/supervisord.conf
