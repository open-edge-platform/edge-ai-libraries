#!/bin/bash
set -e  # Exit on error

##############################################################################
# Helper function: create_dir
# Attempts to create a directory; if it fails due to permission issues,
# changes the ownership of the parent directory and then creates the folder.
##############################################################################
create_dir() {
    local dir="$1"
    if ! mkdir -p "$dir" 2>/dev/null; then
        echo "Failed to create '$dir'. It may be owned by root. Attempting to fix ownership..."
        # Change ownership of the parent directory
        sudo chown -R "$(id -un):$(id -gn)" "$(dirname "$dir")" || true
        mkdir -p "$dir"
    fi
    # Ensure the created directory is owned by the current user
    chown -R "$(id -un):$(id -gn)" "$dir" || true
}

##############################################################################
# 0. Check for python3.12-venv (only place we use sudo)
##############################################################################
if ! dpkg -s python3.12-venv &>/dev/null; then
    echo "Package python3.12-venv not installed. Attempting to install..."
    sudo apt update
    sudo apt install -y python3.12-venv
fi

##############################################################################
# 1. Source the .env file to get CASE (or other environment variables).
#    Make sure .env contains a line like: Case="Smart_Tolling"
##############################################################################
if [ ! -f ".env" ]; then
    echo "Error: .env file not found in current directory!"
    exit 1
fi
# shellcheck disable=SC1091
source .env

if [ -z "$Case" ]; then
    echo "Error: 'Case' variable not found in .env!"
    exit 1
fi

echo "Detected Case: $Case"

##############################################################################
# 2. Create/Activate a Python virtual environment to avoid pip system issues
##############################################################################
VENV_DIR="$HOME/ri2-venv"  # or pick another name/path if you wish

if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Creating Python virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "Error: Virtual environment activate script not found at $VENV_DIR/bin/activate"
    exit 1
fi

echo "Activating Python virtual environment..."
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

pip install --upgrade pip

##############################################################################
# 3. Locate and parse the model.txt
##############################################################################
MODEL_TXT="usecase/${Case}/model.txt"
cat "$MODEL_TXT"



if [ ! -f "$MODEL_TXT" ]; then
    echo "Error: $MODEL_TXT not found!"
    deactivate
    exit 1
fi

YOLO_MODEL=""
OMZ_MODELS=()

while read -r model_name model_type; do
    # Skip empty lines or those starting with '#'
    [[ -z "$model_name" || "$model_name" == \#* ]] && continue

    if [ "$model_type" = "yolo" ]; then
        YOLO_MODEL="$model_name"
    elif [ "$model_type" = "omz" ]; then
        OMZ_MODELS+=("$model_name")
    fi
done < "$MODEL_TXT"


echo "Found YOLO model: $YOLO_MODEL"
echo "Found OMZ models: ${OMZ_MODELS[@]}"

##############################################################################
# 4. Process YOLO model (if any)
##############################################################################
if [ -n "$YOLO_MODEL" ]; then
    echo ">>> Processing YOLO model: $YOLO_MODEL"

    pip install ultralytics==8.3.50 openvino==2025.0.0

    if [ ! -f "${YOLO_MODEL}.pt" ]; then
        echo "Warning: ${YOLO_MODEL}.pt not found in current directory. If not local, ultralytics will try to download."
    fi

    echo "Exporting ${YOLO_MODEL} to OpenVINO..."
    yolo export model="${YOLO_MODEL}.pt" format=openvino

    EXPORTED_DIR="${YOLO_MODEL}_openvino_model"
    if [ ! -d "$EXPORTED_DIR" ]; then
        echo "Error: Expected folder $EXPORTED_DIR not found after export!"
        deactivate
        exit 1
    fi

    if [ -d "evam/models/public/${YOLO_MODEL}" ]; then
        rm -rf "evam/models/public/${YOLO_MODEL}"
    fi
    create_dir "evam/models/public"
    mv "$EXPORTED_DIR" "evam/models/public/${YOLO_MODEL}"

    XML_FILE="evam/models/public/${YOLO_MODEL}/${YOLO_MODEL}.xml"
    if [ -f "$XML_FILE" ]; then
        sed -i '11172s/YOLO/yolo_v10/' "$XML_FILE" || true
        echo "XML file updated for ${YOLO_MODEL} (if line 11172 existed)."
    else
        echo "Warning: XML file not found for ${YOLO_MODEL}"
    fi

    create_dir "evam/models/public/${YOLO_MODEL}/FP32"

    if [ -f "${YOLO_MODEL}.pt" ]; then
        mv "${YOLO_MODEL}.pt" "evam/models/public/${YOLO_MODEL}/FP32/"
    fi

    mv "evam/models/public/${YOLO_MODEL}/${YOLO_MODEL}.xml" "evam/models/public/${YOLO_MODEL}/FP32/" 2>/dev/null || true
    mv "evam/models/public/${YOLO_MODEL}/${YOLO_MODEL}.bin" "evam/models/public/${YOLO_MODEL}/FP32/" 2>/dev/null || true
    mv "evam/models/public/${YOLO_MODEL}/"*.yaml "evam/models/public/${YOLO_MODEL}/FP32/" 2>/dev/null || true

    if [ -d "usecase/${Case}/evam/models/public/${YOLO_MODEL}" ]; then
        rm -rf "usecase/${Case}/evam/models/public/${YOLO_MODEL}"
    fi
    create_dir "usecase/${Case}/evam/models/public"
    mv "evam/models/public/${YOLO_MODEL}" "usecase/${Case}/evam/models/public/"
fi

##############################################################################
# 5. Process OMZ models (if any)
##############################################################################
if [ ${#OMZ_MODELS[@]} -gt 0 ]; then
    echo ">>> Processing OMZ models: ${OMZ_MODELS[@]}"

    pip install "openvino-dev[onnx,tensorflow,pytorch]"

    if [ ! -d "dlstreamer" ]; then
        git clone https://github.com/dlstreamer/dlstreamer.git
    else
        echo "dlstreamer directory already exists. Skipping clone."
    fi

    export MODELS_PATH="$HOME/intel/models"
    create_dir "$MODELS_PATH"

    pushd dlstreamer/samples > /dev/null

    echo "Overwriting models_omz_samples.lst with OMZ models..."
    > models_omz_samples.lst
    for model in "${OMZ_MODELS[@]}"; do
        echo "$model" >> models_omz_samples.lst
    done

    echo "Downloading OMZ models..."
    ./download_omz_models.sh

    popd > /dev/null

    if [ -d "$HOME/intel/models/public" ]; then
        echo "Merging public models into intel folder..."
        create_dir "$HOME/intel/models/intel"
        for item in "$HOME/intel/models/public/"*; do
            base_item=$(basename "$item")
            target="$HOME/intel/models/intel/$base_item"
            if [ -e "$target" ]; then
                echo "Removing existing $target to overwrite."
                rm -rf "$target"
            fi
            mv "$item" "$target"
        done
        rm -rf "$HOME/intel/models/public"
    fi

    create_dir "usecase/${Case}/evam/models/intel"
    if [ -d "$HOME/intel/models/intel" ]; then
        for item in "$HOME/intel/models/intel/"*; do
            base_item=$(basename "$item")
            target="usecase/${Case}/evam/models/intel/$base_item"
            if [ -e "$target" ]; then
                echo "Removing existing $target to overwrite."
                rm -rf "$target"
            fi
            mv "$item" "$target"
        done
        rm -rf "$HOME/intel/models/intel"
    else
        echo "Warning: $HOME/intel/models/intel not found. Download may have failed."
    fi

    for model in "${OMZ_MODELS[@]}"; do
        MODEL_PROC_URL="https://github.com/dlstreamer/dlstreamer/blob/master/samples/gstreamer/model_proc/intel/${model}.json?raw=true"
        DEST_DIR="usecase/${Case}/evam/models/intel/${model}"
        create_dir "$DEST_DIR"
        echo "Downloading model proc for ${model}..."
        curl -L -o "${DEST_DIR}/${model}.json" "${MODEL_PROC_URL}" || \
            echo "Warning: Could not download model proc for ${model}"
    done
fi

##############################################################################
# 6. (Optional) Ensure current user owns everything under usecase/${Case}
##############################################################################
CURRENT_USER=$(id -un)
CURRENT_GROUP=$(id -gn)
echo "Fixing ownership for usecase/${Case}..."
chown -R "$CURRENT_USER:$CURRENT_GROUP" "usecase/${Case}" 2>/dev/null || true

##############################################################################
# 7. Remove the dlstreamer and evam folders (if they exist), deactivate the venv, and finish
##############################################################################
if [ -d "dlstreamer" ]; then
    echo "Removing dlstreamer folder..."
    rm -rf dlstreamer
fi

if [ -d "evam" ]; then
    echo "Removing evam folder..."
    rm -rf evam
fi

deactivate
echo "=== All tasks completed successfully. ==="
