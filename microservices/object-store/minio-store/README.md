# Getting Started with DataStore Service

An object storage component based on [Minio](https://github.com/minio/minio). This helps in storing objects. One use case for the DataStore is for storing files and documents which are ingested for creating embeddings. [DataPrep](../dataprep/pgvector) service is a component which implements this use case.  These embeddings help LLMs answer queries based on context present in the stored files.

---

## Table of Contents

- [Introduction](#getting-started-with-datastore-service)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
    - [Prerequisites](#prerequisites)
    - [Environment Variables](#environment-variables)
    - [How to set environment variables](#how-to-set-environment-variables)
    - [Setup](#setup)
- [Usage](#usage)
    - [Access Services](#access-services)
    - [Validate Services](#validate-services)
    - [Minio Console UI](#minio-console-ui)

---

## Project Structure

- `docker` directory:
  - Contains the Dockerfile to build the Datastore application image.
  - Includes Docker Compose files for both production and development setups. These files help set up the application container and the Minio-server container, which the application depends on.

- `minio_store` directory:
  - Contains the application code.

- `tests` directory:
  - Contains tests for the application endpoints.

- `poetry.lock` and `poetry.toml` files:
  - Manage dependencies for the Python application. The `poetry.lock` file ensures the same versions of Python packages are installed as in the working development environment.

- `run.sh`:
  - A runner bash script that quickly sets up and runs the application along with all dependencies.

- `.dockerignore`:
  - Specifies files and directories to exclude from the Docker image, reducing unnecessary files in the image.

---

## Configuration

We will be running our application in docker containers. Configuration step involves setting various environment variables, which are prerequisites for spinning up our containers and proper functioning of application inside them.

Two containers will be deployed and each running specific service:

- **Data Store Application**: A service designed to store and manage data.

- **Minio Server**: Hosts MinIO, a high-performance object storage system.

These two services are part of `docker/compose.yaml` file. These two services would be requiring their own set of environment variables to be setup.

### Prerequisites

Please make sure following tools are already installed on your machine:

- Docker
- Docker Compose
- Python 3.10 or later
- If you are behind a proxy, please make sure `http_proxy`, `https_proxy`, `no_proxy` are properly set on the shell you use.

### Environment Variables

Following environment variables are required for setting up the application. **The runner script `run.sh` takes care most of these. Here, we present them mostly for informational purpose, for the cases where you want to override these for any reason. You can safely skip this section and move to next.**

- **PROJECT_NAME:** Helps provide a common docker compose project name and create a common container prefix for all services involved.
- **DATASTORE_CODE_DIR:** Contains the location of DataStore source code. This location is mounted to docker container in dev environment to facilitate auto-reload of server while code changes during development.
- **MINIO_HOST:** Host name for Minio Server. This is used to communicate with Minio Server by Data Store service inside container.
- **MINIO_API_PORT:** Port on which Minio Server's API service runs inside container.
- **MINIO_API_HOST_PORT**: Port on which we want to access Minio server's API service outside container i.e. on host.
- **MINIO_CONSOLE_PORT:** Port on which we want MINIO UI Console to run inside container.
- **MINIO_CONSOLE_HOST_PORT:** Port on which we want to access MINIO UI Console on host machine.
- **MINIO_MOUNT_PATH:** Mount point for Minio server objects storage on host machine. This helps persist objects stored on Minio server.
- **MINIO_ROOT_USER:** Username for MINIO Server. This is required while accessing Minio UI Console.
- **MINIO_ROOT_PASSWORD:** Password for MINIO Server. This is required while accessing Minio UI Console.
- **DATASTORE_HOST_PORT:** Port on host where we want to access DataStore Service outside container.

### How to set environment variables

The runner script in root of project `run.sh` sets default values for most of the required environment variables once we run it. For sensitive values like `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWD`, we can set following env vars on our bash shell before running the script.

```bash
export MINIO_USER="minio_user"
export MINIO_PASSWD="minio_passwd"
```

For all other variables, you can edit the `run.sh` file in project root and update any export statements inside it to override default values.

### Setup

1. Clone the Repo:

   ```bash
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git
   ```

2. Change to the project directory:

   ```bash
   cd edge-ai-libraries/microservices/object-store/minio-store
   ```

3. Set the username and password for MINIO Server.

   ```bash
   export MINIO_USER="minio_user"
   export MINIO_PADSSWD="minio_passwd"
   ```

4. **Optional step:** Edit the `run.sh` script to set other environment variables if required.

5. Verify the configuration.

   ```bash
   source ./run.sh --conf
   ```

This will output docker compose configs with all the environment variables resolved. You can verify whether they appear as expected.

6. Spin up the services. Please go through different ways to spin up the services.

   ```bash
   # Run the development environment in daemon mode
   source ./run.sh --dev

   # Run the production environment in daemon mode
   source ./run.sh

   # Run the development environment in non-daemon mode
   source ./run.sh --dev --nd

   # Run the production environment in non-daemon mode
   source ./run.sh --nd
   ```

7. Tear down all the services.

   ```bash
   source ./run.sh --down
   ```

#### Run `run.sh` to only set variables:

It might be possible that you run all the services in *non-daemon* mode to get all the logs. In that case you will try to access/use the services from another shell window, as previous window will be full with docker container logs. However this shell will not have the required variables set. In that case, you can run `run.sh` to just set the variables and avoid starting/building any containers.

```bash
# Set all the environment variables without building/starting any container
source ./run.sh --nosetup
```

### Build the docker image manually

If you don't want to use docker compose and build the image on your own, please run the following:

```bash
# To build development image
BUILD_TAG="<image-name:tag-name>" source ./run.sh --build-dev

# To build production image
BUILD_TAG="<image-name:tag-name>" source ./run.sh --build
```

---

## Usage

### Access Services

As all the services spin up, we will have two applications available on `MINIO_API_HOST_PORT` and `MINIO_CONSOLE_HOST_PORT`. These variables are set in `run.sh` file.

>__NOTE:__ Please make sure you try to access/verify the services from the same shell where `run.sh` was run. If you are accessing services from a shell where `run.sh` was not run, then you need to re-set the required env vars because none of the variables would be available in another shell. You can do so by running the same script to only set the variables with a *--nosetup* flag: `source ./run.sh --nosetup`

- Data Store API service runs on `MINIO_API_HOST_PORT`
- Minio Server Console UI runs on `MINIO_CONSOLE_HOST_PORT`

Get the IP address of host machine. `run.sh` script sets `host_ip` variable with the IP address of host machine. You can verify and use this variable, or you can provide a host IP manually.

Once you have host IP, access the Data Store API Docs in any web browser on `http://${host_ip}:${DATASTORE_HOST_PORT}/docs`. Similarly, you can access the Minio Server Console UI on `http://${host_ip}:${MINIO_CONSOLE_HOST_PORT}`. Use the Value of `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` from run.sh as login credentials for the Console UI (see below command).

```bash
# Get username and password for Minio User Console
echo $MINIO_ROOT_USER && echo $MINIO_ROOT_PASSWORD
```

You can go through the DataStore API docs to understand how to **put**, **get** and **delete** files from Minio server.

### Validate Services

We will try to upload a PDF file, verify that it is uploaded and then delete it. Please make sure we are in `components/datastore/minio-store` directory of the clone repo.

```bash

# Set the required vars if accessing from another shell
source ./run.sh --nosetup

# Download a sample pdf file
curl -LO https://github.com/py-pdf/sample-files/blob/main/001-trivial/minimal-document.pdf

# Upload the file to default bucket
curl -X PUT "http://${host_ip}:${DATASTORE_HOST_PORT}/data" \
    -H "Content-Type: multipart/form-data" \
    -F "file=@./minimal-document.pdf"

# Verify whether file was uploaded
curl -X GET "http://${host_ip}:${DATASTORE_HOST_PORT}/data"

# Get the bucket_name and file_name from previous GET call response and use it in next delete request
curl -X DELETE "http://${host_ip}:${DATASTORE_HOST_PORT}/data?bucket_name=<bucket_name>&file_name=<file_name>"

# As a clean-up step delete the sample pdf file.
rm -rf ./minimal-document.pdf

```

If you face any issue during accessing any of the endpoints, please make sure all variables are set and resolved properly by running `source ./run.sh --conf`.

#### Minio Console UI

You can also access **Minio Console UI** to verify the bucket creation and uploaded files by heading to `http://${host_ip}:{MINIO_CONSOLE_HOST_PORT}` in your browser. Use the Value of `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` as login credentials for Console UI.