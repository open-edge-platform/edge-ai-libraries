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
# We gate each hardware-telemetry drop-in on an ENABLE_* env var. Rather than
# mutate the shipped drop-in directory (which is bind-mounted READ-ONLY from the
# host via the compose TELEGRAF_CONFIG_DIR mount), we assemble the *active* set
# into a separate writable directory and launch telegraf against that:
#   source (read-only) : /etc/telegraf/telegraf.d       <name>.conf[.example]
#   active (writable)  : /etc/telegraf/active.d          only the enabled <name>.conf
# "enabled" == copy the source drop-in into the active dir; "disabled" == don't.
# This lets one image serve AMR / Industrial-Arm / headless profiles with no
# rebuild — flip the env var and restart — without ever writing to the read-only
# mount (a `cp`/`mv` there would crash the container). Every collector also
# idles gracefully on hardware that lacks its source, so a wrong toggle degrades
# to "no data", never a crash.
TELEGRAF_D_SRC=/etc/telegraf/telegraf.d
TELEGRAF_D=/etc/telegraf/active.d

# Rebuild the active dir from scratch on every start so it always reflects the
# current env, regardless of any state left by a previous run.
rm -rf "$TELEGRAF_D"
mkdir -p "$TELEGRAF_D"

# is_enabled VALUE — treat true/1/yes/on/auto as enabled (case-insensitive).
# `auto` counts as enabled: the reader itself probes the hardware and idles if
# absent, so "auto" == "load it and let it self-detect".
is_enabled() {
    case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        true|1|yes|on|auto) return 0 ;;
        *) return 1 ;;
    esac
}

# enable_conf ENV_VALUE BASENAME — copy a shipped <BASENAME>.conf into the active
# dir when enabled.
enable_conf() {
    local value="$1" base="$2"
    if is_enabled "$value"; then
        if [ -f "$TELEGRAF_D_SRC/$base.conf" ]; then
            cp "$TELEGRAF_D_SRC/$base.conf" "$TELEGRAF_D/$base.conf"
            echo "[INFO]   $base: ENABLED"
        else
            echo "[WARN]  $base: enabled but $base.conf not found — skipping"
        fi
    else
        echo "[INFO]   $base: disabled"
    fi
}

# enable_example ENV_VALUE BASENAME — activate an opt-in drop-in by copying
# <BASENAME>.conf.example into the active dir as <BASENAME>.conf when enabled.
enable_example() {
    local value="$1" base="$2"
    if is_enabled "$value"; then
        if [ -f "$TELEGRAF_D_SRC/$base.conf.example" ]; then
            cp "$TELEGRAF_D_SRC/$base.conf.example" "$TELEGRAF_D/$base.conf"
            echo "[INFO]   $base: ENABLED (from .example)"
        else
            echo "[WARN]  $base: enabled but $base.conf.example not found — skipping"
        fi
    else
        echo "[INFO]   $base: disabled"
    fi
}

echo "[INFO] Configuring hardware-telemetry collectors:"
enable_conf    "${ENABLE_RAPL_POWER:-true}"  "10-power"
enable_conf    "${ENABLE_DRAM_BW:-auto}"     "20-dram-bw"
enable_conf    "${ENABLE_DISK_IO:-true}"     "30-disk"
enable_conf    "${ENABLE_NET_IO:-true}"      "40-net"
enable_conf    "${ENABLE_INTERRUPTS:-true}"  "50-interrupts"
enable_conf    "${ENABLE_PSYS_POWER:-true}"  "90-tcmi-execd"
# Opt-in engineering diagnostics (ship disabled; default off).
enable_example "${ENABLE_TURBOSTAT:-false}"  "60-turbostat"

echo "[INFO] Initialization complete"
echo "       - Metrics API port: ${METRICS_PORT:-9090}"
echo "       - Telegraf Prometheus port: ${TELEGRAF_PORT:-9273}"
echo "       - Custom metrics directory: ${CUSTOM_METRICS_DIR:-/app/custom-metrics}"

# Start supervisor to manage all processes
exec supervisord -c /etc/supervisor/supervisord.conf
