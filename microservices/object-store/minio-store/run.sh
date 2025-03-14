#!/bin/bash
# Sets required environment variable to run the DataStore microservice.
# Change these values as required.

export PROJECT_NAME=object-store

# Location of DataStore Source code. Used to mount code to DataStore Dev Container.
export DATASTORE_CODE_DIR=..

# Service name for minio-server which will be used for communication with minio-server
export MINIO_HOST="minio-server"

# Port on which API service runs inside container
export MINIO_API_PORT=9000

# Port on which we want to access API service outside container i.e. on host.
export MINIO_API_HOST_PORT=9991

# Port on which Minio server console would be running inside container.
export MINIO_CONSOLE_PORT=9001

# Port on which we want to access Minio Console outside container i.e. on host.
export MINIO_CONSOLE_HOST_PORT=9992

# Mount point for Minio objects storage. This helps persist objects stored on minio server.
export MINIO_MOUNT_PATH="/mnt/miniodata"

# Port on host where we want to access DataStore Service outside container
export DATASTORE_HOST_PORT=8881

export host_ip=$(hostname -I | cut -d ' ' -f 1)

# Override the following variables by exporting the MINIO_USER and MINIO_PASSWD
# variables from shell.

# Username for MINIO Server
export MINIO_ROOT_USER=${MINIO_USER:-dummy_user}
# Password for Minio Server
export MINIO_ROOT_PASSWORD=${MINIO_PASSWD:-dummy_321}

# Based on provided CONTAINER_REGISTRY_URL, set registry name which is prefixed to application's name/tag
# to form complete image name. Add a trailing slash to container registry URL if not present.
if ! [ -z "$CONTAINER_REGISTRY_URL" ] && ! [ "${CONTAINER_REGISTRY_URL: -1}" = "/" ]; then
    REGISTRY="${CONTAINER_REGISTRY_URL}/"
else
    REGISTRY=$CONTAINER_REGISTRY_URL
fi
export IMAGE_REGISTRY="${REGISTRY}${PROJECT_NAME}/"

# Setting no_proxy to add service names connection to which does not require proxy
if ! [[ $no_proxy == *"${MINIO_HOST}"* ]]; then
    export no_proxy="${no_proxy},${MINIO_HOST}"
fi

# Build and spinup/teardown container

if [ "$1" = "--nosetup" ] && [ "$#" -eq 1 ]; then
    echo "All environment variables set successfully!"
    return
elif [ "$1" = "--conf" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml config
elif [ "$1" = "--dev" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml -f docker/compose-dev.yaml up -d --build
    if [ $? = 0 ]; then
        docker ps | grep "${PROJECT_NAME}"
        echo "Dev environment is up!"
    fi
elif [ "$1" = "--down" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml down
    if [ $? = 0 ]; then
        echo "All services down!"
    fi
elif [ "$1" = "--build" ] && [ "$#" -eq 1 ]; then
    tag=${BUILD_TAG:-intel/object-store:1.1}
    docker build -t $tag -f docker/Dockerfile .
    if [ $? = 0 ]; then
        docker images | grep $tag
        echo "Image ${tag} was successfully built."
    fi
elif [ "$1" = "--build-dev" ] && [ "$#" -eq 1 ]; then
    tag=${BUILD_TAG:-intel/object-store:1.1-dev}
    docker build -t $tag -f docker/Dockerfile --target dev .
    if [ $? = 0 ]; then
        docker images | grep $tag
        echo "Dev Image ${tag} was successfully built."
    fi
elif [ "$1" = "--dev" ] && [ "$2" = "--nd" ] && [ "$#" -eq 2 ]; then
    docker compose -f docker/compose.yaml -f docker/compose-dev.yaml up --build
elif [ "$1" = "--nd" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml up --build
elif [ "$#" -eq 0 ]; then
    docker compose -f docker/compose.yaml up -d --build
    if [ $? = 0 ]; then
        docker ps | grep "${PROJECT_NAME}"
        echo "Prod environment is up!"
    fi
else
    echo "Invalid argument!"
fi
