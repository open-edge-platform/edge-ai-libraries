#!/bin/bash
#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
set -x

# get abs path to this script
export DIR=$(cd $(dirname $0) && pwd)

# build image from DLStreamer pipeline server Dockerfile
docker build ${DIR}/../ \
    --network host \
    -t intel/dlstreamer-pipeline-server-test:3.1.0 \
    --build-arg MSGBUS_LIB_VERSION="4.0.0" \
    --build-arg UTILS_LIB_VERSION="4.0.0" \
    --build-arg UID=1999 \
    --build-arg USER="intelmicroserviceuser"\
    --build-arg BASE_IMAGE="intel/dlstreamer:2025.0.1.3-ubuntu22" \
    --build-arg CMAKE_INSTALL_PREFIX="/opt/intel/eii" \
    --build-arg DOWNLOAD_GPL_SOURCES="no"
