#!/bin/bash
#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
pytest -vv --cov=. tests/ --cov-config=tests/.coveragerc
coverage xml -i -o /tmp/coverage.xml
