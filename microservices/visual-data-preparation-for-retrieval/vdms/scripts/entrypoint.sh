#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Activates the virtual environment and runs any command given to the docker container

set -e
. $VENV_PATH/bin/activate

exec "$@"