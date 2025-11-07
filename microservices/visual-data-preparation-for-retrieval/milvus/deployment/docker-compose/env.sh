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
export OV_PERFORMANCE_MODE=${OV_PERFORMANCE_MODE:-LATENCY}
# If EMBEDDING_DEVICE is GPU, set EMBEDDING_USE_OV to true
if [ "$EMBEDDING_DEVICE" = "GPU" ]; then
    export EMBEDDING_USE_OV=true
fi

export DATAPREP_SERVICE_PORT=9990
export EMBEDDING_SERVER_PORT=9777
export USE_ONLY_TEXT_EMBEDDINGS=false  # Setup multimodal embedding models, not just text models.
export EMBEDDING_BASE_URL="http://${host_ip}:${EMBEDDING_SERVER_PORT}"
# export EMBEDDING_MODEL_NAME="CLIP/clip-vit-h-14"

docker volume create ov-models

if [ -z "$EMBEDDING_MODEL_NAME" ]; then
    echo "ERROR: EMBEDDING_MODEL_NAME environment variable is required."
    echo ""
    echo "Please set a model name before sourcing env.sh:"
    echo "  export EMBEDDING_MODEL_NAME=\"your-chosen-model\""
    echo "  source env.sh"
    echo ""
    echo "See multimodal-embedding-servicing in microservices for more details."
    return 1
fi

# Check if EMBEDDING_MODEL_NAME is supported
case "$EMBEDDING_MODEL_NAME" in
    "CLIP/clip-vit-b-16"|"CLIP/clip-vit-l-14"|"CLIP/clip-vit-b-32"|"CLIP/clip-vit-h-14")
        echo "Using CLIP model: $EMBEDDING_MODEL_NAME"
        ;;
    "CN-CLIP/cn-clip-vit-b-16"|"CN-CLIP/cn-clip-vit-l-14"|"CN-CLIP/cn-clip-vit-h-14")
        echo "Using CN-CLIP model: $EMBEDDING_MODEL_NAME (Chinese + English support)"
        ;;
    "SigLIP/siglip-vit-b-16"|"SigLIP/siglip-vit-l-16")
        echo "Using SigLIP model: $EMBEDDING_MODEL_NAME"
        ;;
    "MobileCLIP/mobileclip_s0"|"MobileCLIP/mobileclip_s1"|"MobileCLIP/mobileclip_s2"|"MobileCLIP/mobileclip_b"|"MobileCLIP/mobileclip_blt")
        echo "Using MobileCLIP model: $EMBEDDING_MODEL_NAME"
        ;;
    "Blip2/blip2_feature_extractor"|"Blip2/blip2_transformers"|"Blip2/blip2_transformers_vitL")
        echo "Using BLIP2 model: $EMBEDDING_MODEL_NAME"
        ;;
    *)
        echo -e "WARNING: Model '$EMBEDDING_MODEL_NAME' may not be supported."
        echo -e "See docs/user-guide/supported-models.md for the complete list of supported models."
        ;;
esac