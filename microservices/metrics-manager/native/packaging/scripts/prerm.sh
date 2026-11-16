#!/bin/sh
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Stop the services before their files are removed.
#
# On upgrade this deliberately does nothing: postinst restarts the services
# once the new binaries are in place, which keeps the gap to a moment rather
# than the length of the unpack.

set -e

SERVICES="metrics-manager-telegraf.service metrics-manager-qmassa.service metrics-manager-npu.service metrics-manager-powerstat.service metrics-manager-proc.service metrics-manager-membw.service metrics-manager-rapl.service"

case "$1" in
remove | deconfigure)
    if [ -d /run/systemd/system ]; then
        # shellcheck disable=SC2086
        systemctl stop $SERVICES >/dev/null || \
            echo "metrics-manager: could not stop all telemetry services" >&2
        # shellcheck disable=SC2086
        systemctl disable $SERVICES >/dev/null || \
            echo "metrics-manager: could not disable all telemetry services" >&2
    fi
    ;;

upgrade | failed-upgrade) ;;

*)
    echo "prerm called with unknown argument '$1'" >&2
    exit 1
    ;;
esac

exit 0
