host_ip=$(hostname -I | awk '{print $1}')
HOST_IP=$(hostname -I | awk '{print $1}')
USER_GROUP_ID=$(id -g)
VIDEO_GROUP_ID=$(getent group video | awk -F: '{printf "%s\n", $3}')
RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')
export host_ip
export HOST_IP
export USER_GROUP_ID
export VIDEO_GROUP_ID
export RENDER_GROUP_ID

# Append the value of the public IP address to the no_proxy list 
export no_proxy="localhost, 127.0.0.1, ::1" 
export http_proxy=${http_proxy}
export https_proxy=${https_proxy}

export MILVUS_HOST=${host_ip}
export MILVUS_PORT=19530

# huggingface mirror 
export HF_ENDPOINT=https://hf-mirror.com

export DEVICE="GPU.1"
export MODEL_DIR="$HOME/models"
# export LOCAL_EMBED_MODEL_ID="CLIP-ViT-H-14"

export RETRIEVER_SERVICE_PORT=7770

if [[ -z "$LOCAL_EMBED_MODEL_ID" ]]; then
    echo "Warning: LOCAL_EMBED_MODEL_ID is not defined."
    read -p "Please enter the LOCAL_EMBED_MODEL_ID: " user_model_name
    if [[ -n "$user_model_name" ]]; then
        echo "Using provided model name: $user_model_name"
        export LOCAL_EMBED_MODEL_ID="$user_model_name"
    else
        echo "Error: No model name provided. Exiting."
        exit 1
    fi
fi