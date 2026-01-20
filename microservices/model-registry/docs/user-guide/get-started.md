# Get Started

The **Model Registry microservice** enables developers to register, update, retrieve, and
delete models. This section provides step-by-step instructions on how to:

- Set up the microservice using a pre-built Docker image for quick deployment.
- Run predefined tasks to explore its functionality.
- Learn how to modify basic configurations to suit specific requirements.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./get-started/system-requirements.md).
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new
to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Quick Start with Docker

This method provides the fastest way to get started with the microservice.

1. Pull the Docker* image from Docker Hub
    ```sh
    docker pull intel/model-registry:1.0.3
    ```

1. Create a `.env` file with the following environment variables:
    ```sh
    HOST_IP_ADDRESS=
    MR_INSTALL_PATH=/opt/intel/mr

    ENABLE_HTTPS_MODE=false

    # Docker security
    MR_USER_NAME=mruser
    MR_UID=2025

    #PostgreSQL service & client adapter
    MR_PSQL_HOSTNAME=mr_postgres
    MR_PSQL_PASSWORD=
    MR_PSQL_DATABASE=model_registry_db
    MR_PSQL_PORT=5432

    # MinIO service & client
    MR_MINIO_ACCESS_KEY=
    MR_MINIO_SECRET_KEY=
    MR_MINIO_BUCKET_NAME=model-registry
    MR_MINIO_HOSTNAME=mr_minio
    MR_MINIO_SERVER_PORT=8000

    # Model Registry service
    MR_VERSION=1.0.3
    MR_MIN_LOG_LEVEL=INFO
    MR_SERVER_PORT=8111

    # MLflow
    MR_MLFLOW_S3_ENDPOINT_URL=http://127.0.0.1:8000
    ```

1. Enter the desired values for the REQUIRED [Environment Variables](./environment-variables.md)
in the `.env` file:
    1. MR_PSQL_PASSWORD
    2. MR_MINIO_ACCESS_KEY
    3. MR_MINIO_SECRET_KEY

1. Create directories to be used for persistent storage by the Postgres* and MinIO* Docker containers
    ```sh
    set -a

    source .env

    set +a

    mkdir -p $MR_INSTALL_PATH/data/mr_postgres

    mkdir -p $MR_INSTALL_PATH/data/mr_minio

    useradd -u $MR_UID $MR_USER_NAME

    chown -R $MR_USER_NAME:$MR_USER_NAME $MR_INSTALL_PATH/data/mr_postgres $MR_INSTALL_PATH/data/mr_minio
    ```
    > **Note**: The data in these directories will persist after the containers are removed.
    If you would like to subsequently start the containers with no pre-existing data, delete
    the contents in the directories before starting the containers.

1. Create a `docker-compose.yml` file with the following configurations:
    ```yaml
    services:
      model-registry:
        image: intel/model-registry:${MR_VERSION}
        container_name: model-registry
        hostname: model-registry
        ipc: "none"
        ports:
        - "${HOST_IP_ADDRESS}:32002:${MR_SERVER_PORT}"
        restart: unless-stopped
        deploy:
          resources:
            limits:
              memory: 4096mb
              cpus: '0.30'
              pids: 200
            reservations:
              memory: 2048mb
              cpus: '0.15'
        security_opt:
          - no-new-privileges
        healthcheck:
          test: ["CMD-SHELL", "exit", "0"]
        environment:
          AppName: "ModelRegistry"
          MIN_LOG_LEVEL: ${MR_MIN_LOG_LEVEL}
          ENABLE_HTTPS_MODE: ${ENABLE_HTTPS_MODE}
          MLFLOW_TRACKING_URI: postgresql+psycopg2://${MR_USER_NAME}:${MR_PSQL_PASSWORD}@mr_postgres:${MR_PSQL_PORT}/${MR_PSQL_DATABASE}
          MLFLOW_S3_ENDPOINT_URL: ${MR_MLFLOW_S3_ENDPOINT_URL}
          MINIO_HOSTNAME: ${MR_MINIO_HOSTNAME}
          MINIO_SERVER_PORT: ${MR_MINIO_SERVER_PORT}
          MINIO_ACCESS_KEY: ${MR_MINIO_ACCESS_KEY}
          MINIO_SECRET_KEY: ${MR_MINIO_SECRET_KEY}
          MINIO_BUCKET_NAME: ${MR_MINIO_BUCKET_NAME}
          SERVER_PORT: ${MR_SERVER_PORT}
          LSHOST: host.docker.internal
          SERVER_CERT: /run/secrets/ModelRegistry_Server/public.crt
          CA_CERT: /run/secrets/ModelRegistry_Server/server-ca.crt
          SERVER_PRIVATE_KEY: /run/secrets/ModelRegistry_Server/private.key
          no_proxy: mr_minio
          NO_PROXY: mr_minio
        volumes:
          - ./Certificates/ssl/:/run/secrets/ModelRegistry_Server:ro
        extra_hosts:
          - "host.docker.internal:host-gateway"
        networks:
          - mr
      mr_postgres:
        image: postgres:13
        container_name: mr_postgres
        hostname: mr_postgres
        restart: unless-stopped
        security_opt:
          - no-new-privileges
        environment:
          AppName: "ModelRegistry"
          POSTGRES_USER: ${MR_USER_NAME}
          POSTGRES_PASSWORD: ${MR_PSQL_PASSWORD}
          POSTGRES_DB: ${MR_PSQL_DATABASE}
        volumes:
        - ${MR_INSTALL_PATH}/data/mr_postgres:/var/lib/postgresql/data
        expose:
          - ${MR_PSQL_PORT}
        user: "${MR_UID}:${MR_UID}"
        networks:
          - mr
      mr_minio:
        image: minio/minio:RELEASE.2020-12-12T08-39-07Z
        container_name: mr_minio
        hostname: mr_minio
        ipc: "none"
        expose:
          - ${MR_MINIO_SERVER_PORT}
        volumes:
          - ./Certificates/ssl/:/certs/:rw
          - ${MR_INSTALL_PATH}/data/mr_minio:/data
        networks:
          - mr
        restart: unless-stopped
        security_opt:
          - no-new-privileges
        environment:
          MR_USER_NAME: ${MR_USER_NAME}
          MINIO_ACCESS_KEY: ${MR_MINIO_ACCESS_KEY}
          MINIO_SECRET_KEY: ${MR_MINIO_SECRET_KEY}
        command: server --address ":8000" --certs-dir /certs /data
    networks:
      mr:
        driver: bridge
    ```

1. Start and run the defined services in the `docker-compose.yml` file as Docker* containers
    ```sh
    docker compose up -d
    ```

1. **Verify the Microservice**:
    Check that the container is running:
    ```bash
    docker ps
    ```
    - **Expected output**: The container appears in the list with the status “Up.”

## Storing a Model in the Registry

1. **Send a POST request to store a model.**
   - Use the following `curl` command to send a POST request with FormData fields corresponding
   to the model's properties.

    ```bash
    curl -X POST 'PROTOCOL://HOSTNAME:32002/models' \
    --header 'Content-Type: multipart/form-data' \
    --form 'name="MODEL_NAME"' \
    --form 'file=@MODEL_ARTIFACTS_ZIP_FILE_PATH;type=application/zip' \
    --form 'version="MODEL_VERSION"'
    ```

    - Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
      - If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k`
      option to your `curl` command to ignore SSL certificate verification.
    - Replace `HOSTNAME` with the actual host name or IP address of the host system where the
    service is running.
    - Replace `MODEL_NAME` with the name of the model to be stored.
    - Replace `MODEL_ARTIFACTS_ZIP_FILE_PATH` with the file path to the zip file containing
    the model's artifacts.
    - Replace `MODEL_VERSION` with the version of the model to be stored.

    For the complete list of supported model properties, visit `PROTOCOL://HOSTNAME:32002/docs`.

1. **Parse the response.**
    - The response will include the ID of the newly stored model.

## Fetching a List of Models in the Registry

1. **Send a GET request to retrieve a list of models.**
    - Use the following `curl` command to send a GET request to the `/models` endpoint.

    ```bash
    curl -X GET 'PROTOCOL://HOSTNAME:32002/models'
    ```

    - Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
      - If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k`
      option to your `curl` command to ignore SSL certificate verification.
    - Replace `HOSTNAME` with the actual host name or IP address of the host system where the
    service is running.

1. **Include query parameters (optional).**
    - If you want to filter the list, you can include query parameters in the URL.

    - For example, to filter by `project_name`:

    ```bash
    curl -X GET 'PROTOCOL://HOSTNAME:32002/models?project_name=PROJECT_NAME'
    ```

    - Replace `PROJECT_NAME` with the project_name associated to a model stored in the registry.

    - For the complete list of supported query parameters, visit `PROTOCOL://HOSTNAME:32002/docs`.

1. **Parse the response.**
    - The response will be a list containing the metadata of models stored in the registry.

## Getting a specific model in the Registry

1. **Send a GET request to get a model.**
    - Use the following `curl` command to send a GET request to the `/models/MODEL_ID` endpoint.

    ```bash
    curl -L -X GET 'PROTOCOL://HOSTNAME:32002/models/MODEL_ID'
    ```

    - Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
      - If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k`
      option to your `curl` command to ignore SSL certificate verification.
    - Replace `HOSTNAME` with the actual host name or IP address of the host system where the
    service is running.
    - Replace `MODEL_ID` with the `id` of the desired model.

1. **Parse the response.**
    - The response will have a `200 OK` status code and the metadata for a model.

## Updating 1 or more properties for a specific model in the Registry

1. **Send a PUT request to update properties of a model.**
    - Use the following `curl` command to send a PUT request to the `/models` endpoint.

    ```bash
    curl -L -X PUT 'PROTOCOL://HOSTNAME:32002/models/MODEL_ID' \
    --form 'score="NEW_MODEL_SCORE"' \
    --form 'format="NEW_MODEL_FORMAT"'
    ```

    - Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
      - If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k`
      option to your `curl` command to ignore SSL certificate verification.
    - Replace `HOSTNAME` with the actual host name or IP address of the host system where the
    service is running.
    - Replace `MODEL_ID` with the `id` of the desired model.
    - Replace`NEW_MODEL_SCORE`, and `NEW_MODEL_FORMAT` with the desired new values to be stored.

    - For the complete list of supported query parameters, visit `PROTOCOL://HOSTNAME:32002/docs`.

1. **Parse the response.**
    - The response will be a JSON object containing a status of the operation and a message.

## Downloading files for a specific model in the Registry

1. **Send a GET request to download files associated with a model in the Registry.**
    - Use the following `curl` command to send a GET request to the `/models/MODEL_ID/files` endpoint.

    ```bash
    curl -X GET 'PROTOCOL://HOSTNAME:32002/models/MODEL_ID/files'
    ```

    - Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
      - If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k`
      option to your `curl` command to ignore SSL certificate verification.
    - Replace `HOSTNAME` with the actual host name or IP address of the host system where the
    service is running.
    - Replace `MODEL_ID` with the `id` of the desired model.

1. **Parse the Response.**
    - The response will be a Zip file.

## Deleting a Model in the Registry

1. **Send a DELETE request to delete a model.**
    - Use the following `curl` command to send a DELETE request to the `/models/MODEL_ID` endpoint.

    ```bash
    curl -L -X DELETE 'PROTOCOL://HOSTNAME:32002/models/MODEL_ID'
    ```

    - Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
      - If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k`
      option to your `curl` command to ignore SSL certificate verification.
    - Replace `HOSTNAME` with the actual host name or IP address of the host system where the
    service is running.
    - Replace `MODEL_ID` with the `id` of the desired model.

1. **Parse the response.**
    - The response will have a `200 OK` status code and an empty body.

## Advanced Setup Options

For alternative ways to set up the microservice, see:

- [How to Build from Source](./how-to-build-from-source.md)
- [How to Deploy with Helm](./how-to-deploy-with-helm.md)

## Next Steps

- [How to interface with a remote Intel® Geti™ Software using the Model Registry microservice](./how-to-interface-with-intel-geti-platform.md)

## Troubleshooting

1. **Docker Container Fails to Start**:
    - Run `docker logs {{container-name}}` to identify the issue.
    - Check if the required port is available.

2. **Cannot Access the Microservice**:
    - Confirm the container is running:
      ```bash
      docker ps
      ```

## Supporting Resources

- [Overview](./index.md)
- [How It Works](./how-it-works.md)
- [System Requirements](./get-started/system-requirements.md)
- [Environment Variables](./environment-variables.md)
- [API Reference](./api-reference.md)

<!--hide_directive
:::{toctree}
:hidden:

get-started/system-requirements

:::
hide_directive-->
