
# Get Started

<!--
**User Story US-1: Setting Up the Microservice**
- **As a developer**, I want to set up the microservice in my environment, so that I can start using it with minimal effort.

**Acceptance Criteria**:
1. Clear instructions for downloading and running the microservice with Docker.
2. Steps for building the microservice from source for advanced users.
3. Verification steps to ensure successful setup.
-->

The following microservices will be deployed with each dedicated to providing a specific capability. The dataprep microservice is essentially the orchestrating microservice providing the ingestion capability and interacting with other microservices to manage the supported capabilities.
- **dataprep microservice**: This acts as the backend application, offering REST APIs which the user can use to interact with the other microservices. It provides interfaces for uploading documents to object storage, creating and storing embeddings, and managing them.
- **vectorDB microservice**: This microservice is based on selected 3rd party vectorDB solution used. In this implementation, PGVector is used as the vectorDB.
- **Embedding microservice**: This provides the embedding service, optimizing the model used for creating and storing embeddings in the vectorDB. OpenAI API is used for creating the embeddings.
- **data store microservice**: This microservice is essentially the 3rd party solution provider. In this implementation, minIO is used as the data store. Standard API provided by minIO (AWS S3) is used for interacting with the microservice.

### Prerequisites

Before you begin, ensure the following prerequisites are addressed. Note that these pre-requisites are superceded by the prerequisites listed in respective application using this microservice.

- **System Requirements**: Verify that your system meets the [minimum requirements](./system-requirements.md).
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).
- **Docker compose installed**: Refer [Install docker compose](https://docs.docker.com/compose/install/).
- If the setup is behind a proxy, ensure `http_proxy`, `https_proxy`, and `no_proxy` are properly set on the shell.

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Quick start with environment variables
The runner script in root of project `run.sh` sets default values for most of the required environment variables when executed. For sensitive values like `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWD`, `HUGGINGFACEHUB_API_TOKEN` etc. user can export following environment variables in their shell before running the script.

```bash
# User MUST set all these! An error is thrown by docker compose if they are not set.
export HUGGINGFACEHUB_API_TOKEN=<your_huggingface_token>

# vectorDB and object store configuration
export MINIO_USER=<minio_user_or_s3_access_token>
export MINIO_PASSWD=<minio_password_or_s3_secret>
export PGDB_USER=<user_db_user_name>
export PGDB_PASSWD=<user_db_password>
export PGDB_NAME=<user_db_name>
export PGDB_INDEX=<user_db_index>

# OPTIONAL - If user wants to push the built images to a remote container registry, user needs to name the images accordingly. For this, image name should include the registry URL as well. To do this, set the following environment variable from shell. Please note that this URL will be prefixed to application name and tag to form the final image name.

export CONTAINER_REGISTRY_URL=<user_container_registry_url>
```
Refer to [manually customize](./how-to-customize.md) for customization options for the microservice.

## Quick Start with Docker

This method provides the fastest way to get started with the microservice.

1. **Clone the repository**:
    Run the following command to clone the repository:
    ```bash
    git clone <link-to-repository> -b release-1.2.0
    ```

2. **Change to project directory**:
    Start the container using:
    ```bash
    cd <clone-repo-dir-path>/microservices/document-ingestion/pgvector
    ```

3. **Configure the environment variables**:
    Set the required and optional environment variables as mentioned in [quick start with environment variables](#Quick-start-with-environment-variables). Optionally, user can edit the `run.sh` script to add further environment variables as required in their setup.

4. **Verify the configuration**
    ```bash
    source ./run.sh --conf
    # This will output docker compose configs with all the environment variables resolved. The user can verify whether they are configured correctly.
    ```
5. **Start the Microservices**:
    There are different options provided to start the microservices.
    ```bash
    # Run the development environment (only for DataStore) and prod environment for all other services in daemon mode
    source ./run.sh --dev

    # Run the production environment for all services in daemon mode
    source ./run.sh

    # Run the development environment (only for DataStore) and prod environment for all other services in non-daemon mode
    source ./run.sh --dev --nd

    # Run the production environment for all services in non-daemon mode
    source ./run.sh --nd
    ```
6. **Validate the setup**: Open your browser and navigate to:
    ```
    http://${host_ip}:${DATAPREP_HOST_PORT}/docs
    ```
    **Expected result**: Access to Data Store API Docs should now be available. Go through the DataPrep Service API docs to **upload**, **get** and **delete** documents to create/store/delete embeddings and upload/delete document sources for embeddings. Ensure that access to the DataPrep microservice is done from the same shell where `run.sh` was run. If not, run the script to only set the variables with a *--nosetup* flag: `source ./run.sh --nosetup`

<!--
**User Story US-2: Running and Exploring the Microservice**
- **As a developer**, I want to execute a predefined task or pipeline with the microservice, so that I can understand its functionality.

**Acceptance Criteria**:
1. Instructions to run a basic task or query using the microservice.
2. Examples of expected outputs for validation.
-->

## First Use: Running a Predefined Task

Try uploading a sample PDF file and verify that the embeddings and files are stored. Run the commands from the same shell as where the environment variables are set.

1. Download a sample PDF file:
    ```bash
    curl -LO https://github.com/py-pdf/sample-files/blob/main/001-trivial/minimal-document.pdf
    ```

2. POST the file to create embedding and store in object storage.
   ```bash
   curl -X POST "http://${host_ip}:${DATAPREP_HOST_PORT}/documents" \
       -H "Content-Type: multipart/form-data" \
       -F "files=@./minimal-document.pdf"
   ```

3. Verify whether embeddings were created and document was uploaded to object storage.
    ```bash
    curl -X GET "http://${host_ip}:${DATAPREP_HOST_PORT}/documents"
    ```
   Expected output: A JSON response with details of the file should be printed.

4.  Get the `bucket_name` and `file_name` from GET call response in step 3 and use it in the DELETE request below.
    ```bash
    curl -X DELETE "http://${host_ip}:${DATAPREP_HOST_PORT}/documents?bucket_name=<bucket_name>&file_name=<file_name>"
    ```

5. To clean-up, delete the sample pdf file.
   ```bash
   rm -rf ./minimal-document.pdf
   ```

## Advanced Setup Options

To customize the microservice, refer to [customization documentation](./how-to-customize.md).
<!--- [How to Deploy with Helm](./deploy-with-helm.md)-->


## Supporting Resources

- [API Reference](dataprep-api.yml)
