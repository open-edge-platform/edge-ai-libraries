#!/bin/bash
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
set -e

WORK_DIR="$( cd "$( dirname "${BASH_SOURCE[0]:-${(%):-%x}}" )" >/dev/null 2>&1 && pwd )"
ARTIFACT_DIR=/tmp/results/
rm -f ${ARTIFACT_DIR}/*
mkdir -p ${ARTIFACT_DIR}

# some of test cases have same gt json, so we have to start only one tc per gt file. Filter out other tc by 'gt' tag
PYTHONPATH=$WORK_DIR:$PYTHONPATH python3 -u -m regression_test -c configs_ov2/watermark.json --force --tags gt

# copy result histograms to {dataset.groundtruth.base} dir, {dataset.groundtruth.base} defined in configs/watermark.json
cp ${ARTIFACT_DIR}/*.json ${WORK_DIR}/groundtruth_ov2/watermark
