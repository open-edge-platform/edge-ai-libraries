# Working with other services

DL Streamer Pipeline Server can work with following microservices for visualization and model management.

## Model Download

The [Model Download microservice](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-download/index.html) provides a REST API to download AI/ML models from multiple hubs (Hugging Face, Ultralytics, Ollama, Geti™ software, and Pipeline Zoo Models) and optionally convert them to OpenVINO™ IR format. By mounting a shared volume between Model Download and DL Streamer Pipeline Server, downloaded models become immediately accessible to DLSPS pipelines without any manual file transfer.

### Architecture Overview

Both services share a host directory mounted as a volume:

- **Model Download** writes models to `/opt/models` inside its container.
- **DL Streamer Pipeline Server** reads models from `/home/pipeline-server/models` inside its container.
- Both paths are mapped to the **same host directory**, so models downloaded through the Model Download API are instantly available to DLSPS.

### Setup with Docker Compose

Add both services to a Docker Compose file and declare a shared named volume (or bind-mount a host path):

```yaml
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

<<<<<<< HEAD
services:
  model-download:
    image: intel/model-download:latest
    container_name: model-download
    command: --plugins all
    ports:
      - "8200:8000"
    environment:
      - MODEL_PATH=/opt/models
      - HF_TOKEN=${HUGGINGFACEHUB_API_TOKEN:-}
=======
2. Follow the instructions in the [Model Download's Get Started Guide](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-download/get-started.html) to run the microservice.
3. Send a POST request to store a model.
    - Use the following `curl` command to send a POST request with FormData fields corresponding to the model's properties.

    ```bash
    curl -X POST 'PROTOCOL://HOSTNAME:32002/models' \
    --header 'Content-Type: multipart/form-data' \
    --form 'name="MODEL_NAME"' \
    --form 'file=@MODEL_ARTIFACTS_ZIP_FILE_PATH;type=application/zip' \
    --form 'version="MODEL_VERSION"' \
    --form 'project_name="Pallet Defect Detection"' \
    --form 'category="Detection"' \
    --form 'precision="FP32"' \
    --form 'architecture="YOLOX-TINY"'
    ```

    - Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
      - If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k` option to your `curl` command to ignore SSL certificate verification.
    - Replace `HOSTNAME` with the actual host name or IP address of the host system where the service is running.
    - Replace `MODEL_NAME` with the name of the model to be stored.
    - Replace `MODEL_ARTIFACTS_ZIP_FILE_PATH` with the file path to the zip file containing the model's artifacts.
    - Replace `MODEL_VERSION` with the version of the model to be stored.

   > **Note:** For any manual upload of Intel Geti™ models on model registry, please make sure to provide `origin` as `Geti`.

4. Send a GET request to retrieve a list of models and verify the successful storage of the model in Step 3.

    - Use the following `curl` command to send a GET request to the `/models` endpoint.

      ```bash
      curl -X GET 'PROTOCOL://HOSTNAME:32002/models'
      ```

    - Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
      - If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k` option to your `curl` command to ignore SSL certificate verification.
    - Replace `HOSTNAME` with the actual host name or IP address of the host system where the service is running.

### DL Streamer Pipeline Server Integration

#### Pre-requisites

In order to successfully, store models received from the model registry microservice within the context of DL Streamer Pipeline Server, the following steps are required before starting the Docker* container for DL Streamer Pipeline Server:

1. Create the `mr_models` directory in the same directory as your `docker-compose.yml` as referenced [here](../../../get-started.md) in the `volumes` section.
    - This directory will contain the models downloaded from the model registry using DL Streamer Pipeline Server's REST API.
    - The ownership of this directory is required to be the same user of the container (`intelmicroserviceuser`) to enable models to be stored successfully.
    ```sh
    mkdir -p mr_models

    sudo useradd -u 1999 intelmicroserviceuser
    # Verify that the user exists
    getent passwd intelmicroserviceuser
    sudo chown intelmicroserviceuser:intelmicroserviceuser mr_models
    ```

#### Configuration (.env)

##### HTTPS and HTTP mode

The following configuration applies to both the supported protocols HTTPS(default) and HTTP.
Replace `<PROTOCOL>` in the following steps with `https` or `http` according to the mode the model registry microservice was configured with when started based on the `ENABLE_HTTPS_MODE` environment variable value and the corresponding steps completed in the previous section.

The following environment variables are used to establish a connection with the model registry microservice:

- **MR_URL**: The URL where the model registry microservice is accessible.
  - If not set or left empty, the DL Streamer Pipeline Server will not be able to connect to the model registry successfully and an **error** message will be displayed in the logs.
  - Example: `MR_URL=<PROTOCOL>://10.101.10.101:32002`
- **MR_SAVED_MODELS_DIR**: The directory where models are saved when downloaded from the model registry microservice.
  - If this directory does not exist in the container, it will be created when a model is saved for the first time.
  - If you set the value for this variable to a custom path, you will need to update the `/home/pipeline-server/mr_models` path declared in the respective `docker-compose` file.
  - Default: `"./mr_models"` (Note: `.` represents the default working directory)
  - Example: `MR_SAVED_MODELS_DIR=./mr_models`
- **MR_REQUEST_TIMEOUT**: (String): The maximum amount of time in seconds that requests involving the model registry microservice are allowed to take.
  - Default: `300`
  - Example: `MR_REQUEST_TIMEOUT=300`

> **Tip:** Set the `LOG_LEVEL` environment variable to `DEBUG` to see detailed log messages about the model registry client's configuration and its communication with the Model Registry microservice. This is especially useful for troubleshooting, as it will display which environment variables are being used, when defaults are applied, and details about connection attempts and responses.

The model registry microservice supports both HTTPS and HTTP protocols. HTTP mode is enabled by default.
When enabled in HTTPS MODE, DL Streamer Pipeline Server will attempt to verify its SSL certificate using the file(s) in the `/run/secrets/ModelRegistry_Server` directory within the Docker container by default.

> **Note:** If you would prefer to run the model registry in HTTP mode, set the
> `ENABLE_HTTPS_MODE` environment variable to `false` before starting the containers. The
> remainder of this section can be skipped if you are using HTTP mode.

1. Create the `Certificates/model_registry/` directory in the same directory as your `docker-compose.yml`.

    - This directory should contain the `ca-bundle.crt` file associated to the model registry.

    ```sh
    mkdir -p Certificates/model_registry
    ```

    - Note: The `/run/secrets/ModelRegistry_Server` directory in the container is mounted to the local `Certificates/model_registry` directory on the host system as defined in the example `docker-compose.yml` file.

2. Navigate to the model registry's `Certificates/ssl` directory used with the model registry Docker container
    ```shell
    cd <path/to>/Certificates/ssl
    ```

3. Create a **CA BUNDLE** file from the model registry's `server-ca.crt` and `server.crt` files in its `Certificates/ssl` directory
    ```shell
    sudo cat server-ca.crt server.crt > ca-bundle.crt
    ```

4. Move (**DO NOT Copy**) the newly created `ca-bundle.crt` file from the model registry's `Certificates/ssl` directory to DL Streamer Pipeline Server's `Certificates/model_registry/` directory.

    - **Note:** By default, DL Streamer Pipeline Server requires the `ca-bundle.crt` file when sending requests to the model registry to verify its SSL certificate.

    - The `ca-bundle.crt` file is required for DL Streamer Pipeline Server and should not be kept in the model registry's `Certificates/ssl` directory when its containers are started. It will lead to SSL certificate verification issues between the model registry and its dependent containers.

      ```shell
      sudo mv ca-bundle.crt <path/to>/Certificates/model_registry/
      ```

**Note:** The following environment variable is used when HTTPS Mode is enabled:
- **MR_VERIFY_CERT (String)**: Controls whether SSL certificate verification is performed during HTTPS requests to the model registry microservice.
    - Valid options are `True`, `False`, and `</path/to/CA_Bundle_file>`.
        - `True` causes DL Streamer Pipeline Server to validate the model registry's certificate's chain of trust, checks its expiration date and verify its hostname.
        - `False` causes DL Streamer Pipeline Server to ignore verifying the SSL certificate. This may be useful during testing, but not advised for production.
        - `</path/to/CA_Bundle_file>` specifies the path to a **CA_BUNDLE** file.
    - Example: `MR_VERIFY_CERT=False`
    - Default Value: `/run/secrets/ModelRegistry_Server/ca-bundle.crt`

#### Init model download/deployment

##### Configuration (config.json)

DL Streamer Pipeline Server requires the following configuration properties to search, retrieve and store a model locally from the model registry microservice:
A sample config has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/model_registry/config.json`. We need to volume mount the sample config file in `docker-compose.yml` file. `WORKDIR` is your host machine workspace. Refer below snippets:

```sh
>>>>>>> main
    volumes:
      - shared_models:/opt/models
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s

  dlstreamer-pipeline-server:
    image: ${DLSTREAMER_PIPELINE_SERVER_IMAGE}
    container_name: dlstreamer-pipeline-server
    ports:
      - "8080:8080"
    volumes:
      - shared_models:/home/pipeline-server/models:ro
      # ... other required DLSPS volume mounts
    depends_on:
      model-download:
        condition: service_healthy

volumes:
  shared_models:
```

> **Note:** The `shared_models` named volume ensures both containers operate on the same model files. The `:ro` flag on the DLSPS side is optional but recommended to prevent DLSPS from accidentally modifying downloaded models.

### Downloading Models via the Model Download API

Once the services are running, use the Model Download REST API to pull models onto the shared volume. DLSPS can then reference them directly in pipeline configurations.

**Step 1 – Start the services:**

```bash
docker compose up -d
```

**Step 2 – Request a model download** (example: YOLOv8 from Ultralytics):

```bash
curl -X POST "http://localhost:8200/api/v1/models/download?download_path=yolo_model" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "yolov8s",
        "hub": "ultralytics",
        "type": "vision"
      }
    ],
    "parallel_downloads": false
  }'
```

The response contains a `job_id`:

```json
{
  "message": "Started processing 1 model(s)",
  "job_ids": ["5f0d4eba-c79c-4d02-97a6-43c3d0168ca0"],
  "status": "processing"
}
```

**Step 3 – Poll for completion** before launching pipelines:

```bash
curl -X GET "http://localhost:8200/api/v1/jobs/5f0d4eba-c79c-4d02-97a6-43c3d0168ca0"
```

Wait until the response shows `"status": "completed"`. The `result.download_path` field indicates the subdirectory under the shared volume where the model files were saved.

**Step 4 – Reference the model in a DLSPS pipeline** using the path inside the DLSPS container (`/home/pipeline-server/models/<download_path>`).

### Additional Resources

- [Model Download Documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-download/index.html)
- [Model Download API Reference](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-download/index.html) – full OpenAPI spec including upload, conversion, and job management endpoints