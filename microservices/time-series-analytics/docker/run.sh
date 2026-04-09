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
    . ./detect-cores.sh
    declare -n core_list="${detected_core_list_name}"
    [ ${#core_list[@]} -eq 0 ] || taskset_cmds=(taskset -c $(IFS=,; echo "${core_list[*]}"))
    ;;
p-cores)
    detected_core_list_name=p_cores
    . ./detect-cores.sh
    declare -n core_list="${detected_core_list_name}"
    [ ${#core_list[@]} -eq 0 ] || taskset_cmds=(taskset -c $(IFS=,; echo "${core_list[*]}"))
    ;;
lp-cores|lpe-cores)
    detected_core_list_name=lpe_cores
    . ./detect-cores.sh
    declare -n core_list="${detected_core_list_name}"
    [ ${#core_list[@]} -eq 0 ] || taskset_cmds=(taskset -c $(IFS=,; echo "${core_list[*]}"))
    ;;
*)
    [ ${#CORE_PINNING[@]} -eq 0 ] || taskset_cmds=(taskset -c ${CORE_PINNING// /,})
    ;;
esac
echo "Using core pinning: ${taskset_cmds[@]}"
exec "${taskset_cmds[@]}" python3 main.py


