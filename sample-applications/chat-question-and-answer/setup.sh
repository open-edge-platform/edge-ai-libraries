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

# Setup no_proxy
export no_proxy=${no_proxy},minio-server,data-store,vllm-service,text-generation,tei-embedding-service,ovms-service,reranker,openvino-embedding

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

#Create virtual env and install dependencies
if [[ "${1,,}" == *"llm=ovms"* || "${2,,}" == *"embed=ovms"* ]]; then
        # Check for Python first
        if ! command -v python3 >/dev/null 2>&1; then
                echo "Error: Python 3 is required but not found"
                exit 1
        fi
        
        # Check if we need to create or recreate the venv
        if [ ! -d .venv ] || [ "${REBUILD_VENV:-false}" = "true" ]; then
                # Deactivate if there's an active venv (works in both bash and sh)
                command -v deactivate >/dev/null 2>&1 && deactivate
                # Remove old venv if exists
                [ -d .venv ] && rm -rf .venv
                echo "Creating new virtual environment..."
                python3 -m venv .venv || { echo "Failed to create virtual environment"; exit 1; }
        fi
        
        # Activate the virtual environment - compatible with different shells
        if [ -f .venv/bin/activate ]; then
                . .venv/bin/activate || { echo "Failed to activate virtual environment"; exit 1; }
        else
                echo "Virtual environment activation script not found"; exit 1
        fi
        
        if ! python3 -m pip show openvino >/dev/null 2>&1; then
                echo "Installing OpenVINO and required dependencies..."
                python3 -m pip install -r https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/heads/releases/2025/3/demos/common/export_models/requirements.txt
		python3 -m pip install -U "huggingface_hub[hf_xet]==0.36.0"
        fi
        mkdir -p ./ovms/models
        cd ovms || { echo "Failed to change to ovms directory"; exit 1; }
        if [ -n "$HUGGINGFACEHUB_API_TOKEN" ]; then
                hf auth login --token "$HUGGINGFACEHUB_API_TOKEN"
        fi
        curl -s https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/heads/releases/2025/3/demos/common/export_models/export_model.py -o export_model.py
        echo "OpenVINO and required dependencies installed."
        cd ..
fi

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
                        cd ./ovms
                        python3 export_model.py text_generation --source_model $LLM_MODEL --weight-format $WEIGHT_FORMAT --config_file_path models/config.json --model_repository_path models --target_device $DEVICE --cache_size $OVMS_CACHE_SIZE --overwrite_models
                        cd ..
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
                        cd ./ovms
                        python3 export_model.py embeddings_ov --source_model $EMBEDDING_MODEL_NAME --weight-format $WEIGHT_FORMAT --config_file_path models/config.json --model_repository_path models --target_device $DEVICE --overwrite_models
                        cd ..
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
