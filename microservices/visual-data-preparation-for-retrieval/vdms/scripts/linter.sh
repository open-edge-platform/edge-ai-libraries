#!/bin/bash
# Lints source code 

if [ "$1" = "--apply" ] || [ "$1" = "-a" ]; then
    black_apply=""
    isort_apply=""
else
    black_apply="--check"
    isort_apply="--check-only"
fi
poetry run black --config ./pyproject.toml $black_apply tests src
poetry run isort --settings-path ./pyproject.toml $isort_apply .