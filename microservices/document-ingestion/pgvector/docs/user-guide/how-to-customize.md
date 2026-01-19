# Build and customize options

This guide provides build from source and specific customization options provided when building
or deploying the microservice.

## Manually setup environment variables

The following environment variables are required for setting up the service. It is recommended
to use the `run.sh` runner script to setup the variables. Refer to this section only if any
of the variables need to be changed.

### Project name

- **PROJECT_NAME:** Helps provide a common docker compose project name and create a common
container prefix for all services involved.

### Minio related variables

- **MINIO_HOST:** Host name for Minio Server. This is used to communicate with Minio Server
by Data Store service inside container.
- **MINIO_API_PORT:** Port on which Minio Server's API service runs inside container.
- **MINIO_API_HOST_PORT**: Port on which we want to access Minio server's API service outside
container i.e. on host.
- **MINIO_CONSOLE_PORT:** Port on which we want MINIO UI Console to run inside container.
- **MINIO_CONSOLE_HOST_PORT:** Port on which we want to access MINIO UI Console on host machine.
- **MINIO_MOUNT_PATH:** Mount point for Minio server objects storage on host machine. This
helps persist objects stored on Minio server.
- **MINIO_ROOT_USER:** Username for MINIO Server. This is required while accessing Minio UI
Console. This needs to be overridden by setting `MINIO_PASSWD` variable on shell, if not using
the default value.
- **MINIO_ROOT_PASSWORD:** Password for MINIO Server. This is required while accessing Minio
UI Console. This needs to be overridden by setting `MINIO_USER` variable on shell, if not
using the default value.

### Embedding service related variables

Currently, TEI is used to host the embedding model. The following variables are required as a
result.

- **TEI_HOST:** Host IP address or service name for TEI Embedding service to help other
services connect to it.
- **TEI_HOST_PORT:** Port on host machine where we want to access TEI embedding Service
outside container.
- **EMBEDDING_ENDPOINT_URL:** TEI Embedding service API endpoint URL where it serves the model.
This endpoint is used by other services to get results from embedding model server.
- **TEI_EMBEDDING_MODEL_NAME:** This provides the name model served by TEI embedding service.

### PGVector DB related variables

- **PGVECTOR_HOST:** Host IP address or service name for PGVector DB service to help other
services connect to it.
- **PGVECTOR_USER:** User name for PG Vector DB. This needs to overridden by setting
`PGDB_USER` on shell, if not using the default value.
- **PGVECTOR_PASSWORD:** Password for PG Vector DB. This needs to overridden by setting
`PGDB_PASSWD` on shell, if not using the default value.
- **PGVECTOR_DBNAME:** Database name for PG Vector DB which contains different tables to
store embeddings. This needs to overridden by setting `PGDB_NAME` on shell, if not using the
default value.
- **INDEX_NAME:** Name of index used for creating embeddings. This is referenced in several
PG Vector DB queries and defines a particular context for retrieval. This needs to be overridden
by setting `PGDB_INDEX` on shell, if not using the default value.
- **PG_CONNECTION_STRING:** This is the connection string derived from previous set values for
PG Vector DB. This is used by other services to connect to the databases. Caution: override
it only if you are aware of what you are doing.

### Secrets and token variables

- **HUGGINGFACEHUB_API_TOKEN:** This is the token required for running Huggingface based
services and models. **It is mandatory  to set it and `run.sh` script.** To set it, export
`HUGGINGFACEHUB_API_TOKEN` variable from shell.

## Build from source

If you want to build the dataprep image locally instead of using pre-built images:
```bash
# Build with default tag (uses current date in YYYYMMDD format)
source ./run.sh --build dataprep

# Build with custom tag
source ./run.sh --build dataprep my-registry/my-dataprep:v1.0
```
**Note**: All built images are automatically labeled for easy management and cleanup.

## Common Customizations

Customization options are currently provided in the context of the sample application. Refer
to [ChatQnA sample application](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/chat-question-and-answer/index.html) for details like Helm and customization options.
