
# Get Started

<!--
**User Story US-1: Setting Up the Microservice**
- **As a developer**, I want to set up the microservice in my environment, so that I can start using it with minimal effort.

**Acceptance Criteria**:
1. Clear instructions for downloading and running the microservice with Docker.
2. Steps for building the microservice from source for advanced users.
3. Verification steps to ensure successful setup.
-->

The following microservices will be deployed, with each one dedicated to providing a specific
capability. The dataprep microservice is essentially the orchestrating microservice providing
the ingestion capability and interacting with other microservices to manage the supported
capabilities.

- **dataprep microservice**: This acts as the backend application, offering REST APIs which
the user can use to interact with the other microservices. It provides interfaces for uploading
documents to object storage, creating and storing embeddings, and managing them.
- **vectorDB microservice**: This microservice is based on selected 3rd party vectorDB solution
used. In this implementation, PGVector is used as the vectorDB.
- **Embedding microservice**: This provides the embedding service, optimizing the model used for
creating and storing embeddings in the vectorDB. OpenAI API is used for creating the embeddings.
- **data store microservice**: This microservice is essentially the 3rd party solution provider.
In this implementation, minIO is used as the data store. Standard API provided by minIO (AWS S3)
is used for interacting with the microservice.

## Prerequisites

Before you begin, ensure the following prerequisites are addressed. Note that these
prerequisites are superceded by the prerequisites listed in the respective application using
this microservice.

- **System Requirements**: Verify that your system meets the [minimum requirements](./get-started/system-requirements.md).
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).
- **Docker compose installed**: See [Install docker compose](https://docs.docker.com/compose/install/).
- **Proxy Configuration (if applicable)**: If the setup is behind a proxy, ensure `http_proxy`,
`https_proxy`, and `no_proxy` are properly set on the shell before starting the services.

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new
to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Quick start with environment variables

The runner script in root of project, `run.sh`, sets default values for most of the required
environment variables when executed. For sensitive values, like `MINIO_ROOT_USER`,
`MINIO_ROOT_PASSWD`, `HUGGINGFACEHUB_API_TOKEN`, etc., the user can export the following
environment variables in their shell before running the script.

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

# HTTP request configuration (optional)
# Set USER_AGENT_HEADER to define a custom User-Agent string for outgoing HTTP requests.
# If not set, a robust default User-Agent is automatically applied
# Setting a clear and descriptive User-Agent helps external servers identify the application and
# reduces the chance of requests being treated as bot traffic.
export USER_AGENT_HEADER=<your_user_agent_string>

# OPTIONAL - If user wants to push the built images to a remote container registry, user needs to name the images accordingly. For this, image name should include the registry URL as well. To do this, set the following environment variable from shell. Please note that this URL will be prefixed to application name and tag to form the final image name.

export CONTAINER_REGISTRY_URL=<user_container_registry_url>
```

## ALLOWED_HOSTS Configuration

The `ALLOWED_HOSTS` environment variable is critical for security as it restricts which domains the microservice can access during URL ingestion. Configure this based on your deployment scenario:

```bash
export ALLOWED_HOSTS=<comma_separated_list_of_trusted_domains> # To mitigate SSRF attacks during URL ingestion
```

### Example Configurations

- **Enterprise Setup**: For environments within an organization firewall with access to intranet and internal wikis

    Example: Allow access to internal Intel domains and public Wikipedia

    export ALLOWED_HOSTS="\*.intel.com,en.wikipedia.org,\*.wikipedia.org,\*.github.com"


- **Public Setup**: For public deployments with access to general internet resources:

    Example: Allow access to public wikis and common websites

    export ALLOWED_HOSTS="en.wikipedia.org,\*.wikipedia.org,craigslist.org,\*.craigslist.org,\*.medium.com"

**Note**: Use comma-separated domain patterns. Wildcards (*) are supported for subdomains. Be as specific as possible to minimize security risks from SSRF attacks.

Refer to instructions on [manual customization](./how-to-customize.md) for the customization
options for the microservice.

## Proxy Configuration

If your environment requires proxy settings, configure the following environment variables
before starting the services:

```bash
# Set proxy environment variables
export http_proxy=http://your-proxy-server:port
export https_proxy=https://your-proxy-server:port
export no_proxy=localhost,127.0.0.1,your-internal-hosts
```

**Important Notes:**

- These proxy settings will be automatically passed to all services including the dataprep
microservice during build time
- The `no_proxy` variable should include localhost and any internal services that should bypass
the proxy
- Ensure these variables are set in the same shell session where you run the `run.sh` script

## Quick Start with Docker

This method provides the fastest way to get started with the microservice.

1. **Clone the repository**:
    Run the following command to clone the repository:
    ```bash
    # Clone the latest on mainline
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
    # Alternatively, Clone a specific release branch
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
    ```

2. **Change to project directory**:
    Start the container using:
    ```bash
    cd edge-ai-libraries/microservices/document-ingestion/pgvector
    ```

3. **Configure the environment variables**:
    Set the required and optional environment variables as mentioned in
    [quick start with environment variables](#Quick-start-with-environment-variables).
    Optionally, the user can edit the `run.sh` script to add further environment variables as
    required in their setup.

4. **Verify the configuration**
    ```bash
    source ./run.sh --conf
    # This will output docker compose configs with all the environment variables resolved. The user can verify whether they are configured correctly.
    ```
    The valid configuration will ensure the latest prebuilt image from `intel` registry is downloaded. The scripts take care of this.

5. **Start the Microservices**:
    The user is required to configure the registry and tag params before starting the microservices.
    ```bash
    export CONTAINER_REGISTRY_URL=<preferred-registry-url> #defaults to "intel/" if not set
    export CONTAINER_TAG=<preferred-tag> #defaults to "latest" if not set

    # Run the production environment for all services in daemon mode
    source ./run.sh

    # Run the production environment for all services in non-daemon mode
    source ./run.sh --nd
    ```
    If the user prefers to build and run the `dataprep` in dev mode:
    ```bash
    # Run the development environment (only for DataStore) and prod environment for all other services in daemon mode
    source ./run.sh --dev

    # Run the development environment (only for DataStore) and prod environment for all other services in non-daemon mode
    source ./run.sh --dev --nd
    ```


6. **Validate the setup**: Open your browser and navigate to:
    ```
    http://${host_ip}:${DATAPREP_HOST_PORT}/docs
    ```
    **Expected result**: Access to Data Store API Docs should now be available. Go through the
    DataPrep Service API docs to **upload**, **get** and **delete** documents to
    create/store/delete embeddings and upload/delete document sources for embeddings. Ensure
    that access to the DataPrep microservice is done from the same shell where `run.sh` was run.
    If not, run the script to only set the variables with a *--nosetup* flag: `source ./run.sh --nosetup`

## Cleanup and Management

The microservice provides several cleanup options for managing Docker images and containers:

### Stop Services
```bash
# Stop and remove all running containers
source ./run.sh --down

# Stop and remove all running containers including volumes
source ./run.sh --down --volumes
```

### Image Cleanup
```bash
# Remove all project-related Docker images (uses Docker labels for accurate cleanup)
source ./run.sh --clean

# Remove only dataprep service images
source ./run.sh --clean dataprep

# Complete cleanup - removes containers, images, volumes, and networks
source ./run.sh --purge
```

>**Note**: The cleanup commands use Docker labels to identify and remove images, ensuring that
custom-tagged images built with `--build` are properly cleaned up regardless of their tag names.

<!--
**User Story US-2: Running and Exploring the Microservice**
- **As a developer**, I want to execute a predefined task or pipeline with the microservice, so that I can understand its functionality.

**Acceptance Criteria**:
1. Instructions to run a basic task or query using the microservice.
2. Examples of expected outputs for validation.
-->

## Application Usage

### Type 1: Upload Files

Try uploading a sample PDF file and verify that the embeddings and files are stored. Run the
commands from the same shell as where the environment variables are set.

1. **Download a sample PDF file**:
   Download a sample PDF document to test the file upload and embedding creation process.
    ```bash
    curl -LO https://github.com/py-pdf/sample-files/blob/main/001-trivial/minimal-document.pdf
    ```

2. **Upload the file to create embedding and store in object storage**:
   Submit the PDF file to the dataprep service for processing and storage.
   ```bash
   curl -X POST "http://${host_ip}:${DATAPREP_HOST_PORT}/documents" \
       -H "Content-Type: multipart/form-data" \
       -F "files=@./minimal-document.pdf"
   ```

3. **Verify the file was processed and stored**:
   Retrieve a list of all files to confirm successful processing and storage.
    ```bash
    curl -X GET "http://${host_ip}:${DATAPREP_HOST_PORT}/documents"
    ```
   Expected output: A JSON response with details of the file should be printed.

4. **Delete the uploaded file**:
   Remove the stored file from the system using the file details from step 3.
   Get the `bucket_name` and `file_name` from GET call response in step 3 and use it in the DELETE request below.
    ```bash
    curl -X DELETE "http://${host_ip}:${DATAPREP_HOST_PORT}/documents?bucket_name=<bucket_name>&file_name=<file_name>"
    ```

5. **Clean up the sample PDF file**:
   Remove the downloaded PDF file from your local system.
   ```bash
   rm -rf ./minimal-document.pdf
   ```

### Type 2: Upload URLs

Try uploading web page URLs and verify that the embeddings are created and stored. Run the
commands from the same shell as where the environment variables are set.

 > **Note**: This URL ingestion microservice works best with pages that are not heavily reliant
 on JavaScript such as Wikipedia, which serve as ideal URL input sources. For JavaScript-intensive
 pages (social media feeds, Single Page Applications), the API may indicate a successful request
 but the actual content might not be captured. Such pages should be avoided or handled separately.

 > **Security Note**: This microservice only allows secure URLs using the HTTPS protocol.

1. **Upload URLs to create and store embeddings**:
   Submit one or more URLs to be processed for embedding creation.
   ```bash
   curl -X POST \
     "http://${host_ip}:${DATAPREP_HOST_PORT}/urls" \
     -H 'accept: application/json' \
     -H 'Content-Type: application/json' \
     -d '[
     "https://en.wikipedia.org/wiki/Fiat",
     "https://en.wikipedia.org/wiki/Lunar_eclipse"
   ]'
   ```

2. **Verify the URLs were processed and stored**:
   Retrieve a list of all URLs that have been processed and stored in the system to confirm successful processing.
   ```bash
   curl -X GET \
     "http://${host_ip}:${DATAPREP_HOST_PORT}/urls" \
     -H 'accept: application/json'
   ```
   Expected output: A JSON response with the list of processed URLs should be printed.

3. **Delete a specific URL**:
   Get the URL from the GET call response in step 2 and use it in the DELETE request below.
   ```bash
   curl -X DELETE \
     "http://${host_ip}:${DATAPREP_HOST_PORT}/urls?url=<url_to_be_deleted>&delete_all=false" \
     -H 'accept: */*'
   ```

4. **Delete all URLs**:
   To remove all URLs from the database at once:
   ```bash
   curl -X DELETE \
     "http://${host_ip}:${DATAPREP_HOST_PORT}/urls?delete_all=true" \
     -H 'accept: */*'
   ```

## Advanced Setup Options

To customize the microservice, refer to [customization documentation](./how-to-customize.md).
<!--- [How to Deploy with Helm](./deploy-with-helm.md)-->

## Supporting Resources

- [API Reference](./api-reference.md)

<!--hide_directive
:::{toctree}
:hidden:
get-started/system-requirements
:::
hide_directive-->
