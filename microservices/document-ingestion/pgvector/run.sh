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

# Export version with YYYYMMDD
export DEFAULT_VERSION=$(date +%Y%m%d)

# Based on provided CONTAINER_REGISTRY_URL, set registry name which is prefixed to application's name/tag
# to form complete image name. Add a trailing slash to container registry URL if not present.
if ! [ -z "$CONTAINER_REGISTRY_URL" ] && ! [ "${CONTAINER_REGISTRY_URL: -1}" = "/" ]; then
    REGISTRY="${CONTAINER_REGISTRY_URL}/"
else
    REGISTRY=$CONTAINER_REGISTRY_URL
fi
export IMAGE_REGISTRY="${REGISTRY}${PROJECT_NAME}/"

# Handle the special characters in password for connection string
convert_pg_password() {
    local password="$1"
    password="${password//'%'/'%25'}"
    password="${password//':'/'%3A'}"
    password="${password//'@'/'%40'}"
    password="${password//'/'/'%2F'}"
    password="${password//'+'/'%2B'}"
    password="${password//' '/'%20'}"
    password="${password//'?'/'%3F'}"
    password="${password//'#'/'%23'}"
    password="${password//'['/'%5B'}"
    password="${password//']'/'%5D'}"
    password="${password//'&'/'%26'}"
    password="${password//'='/'%3D'}"
    password="${password//';'/'%3B'}"
    password="${password//'!'/'%21'}"
    password="${password//'$'/'%24'}"
    password="${password//'*'/'%2A'}"
    password="${password//'^'/'%5E'}"
    password="${password//'('/'%28'}"
    password="${password//')'/'%29'}"
    password="${password//'"'/'%22'}"
    password="${password//"'"/'%27'}"
    password="${password//'`'/'%60'}"
    password="${password//'|'/'%7C'}"
    password="${password//'\\'/'%5C'}"
    password="${password//'<'/'%3C'}"
    password="${password//'>'/'%3E'}"
    password="${password//','/'%2C'}"
    password="${password//'{'/'%7B'}"
    password="${password//'}'/'%7D'}"
    echo "$password"
}
CONVERTED_PGVECTOR_PASSWORD=$(convert_pg_password "$PGVECTOR_PASSWORD")

# ---------------------------------------------------------------------------------------

# This is setup based on previously set PGDB values
export PG_CONNECTION_STRING="postgresql+psycopg://$PGVECTOR_USER:$CONVERTED_PGVECTOR_PASSWORD@$PGVECTOR_HOST:5432/$PGVECTOR_DBNAME"
#echo "Connection string is: $PG_CONNECTION_STRING"

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
    docker compose -f docker/compose.yaml config

# Stop and remove containers and networks (basic down)
elif [ "$1" = "--down" ] && [ "$#" -eq 1 ]; then
    echo "Stopping and removing containers and networks..."
    docker compose -f docker/compose.yaml down
    echo "Services stopped. Images and volumes preserved."

# Stop and remove containers, networks, and volumes (keep images)  
elif [ "$1" = "--down" ] && [ "$2" = "--volumes" ] && [ "$#" -eq 2 ]; then
    echo "Stopping and removing containers, networks, and volumes..."
    docker compose -f docker/compose.yaml down --volumes
    echo "Services stopped. Images preserved, volumes removed."

# Stop dev environment services
elif [ "$1" = "--down" ] && [ "$2" = "--dev" ] && [ "$#" -eq 2 ]; then
    echo "Stopping and removing dev environment containers and networks..."
    docker compose -f docker/compose.yaml -f docker/compose-dev.yaml down
    echo "Dev environment services stopped. Images and volumes preserved."

# Stop dev environment services with volumes
elif [ "$1" = "--down" ] && [ "$2" = "--dev" ] && [ "$3" = "--volumes" ] && [ "$#" -eq 3 ]; then
    echo "Stopping and removing dev environment containers, networks, and volumes..."
    docker compose -f docker/compose.yaml -f docker/compose-dev.yaml down --volumes
    echo "Dev environment services stopped. Images preserved, volumes removed."

# Build dataprep image using DEFAULT_VERSION as tag if not provided
elif ([ "$1" = "--build" ] && [ "$2" = "dataprep" ]) && ([ "$#" -eq 2 ] || [ "$#" -eq 3 ]); then
    tag=${3:-intel/document-ingestion:$DEFAULT_VERSION}
    docker build -t $tag \
       --label "project=${PROJECT_NAME}" \
       --label "service=dataprep" \
       --label "build-script=run.sh" \
       -f docker/Dockerfile .
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

# Remove all project-related Docker images
elif [ "$1" = "--clean" ] && [ "$#" -eq 1 ]; then
    echo "Removing all ${PROJECT_NAME} related Docker images..."
    
    # Use docker compose to remove all images from services
    docker compose -f docker/compose.yaml down --rmi all 2>/dev/null || true
    
    # Also remove dev environment images if exists
    if [ -f "docker/compose-dev.yaml" ]; then
        docker compose -f docker/compose.yaml -f docker/compose-dev.yaml down --rmi all 2>/dev/null || true
    fi
    
    # Remove any remaining labeled images
    docker images --filter "label=project=${PROJECT_NAME}" -q | xargs -r docker rmi -f 2>/dev/null || true

    echo "Cleanup completed!"

# Remove specific service image using labels
elif [ "$1" = "--clean" ] && [ "$2" = "dataprep" ] && [ "$#" -eq 2 ]; then
    echo "Removing dataprep service images..."
    docker images --filter "label=project=${PROJECT_NAME}" --filter "label=service=dataprep" -q | xargs -r docker rmi -f
    # Fallback: also remove legacy images that may not have labels
    docker images | grep "intel/document-ingestion" | awk '{print $3}' | xargs -r docker rmi -f 2>/dev/null || true
    echo "Dataprep images removed!"

# Complete cleanup - stop containers, remove containers, networks, volumes, and images
elif [ "$1" = "--purge" ] && [ "$#" -eq 1 ]; then
    echo "Performing complete cleanup..."
    
    # Stop everything and remove all resources including images
    docker compose -f docker/compose.yaml down --rmi all --volumes --remove-orphans 2>/dev/null || true
    
    if [ -f "docker/compose-dev.yaml" ]; then
        docker compose -f docker/compose.yaml -f docker/compose-dev.yaml down --rmi all --volumes --remove-orphans 2>/dev/null || true
    fi
    
    # Clean any remaining labeled images
    docker images --filter "label=project=${PROJECT_NAME}" -q | xargs -r docker rmi -f 2>/dev/null || true
        
    echo "Complete cleanup finished!"

else
    echo "Invalid arguments!"
    echo "Usage: $0 [OPTION]"
    echo "Options:"
    echo "  (no args)       Spin up all services in daemon mode"
    echo "  --nosetup       Set environment variables only"
    echo "  --conf          Verify docker compose configuration"
    echo "  --down          Stop and remove containers and networks (keep images and volumes)"
    echo "  --down --volumes Stop and remove containers, networks, and volumes (keep images)"
    echo "  --down --dev    Stop and remove dev environment containers and networks (keep images and volumes)"
    echo "  --down --dev --volumes Stop and remove dev environment containers, networks, and volumes (keep images)"
    echo "  --build         Build images (requires service name)"
    echo "  --build dataprep [tag]  Build dataprep image with optional tag"
    echo "  --dev           Spin up services with dev environment in daemon mode"
    echo "  --dev --nd      Spin up services with dev environment in non-daemon mode"
    echo "  --nd            Spin up services in non-daemon mode"
    echo "  --clean         Remove all project-related Docker images"
    echo "  --clean dataprep Remove dataprep service images"
    echo "  --purge         Complete cleanup (containers, images, volumes, networks)"
fi
