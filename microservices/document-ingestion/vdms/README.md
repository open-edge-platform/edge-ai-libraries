# VDMS-DataPrep Service

VDMS-DataPrep service helps us create and store embeddings for text/video files in [Intel VDMS Vector DB](https://github.com/IntelLabs/vdms) and store the source video files directly in Minio object storage.

> Only MP4 file format is supported for creating video files embeddings, as of now.

## Project Structure

- `scripts` directory contains various shell scripts to help perform tasks like linting, testing and have entry points for the docker images which we will be building.
- `docker` directory:
  - has the Dockerfile to build the VDMS-Dataprep application image.
  - has docker compose files for Prod and dev setup. This helps spin-up VDMS-Dataprep application container along with all other required microservices _(eg. VDMS VectorDB, Minio Server etc.)_.
- `src` directory contains the application code.
- `tests` directory contains the tests for testing the vdms-dataprep application.
- `poetry.lock` and `poetry.toml` files help in dependency management for the Python application while building it. `poetry.lock` especially helps and installing the same version of python packages which was installed in a working dev environment.
- `setup.sh` is a setup bash script that helps quickly **lint**, **test**, **build** images and **setup** the application along with all required dependencies.
- `.dockerignore` is a file which tells the docker build process what not to include in our image. This is just to cut the unnecessary files being copied into docker image.
- `README.md` contains this documentation.

## Configuration & Setup

We will be running our application in docker containers. Configuration step involves setting various environment variables, which are prerequisites for spinning up the application container along with its dependencies. Dependencies are other applications/microservices which also run in docker containers. **For proper functioning of all these application containers, proper setup of environment variables is crucial.**

For end-to-end VDMS-DataPrep application setup, **three** application containers for following services will be spin-up:

- **vdms-dataprep:** This service contains **DataPrep API Server** application.
- **vdms-vector-db:** This service runs **VDMS Vector DB**. This is backend vector DB used by DataPrep API Server.
- **Minio Server:** This service runs Minio Server, the backend Object storage service used directly by the VDMS-DataPrep service.

These **three** services are part of `docker/compose.yaml` file. All these services would be requiring their own set of environment variables to be setup.

### Prerequisites

Please make sure following prerequisites are already present on your machine:

- Ubuntu 20.04 or later (Recommended)
- Docker
- Docker Compose
- Python 3.10 or later
- If you are behind a proxy, please make sure `http_proxy`, `https_proxy`, `no_proxy` are properly set on the shell you use.

#### Optional Requirement

If you are planning to do development or contribution, `poetry` should be installed on your host _(this will be already installed in the application container)_. See [Development Guide](#development-guide). Poetry helps in dependency management for python application. [See this](https://python-poetry.org/docs/#installing-with-the-official-installer) for steps to install poetry on your system.

### Environment Variables

Following environment variables are required for setting up the application. **The setup script `setup.sh` takes care most of these. Here, we present them mostly for informational purpose, for the cases where you want to override these for any reason. You can safely skip this section and move to next.**

- **PROJECT_NAME:** Helps provide a common docker compose project name and create a common container prefix for all services involved.
- **COVERAGE_REQ:** Helps to set the test coverage requirement criteria. If coverage is less than this criteria, `final-dev` image will fail to build.
- **PROJ_TEST_DIR:** The directory where all tests reside. This is used while running scripts to run tests.
- **REGISTRY:** This is container registry name. To be able to push an image to remote container registry, image name should contain the registry URL as well. Hence, value of this variable is used as prefix to the image name in docker compose file. Its value is set by concatenating the value of `REGISTRY_URL` environment variable with `PROJECT_NAME`. If `REGISTRY_URL` is not set, only the value of `PROJECT_NAME` is used and resulting image name does not contain any registry URL. If `PROJECT_NAME` is also not set, only the application name is used as image name. We must set `REGISTRY_URL`, if we want to push images to container registry.

#### Minio Related variables:

- **MINIO_HOST:** Host name for Minio Server. This is used to communicate with Minio Server by VDMS-DataPrep service inside container.
- **MINIO_API_PORT:** Port on which Minio Server's API service runs inside container.
- **MINIO_API_HOST_PORT:** Port on which we want to access Minio server's API service outside container i.e. on host.
- **MINIO_CONSOLE_PORT:** Port on which we want MINIO UI Console to run inside container.
- **MINIO_CONSOLE_HOST_PORT:** Port on which we want to access MINIO UI Console on host machine.
- **MINIO_MOUNT_PATH:** Mount point for Minio server objects storage on host machine. This helps persist objects stored on Minio server.
- **MINIO_ROOT_USER:** Username for MINIO Server. This is required while accessing Minio UI Console. This needs to overridden by setting `MINIO_PASSWD` variable on shell, if not using the default value.
- **MINIO_ROOT_PASSWORD:** Password for MINIO Server. This is required while accessing Minio UI Console. This needs to overridden by setting `MINIO_USER` variable on shell, if not using the default value.
- **MINIO_SECURE:** Whether to use HTTPS for Minio connections (default is `false`).
- **DEFAULT_BUCKET_NAME:** Default bucket name in Minio for storing videos.

#### VDMS Vector DB and VDMS-DataPrep Related variables:

- **VDMS_DATAPREP_HOST_PORT:** Port on host machine where we want to access VDMS-DataPrep Service outside container.
- **VDMS_VDB_HOST_PORT:** Port on host machine where we want to access VDMS Vector DB Service outside container.
- **VDMS_VDB_PORT:** Port on which VDMS Vector DB service runs inside container.
- **VDMS_VDB_HOST:** Host name for VDMS Vector DB service. This is used by other application containers for communication.
- **INDEX_NAME:** Name of the collection used to store embeddings in VDMS Vector DB in prod setup.

### How to set environment variables

The setup script in root of project `setup.sh` sets default values for most of the required environment variables once we run it. For values like `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD`, we export following env vars on our shell before running the script.

```bash
export MINIO_ROOT_USER="minio_user_or_s3_access_token"
export MINIO_ROOT_PASSWORD="minio_password_or_s3_secret"

# OPTIONAL - If you want to push the built images to a remote container registry, you need to name the images accordingly. For this, image name should include the registry URL as well. To do this, set the following environment variable from shell. Please note that this URL will be prefixed to the application name and tag to form the final image name.

export REGISTRY_URL="your_container_registry_url"
```

For all other variables, you can edit the `setup.sh` file in project root and update any export statements inside it to override default values.

### Setup

1. Clone the Repo:

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
```

2. Change to the project directory:

```bash
cd edge-ai-libraries/microservices/document-ingestion/vdms
```

3. Set a username and password to be used as auth credentials to access MINIO Server.

```bash
export MINIO_ROOT_USER="your_minio_user_name"
export MINIO_ROOT_PASSWORD="your_minio_password"
```

4. **Optional step:** Edit the `setup.sh` script to set other environment variables if required.

5. Verify the configuration.

```bash
source ./setup.sh --conf
```

This will output docker compose configs with all the environment variables resolved. You can verify whether they appear as expected.

6. Spin up the services. Please go through different ways to spin up the services.

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

7. Tear down all the services.

```bash
source ./setup.sh --down
```

## Usage

### Access Services

As all the services spin up, we will have DataPrep applications available on `VDMS_DATAPREP_HOST_PORT`. This variable is set in `setup.sh` file. DataPrep service provides us a bunch of API Endpoints to utilize embedding creations and object storage service.

To access and verify VDMS-DataPrep service:

1. Get the IP address of host machine. `setup.sh` script sets `host_ip` variable with the IP address of host machine. You can verify and use this variable, or you can provide a host IP manually.

2. Once you have host IP, access the Data Store API Docs in any web browser on `http://${host_ip}:${VDMS_DATAPREP_HOST_PORT}/docs`.

3. To verify object being stored directly in Minio, you can access the Minio Server Console in any web browser on `http://${host_ip}:${MINIO_CONSOLE_HOST_PORT}`. This will ask for a username and password. Use the Value of `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` from setup.sh as login credentials (see below bash command).

   ```bash
   # Get username and password for Minio User Console
   echo $MINIO_ROOT_USER && echo $MINIO_ROOT_PASSWORD
   ```

4. Go through the VDMS-DataPrep Service API docs to learn how to **upload**, **get**, **download** video files to create/store embeddings.

### Validate Services

We will try to upload a sample video file, verify that embeddings and video files are stored.

1. POST a video file to create video embedding and store in object storage.

```bash
curl -X POST "http://${host_ip}:${VDMS_DATAPREP_HOST_PORT}/v1/dataprep/videos" \
    -H "Content-Type: multipart/form-data" \
    -F "files=@/path/to/sample/video1.mp4" \
    -F "files=@/path/to/sample/video2.mp4" \
    -F "bucket_name=my-bucket"
```

2. Verify whether embeddings were created and videos were uploaded to Minio:

```bash
curl -X GET "http://${host_ip}:${VDMS_DATAPREP_HOST_PORT}/v1/dataprep/videos?bucket_name=my-bucket"
```

3. Download a video file using the video_id from the previous GET response:

```bash
video_id=<video_id_from_get_response>
curl -X GET "http://${host_ip}:${VDMS_DATAPREP_HOST_PORT}/v1/dataprep/videos/download?video_id=${video_id}&bucket_name=my-bucket" -o downloaded_video.mp4
```

#### Minio Console UI

You can also access **Minio Console UI** to verify the bucket creation and video uploads by heading to `http://${host_ip}:{MINIO_CONSOLE_HOST_PORT}` in your browser. Use the Value of `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` as login credentials for Console UI. Videos are uploaded by default in **vdms-bucket-test** bucket unless you specify a different bucket_name in your API requests.
