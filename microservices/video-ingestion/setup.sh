#!/bin/bash

# Get Host IP Address
host_ip=$(ip route get 1 | awk '{print $7}')

export TAG=${TAG:-latest}
export MINIO_SERVICE=minio
export RABBITMQ_SERVICE=rabbitmq

# If REGISTRY_URL is set, ensure it ends with a trailing slash
# Using parameter expansion to conditionally append '/' if not already present
[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"

# If PROJECT_NAME is set, ensure it ends with a trailing slash
[[ -n "$PROJECT_NAME" ]] && PROJECT_NAME="${PROJECT_NAME%/}/"

export REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"

export MINIO_SERVER=${MINIO_SERVICE}:9000

export EVAM_HOST_PORT=8090
export EVAM_PORT=8080
export MINIO_HOST_PORT=9000
export MINIO_CONSOLE_HOST_PORT=9001
export AMQP_HOST_PORT=5672
export RABBITMQ_UI_HOST_PORT=15672
export MQTT_HOST_PORT=1883

# Setting no_proxy to add service names connection to which does not require proxy
if ! [[ $no_proxy == *"${MINIO_SERVICE}"* ]]; then
    export no_proxy="$no_proxy,$MINIO_SERVICE,$RABBITMQ_SERVICE,$host_ip"
fi

echo "All required environment variables set successfully. \
Please make sure Minio and RabbitMQ credentials are set on your shell before proceeding."
