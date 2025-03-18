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

gpu_execution_prequisites

# genicam_prequisites

python3 -m src

wait

