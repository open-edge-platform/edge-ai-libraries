#!/bin/bash

#Volume mount paths
export model_cache_path=~/.cache/huggingface
export SSL_CERTIFICATES_PATH=/etc/ssl/certs
export CA_CERTIFICATES_PATH=/opt/share/ca-certificates
export VOLUME_OVMS=${PWD}/ovms

# Setup the PG Vector DB Connection configuration
export PGVECTOR_HOST=pgvector_db
export PGVECTOR_PORT=5432
export PGVECTOR_USER=langchain
export PGVECTOR_PASSWORD=langchain
export PGVECTOR_DBNAME=langchain

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
export PG_CONNECTION_STRING="postgresql+psycopg://$PGVECTOR_USER:$CONVERTED_PGVECTOR_PASSWORD@$PGVECTOR_HOST:$PGVECTOR_PORT/$PGVECTOR_DBNAME"
export INDEX_NAME=intel-rag

#Embedding service required configurations
export EMBEDDING_ENDPOINT_URL=http://tei-embedding-service

# UI ENV variables
export MAX_TOKENS=1024
export APP_ENDPOINT_URL=/v1/chatqna
export APP_DATA_PREP_URL=/v1/dataprep

# Required environment variables for the ChatQnA backend
export CHUNK_SIZE=1500
export CHUNK_OVERLAP=200
export FETCH_K=10
export BATCH_SIZE=32
export SEED=42

# Env variables for DataStore
export DATASTORE_HOST_PORT=8200
export DATASTORE_ENDPOINT_URL=http://data-store:8000

# Minio Server configuration variables
export MINIO_HOST=minio-server
export MINIO_API_PORT=9000
export MINIO_API_HOST_PORT=9999
export MINIO_CONSOLE_PORT=9001
export MINIO_CONSOLE_HOST_PORT=9990
export MINIO_MOUNT_PATH=/opt/share/mnt/miniodata
export MINIO_ROOT_USER=${MINIO_USER:-dummy_user}
export MINIO_ROOT_PASSWORD=${MINIO_PASSWD:-dummy_321}


# Model Download Service Configuration (configurable host/port)
export MODEL_DOWNLOAD_BASE_URL="http://${MODEL_DOWNLOAD_HOST}:${MODEL_DOWNLOAD_PORT}/api/v1/"
export MODEL_DOWNLOAD_API_URL="${MODEL_DOWNLOAD_BASE_URL}models/download"

# Setup no_proxy
export no_proxy=${no_proxy},minio-server,data-store,vllm-service,text-generation,tei-embedding-service,ovms-service,reranker,openvino-embedding,model-download,${MODEL_DOWNLOAD_HOST},pgvector_db

# ReRanker Config
export RERANKER_ENDPOINT=http://reranker/rerank

# OpenTelemetry and OpenLit Configurations 
export OTLP_SERVICE_NAME=chatqna
export OTLP_SERVICE_ENV=chatqna
export OTEL_SERVICE_VERSION=1.0.0
if [[ -n "$OTLP_ENDPOINT" ]]; then
  export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
fi


# VLLM
export TENSOR_PARALLEL_SIZE=1
export KVCACHE_SPACE=50
#export VOLUME_VLLM=${PWD}/data

# OVMS
export MODEL_DIRECTORY_NAME=$(basename $LLM_MODEL)
export WEIGHT_FORMAT=int8

#TGI
#export VOLUME=$PWD/data

if [[ -n "$REGISTRY" && -n "$TAG" ]]; then
  export BE_IMAGE_NAME="${REGISTRY}chatqna:${TAG}"
else
  export BE_IMAGE_NAME="chatqna:latest"
fi

if [[ -n "$REGISTRY" && -n "$TAG" ]]; then
  export FE_IMAGE_NAME="${REGISTRY:-}chatqna-ui:${TAG:-latest}"
else
  export FE_IMAGE_NAME="chatqna-ui:latest"
fi

#GPU Configuration
# Check if render device exist
if compgen -G "/dev/dri/render*" > /dev/null; then
    echo "RENDER device exist. Getting the GID..."
    export RENDER_DEVICE_GID=$(stat -c "%g" /dev/dri/render* | head -n 1)

fi


############################################
# OVMS model downloader
############################################
download_ovms_model() {
    local MODEL_NAME=$1
    local MODEL_TYPE=$2   # llm | embeddings | rerank

    echo "Downloading $MODEL_TYPE model '$MODEL_NAME' via model-download..."

    mkdir -p temp_models ovms/models

    # Submit download request
    local POST_RESPONSE
    POST_RESPONSE=$(
        curl -s -X POST "${MODEL_DOWNLOAD_API_URL}?download_path=temp_models" \
            -H "Content-Type: application/json" \
            -d "{
                \"models\": [
                    {
                        \"name\": \"${MODEL_NAME}\",
                        \"hub\": \"openvino\",
                        \"type\": \"${MODEL_TYPE}\",
                        \"is_ovms\": true,
                        \"config\": {
                            \"precision\": \"${WEIGHT_FORMAT}\",
                            \"device\": \"${DEVICE}\",
                            \"cache_size\": \"${OVMS_CACHE_SIZE}\"
                        }
                    }
                ]
            }"
    )

    echo "Job submission response: $POST_RESPONSE"

    # jq is mandatory
    if ! command -v jq >/dev/null 2>&1; then
        echo "❌ jq is required but not installed."
        return 1
    fi

    # Extract job IDs
    local JOB_IDS
    mapfile -t JOB_IDS < <(echo "$POST_RESPONSE" | jq -r '.job_ids[]')

    if [[ ${#JOB_IDS[@]} -eq 0 ]]; then
        echo "❌ No job_ids returned by model-download API."
        return 1
    fi

    echo "Jobs submitted: ${JOB_IDS[*]}"

    local MAX_ATTEMPTS=60
    local SLEEP_SECS=5
    local attempt=1

    declare -A job_done
    declare -A job_conversion_path

    # Poll all jobs in parallel
    while (( attempt <= MAX_ATTEMPTS )); do
        local all_done=1

        for job_id in "${JOB_IDS[@]}"; do
            # Skip already finished jobs
            if [[ "${job_done[$job_id]}" == "1" ]]; then
                continue
            fi

            local JOB_URL="${MODEL_DOWNLOAD_BASE_URL%/}/jobs/${job_id}"
            local JOB_RESPONSE
            JOB_RESPONSE=$(curl -s "$JOB_URL")

            local status conversion_path
            status=$(echo "$JOB_RESPONSE" | jq -r '.status')
            conversion_path=$(echo "$JOB_RESPONSE" | jq -r '.result.conversion_path // empty')

            echo "Job $job_id → $status"

            if [[ "$status" == "completed" || "$status" == "failed" ]]; then
                job_done[$job_id]=1
                job_conversion_path[$job_id]="$conversion_path"
            else
                all_done=0
            fi
        done

        if (( all_done )); then
            break
        fi

        echo "Waiting for jobs to finish (attempt $attempt/$MAX_ATTEMPTS)..."
        sleep "$SLEEP_SECS"
        ((attempt++))
    done

    # Timeout handling
    if (( attempt > MAX_ATTEMPTS )); then
        echo "❌ Timed out waiting for model download jobs."
        return 1
    fi

    # Target directory mirrors model name (Intel/neural-chat-7b-v3-3)
    local TARGET_DIR="${VOLUME_OVMS}/models/"
    mkdir -p "$TARGET_DIR"

    echo "Copying model artifacts to $TARGET_DIR..."

    # Copy model files from each job's conversion_path
    for job_id in "${JOB_IDS[@]}"; do
        local conversion_path="${job_conversion_path[$job_id]}"

        if [[ ! -d "$conversion_path" ]]; then
            echo "❌ Expected model directory not found: $conversion_path"
            return 1
        fi

        echo "Copying artifacts from job $job_id → $conversion_path"
        local SRC_MODEL_DIR="$conversion_path"
        if [[ ! -d "$SRC_MODEL_DIR" ]]; then
            echo "❌ Expected model directory not found: $SRC_MODEL_DIR"
            return 1
        fi

        echo "Copying $SRC_MODEL_DIR to $TARGET_DIR"
        cp -r "$SRC_MODEL_DIR/"* "$TARGET_DIR"
    done

    echo "All model artifacts copied to $TARGET_DIR."
}


setup_inference() {
        local service=$1
        case "${service,,}" in
                vllm)
                        echo "Error: vLLM support is deprecated and no longer available."
                        echo "Please use OVMS as the Model Server instead."
                        echo "Usage: setup.sh llm=OVMS embed=<Embedding Service>"
                        #exit 1
                        ;;
                ovms)
                        export ENDPOINT_URL=http://ovms-service/v3
                        #Target Device
                        if [[ "$DEVICE" == "GPU" ]]; then
                                export OVMS_CACHE_SIZE=2
                                export COMPOSE_PROFILES=GPU-OVMS
                        elif [[ "$DEVICE" == "CPU" ]]; then
                                export OVMS_CACHE_SIZE=10
                                export COMPOSE_PROFILES=OVMS

                        fi
                        
                        download_ovms_model "$LLM_MODEL" "llm"
                        ;;
                tgi)
                        echo "Error: TGI support is deprecated and no longer available."
                        echo "Please use OVMS as the Model Server instead."
                        echo "Usage: setup.sh llm=OVMS embed=<Embedding Service>"
                        #exit 1
                        ;;
                *)
                        echo "Invalid Model Server option: $service"
                        ;;
        esac
}

setup_embedding() {
        local service=$1
        case "${service,,}" in
                tei)
                        export EMBEDDING_ENDPOINT_URL=http://tei-embedding-service
                        export COMPOSE_PROFILES=$COMPOSE_PROFILES,TEI
                        ;;
                ovms)
                        export EMBEDDING_ENDPOINT_URL=http://ovms-service/v3
                        #Target Device
                        if [[ "$DEVICE" == "GPU" ]]; then
                                export COMPOSE_PROFILES=$COMPOSE_PROFILES,GPU-OVMS
                        elif [[ "$DEVICE" == "CPU" ]]; then
                                export COMPOSE_PROFILES=$COMPOSE_PROFILES,OVMS

                        fi
                        
                        download_ovms_model "$EMBEDDING_MODEL_NAME" "embeddings"
                        ;;
                *)
                        echo "Invalid Embedding Service option: $service"
                        ;;
        esac
}

if [[ -n "$1" && -n "$2" ]]; then
        for arg in "$@"; do
                case $arg in
                        llm=*)
                                LLM_SERVICE="${arg#*=}"
                                ;;
                        embed=*)
                                EMBED_SERVICE="${arg#*=}"
                                ;;
                        *)
                                echo "Invalid argument: $arg"
                                echo "Usage: setup.sh llm=<Model Server> embed=<Embedding Service>"
                                echo "Model Server options: OVMS"
                                echo "Embedding Service options: TEI or OVMS"
                                echo ""
                                echo "Note: vLLM and TGI are deprecated and no longer supported."
                                ;;
                esac
        done
        setup_inference "$LLM_SERVICE"
        setup_embedding "$EMBED_SERVICE"
else
        echo "Please provide the service to start: specify Model server and Embedding service"
        echo "Usage: setup.sh llm=<Model Server> embed=<Embedding Service>"
        echo "Model Server options: OVMS"
        echo "Embedding Service options: TEI or OVMS"
        echo ""
        echo "Note: vLLM and TGI are deprecated and no longer supported."
fi
