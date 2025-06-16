#!/bin/bash
# Runs tests and generates coverage report
set -e

poetry run coverage run --rcfile ./pyproject.toml -m pytest ./tests
poetry run coverage html
# Serve the coverage report HTML file using python inbuilt http server
poetry run python -m http.server --bind 0.0.0.0 8899 --directory .coverage-report