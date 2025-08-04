#!/bin/bash

#Volume mount paths
export model_cache_path=~/.cache/huggingface
export SSL_CERTIFICATES_PATH=/etc/ssl/certs
export CA_CERTIFICATES_PATH=/opt/share/ca-certificates
export VOLUME_OVMS=${PWD}/ovms_config

# Setup the PG Vector DB Connection configuration
export PGVECTOR_HOST=pgvector_db
export PGVECTOR_PORT=5432
export PGVECTOR_USER=langchain
export PGVECTOR_PASSWORD=langchain
export PGVECTOR_DBNAME=langchain
export PG_CONNECTION_STRING=postgresql+psycopg://$PGVECTOR_USER:$PGVECTOR_PASSWORD@pgvector_db:$PGVECTOR_PORT/$PGVECTOR_DBNAME
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

setup_inference() {
        local service=$1
        case "${service,,}" in
                vllm)
                        export ENDPOINT_URL=http://vllm-service/v1
                        export COMPOSE_PROFILES=VLLM
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
                        cd ./ovms_config
                        python3 export_model.py text_generation --source_model $LLM_MODEL --weight-format $WEIGHT_FORMAT --config_file_path models/config.json --model_repository_path models --target_device $DEVICE --cache_size $OVMS_CACHE_SIZE --overwrite_models
                        cd ..
                        ;;
                tgi)
                        export ENDPOINT_URL=http://text-generation/v1
                        export COMPOSE_PROFILES=TGI
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
                        cd ./ovms_config
                        python3 export_model.py embeddings --source_model $EMBEDDING_MODEL_NAME --weight-format $WEIGHT_FORMAT --config_file_path models/config.json --model_repository_path models --target_device $DEVICE --overwrite_models
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
                                echo "Model Server options: VLLM or TGI or OVMS"
                                echo "Embedding Service options: TEI or OVMS"
                                ;;
                esac
        done
        setup_inference "$LLM_SERVICE"
        setup_embedding "$EMBED_SERVICE"
else
        echo "Please provide the service to start: specify Model server and Embedding service"
        echo "Usage: setup.sh llm=<Model Server> embed=<Embedding Service>"
        echo "Model Server options: VLLM or TGI or OVMS"
        echo "Embedding Service options: TEI or OVMS"
fi
