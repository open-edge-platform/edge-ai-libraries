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
export no_proxy="localhost,127.0.0.1,::1,${host_ip}" 
export no_proxy_env=${no_proxy},$HOST_IP
export http_proxy=${http_proxy}
export https_proxy=${https_proxy}

export MILVUS_HOST=${host_ip}
export MILVUS_PORT=19530

# huggingface mirror 
export HF_ENDPOINT=https://hf-mirror.com

export DEVICE="GPU.1"
export HOST_DATA_PATH="$HOME/data"

export DEFAULT_START_OFFSET_SEC=0
export DEFAULT_CLIP_DURATION=-1  # -1 means take the video till end
export DEFAULT_NUM_FRAMES=64

# OpenVINO configuration
export EMBEDDING_USE_OV=false
export EMBEDDING_DEVICE=${EMBEDDING_DEVICE:-CPU}
# If EMBEDDING_DEVICE is GPU, set EMBEDDING_USE_OV to true
if [ "$EMBEDDING_DEVICE" = "GPU" ]; then
    export EMBEDDING_USE_OV=true
fi

export DATAPREP_SERVICE_PORT=9990
export EMBEDDING_SERVER_PORT=9777
export USE_ONLY_TEXT_EMBEDDINGS=false  # Setup multimodal embedding models, not just text models.
export EMBEDDING_BASE_URL="http://${host_ip}:${EMBEDDING_SERVER_PORT}"
export VCLIP_MODEL="openai/clip-vit-base-patch32"

docker volume create ov-models

if [ -z "$VCLIP_MODEL" ] || [ "$VCLIP_MODEL" != "openai/clip-vit-base-patch32" ]; then
    echo -e "ERROR: VCLIP_MODEL is either not set or is set to an invalid value in your shell environment."
    return
fi

