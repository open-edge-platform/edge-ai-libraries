# How to Build from Source

Build the **Vector Retriever microservice** from source to customize, debug, or extend its functionality. In this guide, you will:

- Set up your development environment.
- Build container images from source.
- Run and validate the service locally.

This guide is ideal for developers who want to work directly with the source code.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify your system meets the [minimum requirements](./system-requirements.md).
- This guide assumes basic familiarity with Git commands, Python virtual environments, and terminal usage. If you are new to these concepts, see:
  - [Git Documentation](https://git-scm.com/doc)
  - [Python Virtual Environments](https://docs.python.org/3/tutorial/venv.html)

## Steps to Build

This section provides a detailed walkthrough for building the Vector Retriever microservice.

**_(Optional)_** Docker Compose builds the Vector Retriever image with a default image and tag name. If you want to use a different image and tag, export these variables:

```bash
export REGISTRY_URL="your-container-registry-url"
export PROJECT_NAME="your-project-name"
export TAG="your-tag"
```

Note: `PROJECT_NAME` is suffixed to `REGISTRY_URL` to create a namespaced URL. Final image names are created by appending the service name and tag.

Example: If variables are set using the commands above, final backend-flavor image names are:

- `<your-container-registry-url>/<your-project-name>/vector-retriever-vdms:<your-tag>`
- `<your-container-registry-url>/<your-project-name>/vector-retriever-milvus:<your-tag>`
- `<your-container-registry-url>/<your-project-name>/vector-retriever-pgvector:<your-tag>`
- `<your-container-registry-url>/<your-project-name>/vector-retriever-faiss:<your-tag>`

If variables are not set, `TAG` defaults to `latest`.

- Clone the repository:

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
cd edge-ai-libraries/microservices/vector-retriever/vector-retriever
```

- If your branch uses a different service path, adjust the `cd` command accordingly.

- Set up environment values:

Follow all instructions in the [Get Started](./get-started.md#set-environment-values) guide to configure required environment variables.

Example required values:

```bash
export RETRIEVER_BACKEND=vdms
export MULTIMODAL_EMBEDDING_ENDPOINT=http://<embedding-service-host>:<port>/embeddings
export EMBEDDING_MODEL_NAME=<model-name>
```

- Set the environment in shell:

```bash
source ./setup.sh
```

- Build the Docker image:

```bash
source ./setup.sh --build
```

- Verify rendered compose configuration:

```bash
source ./setup.sh --conf
```

- Run the service:

```bash
source ./setup.sh
```

- To run with a local VDMS profile for quick local testing:

```bash
source ./setup.sh --up-with-vdms
```

- You can also start backend-specific overlays directly:

```bash
source ./setup.sh --up-with-milvus
source ./setup.sh --up-with-pgvector
source ./setup.sh --up-with-faiss
```

- Stop services:

```bash
source ./setup.sh --down
```

- Run unit tests with the workspace virtual environment:

```bash
PYTHONPATH=. poetry run pytest -q tests --ignore=tests/functional
```

- Run backend functional checks explicitly when Docker is available:

```bash
RUN_FUNCTIONAL_BACKEND_TESTS=1 PYTHONPATH=. poetry run pytest -q tests/functional
```

## Validation

**Verify Build Success**:

- Check container logs for successful startup.
- Verify health and readiness endpoints. Docker Compose publishes the service on port `6008`; direct `uvicorn` runs use port `8000` unless you override it:

```bash
curl --location --request GET 'http://localhost:6008/health'
curl --location --request GET 'http://localhost:6008/ready'
```

## Supporting Resources

- [Overview](Overview.md)
- [Overview and Architecture](overview-architecture.md)
- [Get Started](get-started.md)
- [API Reference](api-reference.md)
- [OpenAPI Specification](api-docs/openapi.yaml)
- [System Requirements](system-requirements.md)
- [Add New Retriever Backend](add-new-retriever-backend.md)
- [Release Notes](release-notes.md)
