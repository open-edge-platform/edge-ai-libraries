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
docker build -f ${DIR}/../unittests.Dockerfile ${DIR}/../ -t intel/dlstreamer-pipeline-server-test:3.1.0
