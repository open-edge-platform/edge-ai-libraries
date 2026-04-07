#!/bin/bash
#
# Apache v2 license
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

taskset_cmds=()
case "$CORE_PINNING" in
e-cores|p-cores|lpe-cores)
    . ./detect-cores.sh
    declare -n core_list="${CORE_PINNING/-/_}"
    [ ${#core_list[@]} -eq 0 ] || taskset_cmds=(taskset -c $(IFS=,; echo "${core_list[*]}"))
    ;;
*)
    [ ${#CORE_PINNING[@]} -eq 0 ] || taskset_cmds=(taskset -c ${CORE_PINNING// /,})
    ;;
esac
echo "Using core pinning: ${taskset_cmds[@]}"
"${taskset_cmds[@]}" python3 main.py


