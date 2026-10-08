#!/bin/bash
#
# Apache v2 license
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

taskset_cmds=()
case "$CORE_PINNING" in
e-cores)
    detected_core_list_name=e_cores
    # sourced at runtime relative to the container workdir; shellcheck cannot resolve this path statically
    # shellcheck disable=SC1091
    . ./detect-cores.sh
    declare -n core_list="${detected_core_list_name}"
    core_csv=$(IFS=,; echo "${core_list[*]}")
    [ ${#core_list[@]} -eq 0 ] || taskset_cmds=(taskset -c "$core_csv")
    ;;
p-cores)
    detected_core_list_name=p_cores
    # sourced at runtime relative to the container workdir; shellcheck cannot resolve this path statically
    # shellcheck disable=SC1091
    . ./detect-cores.sh
    declare -n core_list="${detected_core_list_name}"
    core_csv=$(IFS=,; echo "${core_list[*]}")
    [ ${#core_list[@]} -eq 0 ] || taskset_cmds=(taskset -c "$core_csv")
    ;;
lp-cores|lpe-cores)
    detected_core_list_name=lpe_cores
    # sourced at runtime relative to the container workdir; shellcheck cannot resolve this path statically
    # shellcheck disable=SC1091
    . ./detect-cores.sh
    declare -n core_list="${detected_core_list_name}"
    core_csv=$(IFS=,; echo "${core_list[*]}")
    [ ${#core_list[@]} -eq 0 ] || taskset_cmds=(taskset -c "$core_csv")
    ;;
*)
    [ ${#CORE_PINNING[@]} -eq 0 ] || taskset_cmds=(taskset -c "${CORE_PINNING// /,}")
    ;;
esac
echo "Using core pinning: ${taskset_cmds[*]}"

core_pid=
api_pid=
cleanup() {
    trap - EXIT INT TERM
    [[ -n "$api_pid" ]] && kill -TERM "$api_pid" 2>/dev/null || true
    [[ -n "$core_pid" ]] && kill -TERM "$core_pid" 2>/dev/null || true
    [[ -n "$api_pid" ]] && wait "$api_pid" 2>/dev/null || true
    [[ -n "$core_pid" ]] && wait "$core_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

/usr/bin/entrypoint.sh serve \
    --node-id=windturbine \
    --object-store=file \
    --data-dir=/var/lib/influxdb3/data \
    --plugin-dir=/tmp \
    --admin-token-file="${INFLUXDB3_ADMIN_TOKEN_FILE:-/run/secrets/admin-token}" &
core_pid=$!

core_ready=false
for attempt in $(seq 1 60); do
    if ! kill -0 "$core_pid" 2>/dev/null; then
        echo "InfluxDB 3 Core exited before becoming ready."
        exit 1
    fi
    status=$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:8181/health || true)
    if [[ "$status" == "200" || "$status" == "401" ]]; then
        core_ready=true
        break
    fi
    sleep 1
done

if [[ "$core_ready" != "true" ]]; then
    echo "Timed out waiting for InfluxDB 3 Core to become ready."
    exit 1
fi

"${taskset_cmds[@]}" python3 /app/main.py &
api_pid=$!
wait -n "$core_pid" "$api_pid"
exit $?


