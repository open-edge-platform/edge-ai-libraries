# How to Build from Source

Build the VDMS-DataPrep microservice from source to customize, debug, or extend its functionality. In this guide, you will:
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
Following options are provided to build the microservice.

### Setup in a container using Docker Script

1. Clone the repository and change to project directory:
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b release-1.2.0
cd edge-ai-libraries/microservices/visual-data-preparation-for-retrieval/vdms
```

2. Set the required environment variables:

```bash
# OPTIONAL - If you want to push the built images to a remote container registry, you need to name the images accordingly. For this, image name should include the registry URL as well. To do this, set the following environment variable from shell. Please note that this URL will be prefixed to the application name and tag to form the final image name.

export REGISTRY_URL=<your-registry-url>
export TAG=<your-yag> # Default: latest
```
Refer to the [environmental variable](./get-started.md#environment-variables) setup section and configure the required variables.

3. Verify the configuration.

```bash
source ./setup.sh --conf
```
This will output docker compose configs with all the environment variables resolved. You can verify whether they appear as expected.

4. Spin up the services. Please go through different ways to spin up the services.

```bash
# Run the development environment in daemon mode
source ./setup.sh --dev

# Run the development environment in non-daemon mode
source ./setup.sh --dev --nd

# Run the production environment in daemon mode
source ./setup.sh

# Run the production environment in non-daemon mode
source ./setup.sh --nd
```

5. Tear down all the services.

```bash
source ./setup.sh --down
```

## Validation

1. **Verify Build Success**:
   - Check the logs. Look for confirmation messages indicating the microservice started successfully.

## Troubleshooting


## Supporting Resources
* [Overview](Overview.md)
* [System Requirements](system-requirements.md)
* [API Reference](api-reference.md)