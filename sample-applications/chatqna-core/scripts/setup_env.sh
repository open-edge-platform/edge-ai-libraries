#!/bin/bash

# Get MODEL_CACHE_PATH from user or use default
MODEL_CACHE_PATH=${1:-"/tmp/model_cache/"}

# Check if MODEL_CACHE_PATH is an absolute path
if [[ "$MODEL_CACHE_PATH" != /* ]]; then
    MODEL_CACHE_PATH="$PWD/$MODEL_CACHE_PATH"
    echo "Relative path provided. Using absolute path: $MODEL_CACHE_PATH"
fi

# Check if MODEL_CACHE_PATH exists
if [ -e "$MODEL_CACHE_PATH" ]; then
    # Check if the owner is not root:root, keep it.
    # Else delete and recreate it.
    if [ "$(stat -c '%U:%G' "$MODEL_CACHE_PATH")" != "root:root" ]; then
        echo "$MODEL_CACHE_PATH exists..."
    else
        echo "$MODEL_CACHE_PATH exists and is owned by root:root. Deleting it and recreate..."
        sudo rm -rf "$MODEL_CACHE_PATH"
        mkdir "$MODEL_CACHE_PATH"
    fi
else
    echo "$MODEL_CACHE_PATH does not exist. Creating it..."
    mkdir "$MODEL_CACHE_PATH"
fi

# Export environment variables
export HOST_IP=$(hostname -I | awk '{print $1}')
export HF_ACCESS_TOKEN="${HUGGINGFACEHUB_API_TOKEN}"
export EMBEDDING_MODEL_ID="BAAI/bge-small-en-v1.5"
export LLM_MODEL_ID="Intel/neural-chat-7b-v3-3"
export RERANKER_MODEL_ID="BAAI/bge-reranker-base"
export MODEL_CACHE_PATH="$MODEL_CACHE_PATH"
export APP_BACKEND_URL="http://$HOST_IP:8888"