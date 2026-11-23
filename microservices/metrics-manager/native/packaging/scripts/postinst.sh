#!/bin/sh
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Post-installation configuration for the Metrics Manager package.
#
# The package draws a privilege boundary between an unprivileged Telegraf and
# the collectors that need more, so this script creates the service account
# that boundary is built on, puts the runtime directory in place with the right
# ownership, and makes sure the kernel interface the GPU telemetry depends on
# is actually available.

set -e

SERVICE_USER="metrics-manager"
SERVICES="metrics-manager-telegraf.service metrics-manager-qmassa.service metrics-manager-npu.service metrics-manager-powerstat.service metrics-manager-proc.service metrics-manager-membw.service"

case "$1" in
configure)
    # A system account with no home, no shell and no password. Telegraf and the
    # NPU collector both run as this user; nothing is ever meant to log in as
    # it.
    if ! getent group "$SERVICE_USER" >/dev/null; then
        addgroup --system "$SERVICE_USER"
    fi
    if ! getent passwd "$SERVICE_USER" >/dev/null; then
        adduser --system --ingroup "$SERVICE_USER" \
            --home /nonexistent --no-create-home \
            --shell /usr/sbin/nologin \
            --gecos "Metrics Manager telemetry" \
            "$SERVICE_USER"
    fi

    # Custom metrics scripts stay root-owned: a compromise of the unprivileged
    # Telegraf must not be able to plant something that Telegraf then runs.
    chown root:root /etc/metrics-manager/custom-metrics.d
    chmod 0755 /etc/metrics-manager/custom-metrics.d

    # Create the runtime directory and the FIFO now, rather than waiting for
    # the next boot.
    systemd-tmpfiles --create /usr/lib/tmpfiles.d/metrics-manager.conf

    # GPU power and package temperature are read through model-specific
    # registers. Without this module they are silently missing, so load it
    # immediately as well as at boot. A kernel that lacks it is not an
    # installation failure: the rest of the telemetry still works.
    if [ ! -e /dev/cpu/0/msr ]; then
        modprobe msr >/dev/null 2>&1 || \
            echo "metrics-manager: could not load the msr module; GPU power and temperature will be unavailable" >&2
    fi

    if [ -d /run/systemd/system ]; then
        systemctl daemon-reload >/dev/null || \
            echo "metrics-manager: could not reload systemd; check service status" >&2
        # shellcheck disable=SC2086
        systemctl enable $SERVICES >/dev/null || \
            echo "metrics-manager: could not enable all telemetry services" >&2
        # shellcheck disable=SC2086
        systemctl restart $SERVICES >/dev/null || \
            echo "metrics-manager: some telemetry services failed to start; check journalctl" >&2
        # RAPL is opt-in. Upgrade its binary for existing users without
        # enabling or starting it on installations that never opted in.
        systemctl try-restart metrics-manager-rapl.service >/dev/null || \
            echo "metrics-manager: could not restart the active RAPL service" >&2
    else
        echo "metrics-manager: systemd is not running; services were not started" >&2
    fi

    echo "metrics-manager: package configured; verify services before using http://127.0.0.1:9273/metrics or mm-tui"
    ;;

abort-upgrade | abort-remove | abort-deconfigure) ;;

*)
    echo "postinst called with unknown argument '$1'" >&2
    exit 1
    ;;
esac

exit 0
