# Build From Source

This page covers building the Alert Service from source code. Use this path when you need to apply code modifications or package customized builds.

## Prerequisites

- Clone the repository and navigate into the `alert-service/` directory.
- Verify that [system requirements](system-requirements.md) are met.

## Build the Docker Image

The repository provides a `docker/Dockerfile` and a `docker/docker-compose.yml`. The compose configuration builds the alert service image using local source files by default when running `make build`.

To build the image using the Makefile:

```bash
make build
```

To build the image directly using the `docker` CLI from the root of `alert-service/`:

```bash
docker build -t alert-service:local -f docker/Dockerfile .
```

This will package the code, establish a lightweight Python runtime environment, and copy source files under `/app`.

## Build a Python Environment (Standalone)

To set up a local development environment and run or test the service directly:

```bash
# Initialize local environment
make init-env

# Create and activate python venv
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

## Verifying the Build

To test the build locally, run the automated test suite:

```bash
# Run tests inside docker environment
make test

# Or run tests locally with pytest
pytest
```

If tests pass, the build is functional and ready.
