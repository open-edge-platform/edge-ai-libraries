#!/bin/bash
#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
set -x

# get abs path to this script
export DIR=$(cd $(dirname $0) && pwd)

# build image from EVAM Dockerfile
docker build ${DIR}/../ \
    --network host \
    -t intel/edge-video-analytics-microservice-test:2.3.0 \
    --build-arg MSGBUS_LIB_VERSION="4.0.0" \
    --build-arg UTILS_LIB_VERSION="4.0.0" \
    --build-arg EVAM_UID=1999 \
    --build-arg USER=intelmicroserviceuser \
    --build-arg BASE_IMAGE="ubuntu:22.04" \
    --build-arg CMAKE_INSTALL_PREFIX="/opt/intel/eii" \
    --build-arg DOWNLOAD_GPL_SOURCES="no"
