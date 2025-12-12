# Running Unit Tests

This guide provides comprehensive instructions for running the unit test suite for the Model Download Microservice.

## Prerequisites

### Environment Setup

You can use either traditional pip/venv or the modern uv tool for dependency management:

#### Using uv

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh
# or
pip install uv

# Create and activate virtual environment
uv venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows

# Install core testing dependencies
uv pip install -e ".[dev]"

```
## Test Structure

The test suite is organized as follows:

```
tests/
├── conftest.py              # Test configuration and fixtures
├── unit/
│   ├── test_api_main.py            # API endpoint tests
│   ├── test_huggingface_plugin.py  # HuggingFace plugin tests
│   ├── test_ollama_plugin.py       # Ollama plugin tests
│   ├── test_openvino_plugin.py     # OpenVINO plugin tests
│   └── test_ultralytics_plugin.py  # Ultralytics plugin tests
└── test_data/               # Test data and temporary files
```

## Basic Test Commands

### Run All Tests

```bash
# From the project root directory
pytest tests/ -v
```

### Run Tests with Coverage Report

```bash
# Generate coverage report in terminal and HTML
pytest tests/ --cov=src --cov-report=html --cov-report=term

# Open the HTML coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

### Run Specific Test Categories

```bash
# API tests only
pytest tests/unit/test_api_main.py -v

# All plugin tests
pytest tests/unit/test_*_plugin.py -v

# Specific plugin test
pytest tests/unit/test_huggingface_plugin.py -v
pytest tests/unit/test_ollama_plugin.py -v
pytest tests/unit/test_openvino_plugin.py -v
pytest tests/unit/test_ultralytics_plugin.py -v
```