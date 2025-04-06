#!/bin/bash

# Run each fuzz test file with coverage in parallel
for file in tests/fuzz_targets/*.py; do
    coverage run --parallel-mode --rcfile=.coveragerc_fuzz_targets "${file%.*}".py -atheris_runs=100 &
done
wait

# Combine and generate reports
coverage combine
coverage report -m --rcfile=.coveragerc_fuzz_targets --skip-empty
coverage html --rcfile=.coveragerc_fuzz_targets --skip-empty
