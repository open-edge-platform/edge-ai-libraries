# How to Build from Source

Build the **Multimodal Embedding Serving microservice** from source to customize, debug, or extend its functionality. In this guide, you will:
- Set up your development environment.
- Compile the source code and resolve dependencies.
- Generate a runnable build for local testing or deployment.

This guide is ideal for developers who want to work directly with the source code.

## Prerequisites

Before you begin, ensure the following:
- **System Requirements**: Verify your system meets the [minimum requirements](./system-requirements.md).
- This guide assumes basic familiarity with Git commands, Python virtual environments, and terminal usage. If you are new to these concepts, see:
  - [Git Documentation](https://git-scm.com/doc)
  - [Python Virtual Environments](https://docs.python.org/3/tutorial/venv.html)


## Steps to Build
This section provides a detailed note on how to build the Multimodal Embedding Serving microservice.

**_(Optional)_** Docker Compose builds the _Multimodal Embedding Serving_ with a default image and tag name. If you want to use a different image and tag, export these variables:

```bash
export REGISTRY_URL="your-container-registry-url"
export PROJECT_NAME="your-project-name"
export TAG="your-tag"
```

> **_NOTE:_** `PROJECT_NAME` will be suffixed to `REGISTRY_URL` to create a namespaced url. Final image name will be created/pulled by further suffixing the application name and tag with the namespaced url. 

> **_EXAMPLE:_** If variables are set using above command, the final image names for _Multimodal Embedding Serving_ would be `<your-container-registry-url>/<your-project-name>/multimodal-embedding-serving:<your-tag>`. 

If variables are not set, in that case, the `TAG` will have default value as _latest_. Hence, final image will be `multimodal-embedding-serving:latest`.

1. **Clone the Repository**:
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b release-1.2.0
cd edge-ai-libraries/microservices/multimodal-embedding-service
```

2. **Set up environment values**:
    
Follow all the instructions provided in the [get started](./get-started.md#set-environment-values) document to set up the environment variables.
> **Note**: To build or run with GPU support, set EMBEDDING_DEVICE=GPU before sourcing setup.sh.

3. **Build the Docker image**:

To build the Docker image, run the following command:
```bash
docker compose -f docker/compose.yaml build
```

4. **Run the service**:

 ```bash
 docker compose -f docker/compose.yaml  up
 ```

This will run the service in either CPU or GPU mode depending on your environment variable settings.

## Validation

**Verify Build Success**:
- Check the logs. Look for confirmation messages indicating the microservice started successfully.


## Supporting Resources
* [Overview](Overview.md)
* [System Requirements](system-requirements.md)
* [API Reference](api-reference.md)