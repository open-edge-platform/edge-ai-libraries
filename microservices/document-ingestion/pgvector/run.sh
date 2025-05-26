#!/bin/bash
# Sets required environment variable to run the Several microservices in docker compose.
# Change these values as required.

export PROJECT_NAME=document-ingestion

# MinIO server various hosts, ports, mounts and credentials
export MINIO_HOST=minio-server
export MINIO_API_PORT=9000
export MINIO_API_HOST_PORT=9999
export MINIO_CONSOLE_PORT=9001
export MINIO_CONSOLE_HOST_PORT=9990
export MINIO_MOUNT_PATH=/mnt/miniodata

# Host port for dataprep. Service will be available on this port on host machine.
export DATAPREP_HOST_PORT=8000

# TEI Embedding service vars
export TEI_HOST=tei-embedding-service
export TEI_HOST_PORT=6060
export TEI_ENDPOINT_URL="http://$TEI_HOST"
export EMBEDDING_MODEL_NAME=BAAI/bge-large-en-v1.5

# PGVector DB Vars
export PGVECTOR_HOST=pgvector-vector-db

export host_ip=$(hostname -I | cut -d ' ' -f 1)

# ----------------------------------------------------------------------------------------
# Following part contains variables that need to be set from shell. If not set, their default
# values would be used.
# ----------------------------------------------------------------------------------------
# To override value of IMAGE_REGISTRY, export CONTAINER_REGISTRY_URL from shell.

export MINIO_ACCESS_KEY=$MINIO_USER
export MINIO_SECRET_KEY=$MINIO_PASSWD
export MINIO_ROOT_USER=$MINIO_USER
export MINIO_ROOT_PASSWORD=$MINIO_PASSWD
export PGVECTOR_USER=$PGDB_USER
export PGVECTOR_PASSWORD=$PGDB_PASSWD
export PGVECTOR_DBNAME=$PGDB_NAME
export INDEX_NAME=$PGDB_INDEX
export BATCH_SIZE=32
export CHUNK_SIZE=1500
export CHUNK_OVERLAP=200

# Based on provided CONTAINER_REGISTRY_URL, set registry name which is prefixed to application's name/tag
# to form complete image name. Add a trailing slash to container registry URL if not present.
if ! [ -z "$CONTAINER_REGISTRY_URL" ] && ! [ "${CONTAINER_REGISTRY_URL: -1}" = "/" ]; then
    REGISTRY="${CONTAINER_REGISTRY_URL}/"
else
    REGISTRY=$CONTAINER_REGISTRY_URL
fi
export IMAGE_REGISTRY="${REGISTRY}${PROJECT_NAME}/"


# ---------------------------------------------------------------------------------------

# This is setup based on previously set PGDB values
export PG_CONNECTION_STRING="postgresql+psycopg://$PGVECTOR_USER:$PGVECTOR_PASSWORD@$PGVECTOR_HOST:5432/$PGVECTOR_DBNAME"

# Updating no_proxy to add required service names. Containers need to bypass proxy while connecting to these services.
if ! [[ $no_proxy == *"${PGVECTOR_HOST}"* ]]; then
    export no_proxy="$no_proxy,$PGVECTOR_HOST"
fi
if ! [[ $no_proxy == *"${TEI_HOST}"* ]]; then
    export no_proxy="$no_proxy,$TEI_HOST"
fi
if ! [[ $no_proxy == *"${MINIO_HOST}"* ]]; then
    export no_proxy="$no_proxy,$MINIO_HOST"
fi

# Manage, spin-up, teardown containers required for DataPrep Service

# Only set env vars and do no docker setup
if [ "$1" = "--nosetup" ] && [ "$#" -eq 1 ]; then
    echo "All environment variables set successfully!"
    return

# Verify the configuration of docker compose
elif [ "$1" = "--conf" ] && [ "$#" -eq 1 ]; then
    docker compose config

# tear down all services
elif [ "$1" = "--down" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml down

# Build images
elif [ "$1" = "--build" ] && [ "$#" -eq 1 ]; then
    echo "Please provide the service name to build: dataprep"

# Build dataprep image
elif ([ "$1" = "--build" ] && [ "$2" = "dataprep" ]) && ([ "$#" -eq 2 ] || [ "$#" -eq 3 ]); then
    tag=${3:-intel/document-ingestion:1.1}
    docker build -t $tag -f docker/Dockerfile .
    if [ $? = 0 ]; then
        docker images | grep $tag
        echo "Image ${tag} was successfully built."
    fi

# Spin up all services with dev environment in daemon mode
elif [ "$1" = "--dev" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml -f docker/compose-dev.yaml up -d --build
    if [ $? = 0 ]; then
        docker ps | grep "${PROJECT_NAME}"
        echo "All services with dev environment for DataPrep is up!"
    fi

# Spin up all services with dev environment for DataPrep in non-daemon mode
elif [ "$1" = "--dev" ] && [ "$2" = "--nd" ] && [ "$#" -eq 2 ]; then
    docker compose -f docker/compose.yaml -f docker/compose-dev.yaml up --build

# Spin up all services with prod environment in non-daemon mode
elif [ "$1" = "--nd" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml up --build

# Spin up all services with prod environment in daemon mode
elif [ "$#" -eq 0 ]; then
    docker compose -f docker/compose.yaml up -d --build
    if [ $? = 0 ]; then
        docker ps | grep "${PROJECT_NAME}"
        echo "All services are up with prod environment!"
    fi
else
    echo "Invalid arguments!"
fi
