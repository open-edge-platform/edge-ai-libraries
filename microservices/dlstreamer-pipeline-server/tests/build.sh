#!/bin/bash
#
# Apache v2 license
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
set -x

# get abs path to this script
export DIR=$(cd $(dirname $0) && pwd)

# Check if BASE_IMAGE is set and not empty
if [ -z "$BASE_IMAGE" ]; then
    echo "ERROR: BASE_IMAGE environment variable is not set or is empty!"
    echo "Please set BASE_IMAGE before running this script."
    exit 1
fi

echo "Using BASE_IMAGE: $BASE_IMAGE"

# Build image for running unit tests
docker build -f ${DIR}/../unittests.Dockerfile ${DIR}/../ \
    --build-arg USER="intelmicroserviceuser" \
    --build-arg BASE_IMAGE="$BASE_IMAGE" \
    -t intel/dlstreamer-pipeline-server-test:latest
