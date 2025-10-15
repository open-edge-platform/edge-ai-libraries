#!/bin/bash

#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

# Pre-requisites needed for Gencam based Cameras video Ingestion
genicam_prequisites() {
    # Adding path of Generic Plugin
    export GST_PLUGIN_PATH=$GST_PLUGIN_PATH:"/usr/local/lib/gstreamer-1.0"

    source ./gentl_producer_env.sh
}

gpu_execution_prequisites() {
    # Adding path of Generic Plugin
    export GST_PLUGIN_PATH=$GST_PLUGIN_PATH:"/usr/local/lib/gstreamer-1.0"
    
    # Adding path of vaapi elements
    export LIBVA_DRIVER_NAME=iHD
    export LIBVA_DRIVERS_PATH=/usr/lib/x86_64-linux-gnu/dri
    export GST_VAAPI_ALL_DRIVERS=1

    # Open CL Cache to optimize load & execution time for GPU models on subsequent runs
    mkdir -p /var/tmp/.cl-cache
    export cl_cache_dir=/var/tmp/.cl-cache
}

ros2_prerequisites() {
    if [ -f /opt/ros/humble/setup.bash ]; then
        echo "Sourcing ROS2 Humble environment..."
        source /opt/ros/humble/setup.bash
    elif [ -f /opt/ros/jazzy/setup.bash ]; then
        echo "Sourcing ROS2 Jazzy environment..."
        source /opt/ros/jazzy/setup.bash
    else
        return
    fi

    export ROS_LOG_DIR=/tmp/ros_logs
    mkdir -p "$ROS_LOG_DIR"
    echo "ROS_LOG_DIR set to $ROS_LOG_DIR"
}

gpu_execution_prequisites

# genicam_prequisites

ros2_prerequisites

taskset_cmds=()
case "$CORE_PINNING" in
e-cores|p-cores|lp-cores)
    . ./detect-cores.sh
    declare -n core_list="${CORE_PINNING/-/_}"
    [ ${#core_list[@]} -eq 0 ] || taskset_cmds=(taskset -c $(IFS=,; echo "${core_list[*]}"))
    ;;
*)
    [ ${#CORE_PINNING[@]} -eq 0 ] || taskset_cmds=(taskset -c ${CORE_PINNING// /,})
    ;;
esac
${taskset_cmds[@]} python3 -m src

wait

