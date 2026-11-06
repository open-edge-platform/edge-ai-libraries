#!/bin/sh
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Undo what postinst changed outside the package's own files.
#
# A package that alters the state of the host has to be able to put it back.
# Removal clears the runtime directory; purge additionally removes the service
# account and the configuration the operator was left with.
#
# The msr module is deliberately not unloaded: something else on the machine
# may be relying on it by now, and unloading a kernel module out from under an
# unknown user is not a reasonable thing for a package removal to do.

set -e

SERVICE_USER="metrics-manager"
RUNTIME_DIR="/run/metrics-manager"

case "$1" in
remove)
    rm -rf "$RUNTIME_DIR"
    if [ -d /run/systemd/system ]; then
        systemctl daemon-reload >/dev/null || \
            echo "metrics-manager: could not reload systemd after removal" >&2
    fi
    ;;

purge)
    rm -rf "$RUNTIME_DIR"
    rm -rf /etc/metrics-manager

    if getent passwd "$SERVICE_USER" >/dev/null; then
        deluser --system "$SERVICE_USER" >/dev/null || \
            echo "metrics-manager: could not remove the service account" >&2
    fi
    if getent group "$SERVICE_USER" >/dev/null; then
        delgroup --system "$SERVICE_USER" >/dev/null || \
            echo "metrics-manager: could not remove the service group" >&2
    fi

    if [ -d /run/systemd/system ]; then
        systemctl daemon-reload >/dev/null || \
            echo "metrics-manager: could not reload systemd after purge" >&2
    fi
    ;;

upgrade | failed-upgrade | abort-install | abort-upgrade | disappear) ;;

*)
    echo "postrm called with unknown argument '$1'" >&2
    exit 1
    ;;
esac

exit 0
