# Build From Source

This page covers building the Semantic Search Agent from source code. Use this path when you need to apply code modifications or package customized builds.

## Prerequisites

- Clone the repository and navigate into the `semantic-search-agent/` directory.
- Verify that [system requirements](system-requirements.md) are met.

## Build the Docker Image

The repository provides a `docker/Dockerfile` and a `docker/docker-compose.yml`. The Compose configuration builds the image from local source files.

To build using the Makefile from the project root:

```bash
make docker-build
```

To build the image directly using the `docker` CLI:

```bash
docker build \
  --build-arg HTTP_PROXY=${HTTP_PROXY} \
  --build-arg HTTPS_PROXY=${HTTPS_PROXY} \
  -t intel/semantic-search-agent:2026.1.0 \
  -f docker/Dockerfile \
  .
```

This packages the application code, installs Python dependencies, and configures the container to run as a non-root user (UID 1000).

> **Note**: If you are behind a corporate proxy, pass `--build-arg HTTP_PROXY` and `--build-arg HTTPS_PROXY` as shown above so `pip` can reach PyPI during the build.

## Build a Python Environment (Standalone)

To set up a local development environment and run or test the service directly:

```bash
# Create and activate python venv
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

## Verifying the Build

To test the build locally, run the automated test suite:

```bash
# Run tests with coverage report
make test

# Or run tests directly with pytest
pytest
```

To run a faster test pass without coverage:

```bash
make test-fast
```

If all tests pass, the build is functional and ready for deployment.
