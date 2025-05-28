#!/bin/bash
#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
pytest -vv --cov=. tests/ --cov-config=tests/.coveragerc 
exit_code=$?
coverage html -i -d /tmp/htmlcov
# Exit with pytest's exit code
exit $exit_code
