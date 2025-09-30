# Get Started

The **VDMS based Data Preparation microservice** enables creating and storing of embeddings for text and video files in the VMDS vectorDB. The input video files are stored in the MinIO object storage. This section provides step-by-step instructions to:

- Set up the microservice using a pre-built Docker image for quick deployment.
- Run predefined tasks to explore its functionality.
- Learn how to modify basic configurations to suit specific requirements.

## Configuration and Setup

We will be running our application in docker containers. Configuration step involves setting various environment variables, which are prerequisites for spinning up the application container along with its dependencies. Dependencies are other applications/microservices which also run in docker containers. **For proper functioning of all these application containers, proper setup of environment variables is crucial.**

For end-to-end VDMS-DataPrep application setup, **three** application containers for following services will be spun-up:

- **vdms-dataprep:** This service contains **DataPrep API Server** application.
- **vdms-vector-db:** This service runs **VDMS Vector DB**. This is backend vector DB used by DataPrep API Server.
- **Minio Server:** This service runs Minio Server, the backend Object storage service used directly by the VDMS-DataPrep service.

These **three** services are part of `docker/compose.yaml` file. All these services would be requiring their own set of environment variables to be setup.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./system-requirements.md).
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Environment Variables

Following environment variables are required for setting up the application. **The setup script `setup.sh` takes care most of these. Here, we present them mostly for informational purpose, for the cases where you want to override these for any reason. You can safely skip this section and move to next.**

- **PROJECT_NAME:** Helps provide a common docker compose project name and create a common container prefix for all services involved.
- **COVERAGE_REQ:** Helps to set the test coverage requirement criteria. If coverage is less than this criteria, `final-dev` image will fail to build.
- **PROJ_TEST_DIR:** The directory where all tests reside. This is used while running scripts to run tests.
- **REGISTRY:** This is container registry name. To be able to push an image to remote container registry, image name should contain the registry URL as well. Hence, value of this variable is used as prefix to the image name in docker compose file. Its value is set by concatenating the value of `REGISTRY_URL` environment variable with `PROJECT_NAME`. If `REGISTRY_URL` is not set, only the value of `PROJECT_NAME` is used and resulting image name does not contain any registry URL. If `PROJECT_NAME` is also not set, only the application name is used as image name. We must set `REGISTRY_URL`, if we want to push images to container registry.

### MinIO Related variables
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

### VDMS Vector DB and VDMS-DataPrep Related variables:
- **VDMS_DATAPREP_HOST_PORT:** Port on host machine where we want to access VDMS-DataPrep Service outside container.
- **VDMS_VDB_HOST_PORT:** Port on host machine where we want to access VDMS Vector DB Service outside container.
- **VDMS_VDB_PORT:** Port on which VDMS Vector DB service runs inside container.
- **VDMS_VDB_HOST:** Host name for VDMS Vector DB service. This is used by other application containers for communication.
- **INDEX_NAME:** Name of the collection used to store embeddings in VDMS Vector DB in prod setup.

### How to set environment variables

The setup script in root of project `setup.sh` sets default values for most of the required environment variables once we run it. For values like `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD`, we export following env vars on our shell before running the script.

```bash
export MINIO_ROOT_USER="minio-user-or-s3-access-token"
export MINIO_ROOT_PASSWORD="minio-password-or-s3-secret"
```
For all other variables, you can edit the `setup.sh` file in project root and update any export statements inside it to override default values.

## Quick Start with Docker

The user has an option to either [build the docker images](./how-to-build-from-source.md#steps-to-build) or use prebuilt images as documented below.

_To be documented_

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

## Runs Tests

We can run unit tests and generate coverage by running following command in the application's directory :

```bash
# Switch to application directory (assuming you are in cloned repo's root dir)
cd microservices/visual-data-preparation-for-retrieval/vdms

poetry lock --no-update
poetry install --with cpu,dev

# Run tests and generate coverage report
source setup.sh test
```

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

* [Overview](Overview.md)
* [Architecture Overview](./overview-architecture.md)
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)
