#!/bin/bash
#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Create python virtual environment and run the tests
python3 -m venv env
source env/bin/activate
# Install the requirements for executing the pytests
pip3 install -r requirements.txt
pip3 install -r tests/requirements.txt
sudo rm -rf /tmp/htmlcov /tmp/report.txt /tmp/unit-test-results.txt
PYTHONPATH=./src python3 -m pytest --cov=./src tests/ --cov-config=./tests/.coveragerc --maxfail=1 -v | tee /tmp/report.txt
PYTHONPATH=./src python3 -m pytest --cov=./src tests/ --cov-config=./tests/.coveragerc --cov-report=term --tb=no -q --disable-warnings > /tmp/unit-test-results.txt
retval=$?
python3 -m coverage html -d /tmp/htmlcov