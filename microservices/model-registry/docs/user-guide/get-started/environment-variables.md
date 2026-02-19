# Environment Variables

The model registry microservice's configuration is defined via environment variables.

## Required:
- **MINIO_ACCESS_KEY (String)**: The access key used to access a MinIO object storage server
    - Example: `MINIO_ACCESS_KEY={access_key}`
- **MINIO_SECRET_KEY (String)**: The secret key used to access a MinIO object storage server
    - Example: `MINIO_SECRET_KEY={secret_key}`
- **MR_USER_NAME (String)**: The username for the user within the model-registry Docker container
    - Example: `MR_USER_NAME={username}`
- **MR_UID (Integer)**: The ID for the user within the Docker container
    - Example: `MR_UID=2333`
- **PSQL_HOSTNAME (String)**: The host name for the PostgreSQL service
    - Example: `PSQL_HOSTNAME=mr_postgres`
- **PSQL_PASSWORD (String)**: The password associated to the `POSTGRES_USER`
    - Example: `PSQL_PASSWORD={password}`
- **PSQL_DATABASE (String)**: The name of the PostgreSQL database
    - Example: `PSQL_DATABASE=model_registry_db`
- **PSQL_PORT (Integer)**: The port for which the PostgreSQL server listens for connections and requests
    - Example: `PSQL_PORT=5432`
- **MINIO_BUCKET_NAME (String)**: The name of the bucket where model artifacts are stored on the MinIO Object Storage server
    - Example: `MINIO_BUCKET_NAME=model-registry`
- **MINIO_HOSTNAME (String)**: The host name for the MinIO service
    - Example: `MINIO_HOSTNAME=mr_minio`
- **MINIO_SERVER_PORT (Integer)**: The port for which the MinIO server listens for connections and requests
    - Example: `MINIO_SERVER_PORT=8000`
- **VERSION (Float)**: The version of the model registry microservice
    - Example: `VERSION=1.0.3`
- **SERVER_PORT (Integer)**: The port for which the Model Registry server listens for connections and requests
    - Example: `SERVER_PORT=5002`
- **MLFLOW_S3_ENDPOINT_URL (String)**: The URL for a S3 endpoint to use for artifact operations
    - Example: `MLFLOW_S3_ENDPOINT_URL=http://127.0.0.1:8000`
- **SERVER_CERT**: The path to the certificate for the server
  > **Note**: This environment variable is required if `ENABLE_HTTPS_MODE=True` or is unset.
  - Example: `SERVER_CERT=/run/secrets/ModelRegistry_Server/public.crt`
- **CA_CERT**: The path to the certificate for the Certificate Authority (CA)
  > **Note**: This environment variable is required if `ENABLE_HTTPS_MODE=True` or is unset.
  - Example: `CA_CERT=/run/secrets/ModelRegistry_Server/server-ca.crt`
- **SERVER_PRIVATE_KEY**: The path to the private key for the server
  > **Note**: This environment variable is required if `ENABLE_HTTPS_MODE=True` or is unset.
  - Example: `SERVER_PRIVATE_KEY=/run/secrets/ModelRegistry_Server/private.key`

## Optional:
- **HOST_IP_ADDRESS (String)**: The IP address of the host system that the microservice is running on
    - Example: `HOST_IP_ADDRESS=192.224.24.200`
- **ENABLE_HTTPS_MODE (Boolean)**: Indicates whether the microservice should run with HTTPS enabled.
    - Example: `ENABLE_HTTPS_MODE=False`
    - Default Value: `True`
- **MIN_LOG_LEVEL (String)**: The minimum threshold of log messages to be shown
    - Valid options are "NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", and "CRITICAL". These levels are listed from least to most severe.
    - Example: `MIN_LOG_LEVEL=INFO`
    - Default Value: `INFO`
- **GETI_HOST (String)**: The hostname or IP address and port of a Geti Server
    - Examples:
      - `GETI_HOST=https://app.geti.intel.com`
      - `GETI_HOST=http://10.13.200.0:8001`
    - Default Value: `None`
- **GETI_TOKEN (String)**: The access token used to enable access to a Geti Server
    - Example: `GETI_TOKEN={token}`
    - Default Value: `None`
- **GETI_SERVER_API_VERSION (String)**: The version of the API provided by a GETI server
    - Example: `GETI_SERVER_API_VERSION=v1`
    - Default Value: `None`
- **GETI_ORGANIZATION_ID (String)**: The ID of an organization within a GETI server
    - Example: `GETI_ORGANIZATION_ID=1`
    - Default Value: `None`
- **GETI_WORKSPACE_ID (String)**: The ID of a workspace within a GETI server
    - Example: `GETI_WORKSPACE_ID=1`
    - Default Value: `None`
- **GETI_SERVER_SSL_VERIFY (Boolean)**: Controls whether to verify the SSL certificates of a Geti server
  - Example: `GETI_SERVER_SSL_VERIFY=True`
  - Default Value: `True`
