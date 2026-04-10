#!/bin/bash
#
# Apache v2 license
# Copyright (C) 2024-2026 Intel Corporation
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

taskset_cores=()
[ -z "$CORE_PINNING" ] || . ./detect-cores.sh || true
for coreset in ${CORE_PINNING//,/ }; do
  case "$coreset" in
  e-cores|p-cores|lpe-cores)
    declare -n core_list="${coreset/-/_}"
    taskset_cores+=(${core_list[@]})
    ;;
  *)
    taskset_cores+=($coreset)
    ;;
  esac
done
if [ ${#taskset_cores[@]} -gt 0 ]; then
  coreset="${taskset_cores[@]}"
  echo "Core pinned to $coreset" 1>&2
  taskset -c ${coreset// /,} python3 -m src &
else
  python3 -m src &
fi

wait

