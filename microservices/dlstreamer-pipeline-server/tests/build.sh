#!/bin/bash
#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
set -x

# get abs path to this script
export DIR=$(cd $(dirname $0) && pwd)

# Build image for running unit tests
docker build -f ${DIR}/../unittests.Dockerfile ${DIR}/../ --build-arg USER="intelmicroserviceuser" --build-arg BASE_IMAGE="$(grep ^DLSTREAMER_PIPELINE_SERVER_IMAGE= ${DIR}/../docker/.env | cut -d= -f2-)" -t intel/dlstreamer-pipeline-server-test:3.1.0
