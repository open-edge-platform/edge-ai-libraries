#!/bin/bash

# Check if MODELS_PATH environment variable is set and valid
if [ -z "${MODELS_PATH:-}" ]; then
    echo "Error: MODELS_PATH environment variable is not set. Exiting."
    exit 1
fi

if [ ! -d "$MODELS_PATH" ]; then
    echo "Error: MODELS_PATH ('$MODELS_PATH') does not exist or is not a directory. Exiting."
    exit 2
fi

# Script to manage installation/removal of models using dialog.
# Requires: dialog, supported_models.lst

SUPPORTED_MODELS_FILE="/models/supported_models.lst"
MODEL_MANAGER_TMP_DIR="/tmp/model_manager"

MODEL_INSTALLATION="${MODEL_INSTALLATION:-once}"

if [ "$MODEL_INSTALLATION" == "force" ]; then
    echo "MODEL_INSTALLATION=force detected. Proceeding with model installation."
elif [ "$MODEL_INSTALLATION" == "once" ]; then
    if [ -f "$MODELS_PATH/.models_initialized" ]; then
        echo "Models already initialized and MODEL_INSTALLATION is 'once'. Exiting."
        exit 0
    fi
elif [ "$MODEL_INSTALLATION" == "all" ]; then
    echo "MODEL_INSTALLATION=all detected. Will install all models automatically."
else
    echo "Error: Invalid value for MODEL_INSTALLATION ('$MODEL_INSTALLATION')."
    echo "Valid values are: 'once', 'force', 'all'."
    exit 3
fi

# Check if dialog is installed, exit if not (only for interactive modes)
if [ "$MODEL_INSTALLATION" != "all" ]; then
    if ! command -v dialog &>/dev/null; then
        echo "Error: 'dialog' is not installed. Please install it before running this script."
        exit 4
    fi
fi

function cleanup {
    if [ -n "$VIRTUAL_ENV" ]; then
        echo "Removing Python virtual environment..."
        deactivate
    fi
    echo "Cleaning up temporary files..."
    rm -rf "$MODEL_MANAGER_TMP_DIR"
}

function cleanup_and_exit {
    local exit_code="${1:-0}"

    cleanup

    if [ "$exit_code" -eq 0 ]; then
        touch "$MODELS_PATH/.models_initialized"
    fi

    exit "$exit_code"
}

download_public_models() {
    local models="$1"
    local IFS=','

    for model in $models; do
        echo "Installing public model: $model"
        if ! bash /opt/intel/dlstreamer/samples/download_public_models.sh "$model"; then
            echo "Error: Failed to download public model $model"
            cleanup_and_exit 9
        fi
        echo "Model $model installed."
    done
}

download_omz_models() {
    local models="$1"
    local IFS=','
    # Temporary directory for downloads and conversions, some models are published under intel/ and some under public/
    # At the end we move the converted model to the target omz directory
    local tmp_models_dir="$MODEL_MANAGER_TMP_DIR/omz_models"

    echo "Setting up Python venv for Open Model Zoo tools..."
    local venv_dir="$MODEL_MANAGER_TMP_DIR/.venv"
    python3 -m venv "$venv_dir"
    source "$venv_dir/bin/activate"

    pip install --no-cache-dir openvino-dev[onnx] torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 --extra-index-url https://download.pytorch.org/whl/cpu

    for model in $models; do
        echo "Installing OMZ model: $model"
        target_dir="$MODELS_PATH/omz/$model"

        echo "Downloading model $model using omz_downloader..."
        if ! omz_downloader --name "$model" --output_dir "$tmp_models_dir"; then
            echo "Error: Failed to download OMZ model $model"
            cleanup_and_exit 10
        fi

        echo "Converting model $model using omz_converter..."
        if ! omz_converter --name "$model" --output_dir "$tmp_models_dir" --download_dir "$tmp_models_dir"; then
            echo "Error: Failed to convert OMZ model $model"
            cleanup_and_exit 11
        fi

        mkdir -p "$target_dir"
        # Custom handling for specific models
        if [ "$model" == "vehicle-attributes-recognition-barrier-0039" ]; then
            mv "$tmp_models_dir/intel/$model/"* "$target_dir"
            local proc_src="/opt/intel/dlstreamer/samples/gstreamer/model_proc/intel/vehicle-attributes-recognition-barrier-0039.json"
            if [ -f "$proc_src" ]; then
                cp "$proc_src" "$target_dir/vehicle-attributes-recognition-barrier-0039.json"
                echo "Copied model_proc file for $model."
            fi
        elif [ "$model" == "mobilenet-v2-pytorch" ]; then
            mv "$tmp_models_dir/public/$model/"* "$target_dir"
            local proc_src="/opt/intel/dlstreamer/samples/gstreamer/model_proc/public/preproc-aspect-ratio.json"
            if [ -f "$proc_src" ]; then
                cp "$proc_src" "$target_dir/mobilenet-v2.json"
                echo "Copied model_proc file for $model."
            fi
            python3 -c "
import json
labels_path = '/opt/intel/dlstreamer/samples/labels/imagenet_2012.txt'
json_path = '$target_dir/mobilenet-v2.json'
labels = []
with open(labels_path, 'r') as f:
    for line in f:
        parts = line.strip().split(' ', 1)
        if len(parts) == 2:
            labels.append(parts[1])
        else:
            labels.append(parts[0])
with open(json_path, 'r') as f:
    data = json.load(f)
if 'output_postproc' in data and isinstance(data['output_postproc'], list) and data['output_postproc']:
    data['output_postproc'][0]['labels'] = labels
with open(json_path, 'w') as f:
    json.dump(data, f, indent=4)
"
            echo "Added labels to mobilenet-v2-pytorch model_proc file."
        fi

        echo "Model $model installed to $target_dir"
    done
}

download_pipeline_zoo_models() {
    local models="$1"
    local IFS=','

    local repo_dir="$MODEL_MANAGER_TMP_DIR/pipeline-zoo-models-main"
    local archive_url="https://github.com/dlstreamer/pipeline-zoo-models/archive/refs/heads/main.tar.gz"
    local archive_path="$MODEL_MANAGER_TMP_DIR/pipeline-zoo-models-main.tar.gz"

    # Download and extract pipeline-zoo-models repository if not already present
    if [ ! -d "$repo_dir" ]; then
        mkdir -p "$MODEL_MANAGER_TMP_DIR"
        echo "Downloading pipeline-zoo-models repository archive..."
        if ! curl -L "$archive_url" -o "$archive_path"; then
            echo "Error: Failed to download $archive_url"
            cleanup_and_exit 12
        fi
        echo "Extracting pipeline-zoo-models archive..."
        tar -xzf "$archive_path" -C "$MODEL_MANAGER_TMP_DIR"
        rm -f "$archive_path"
        echo "Repository extracted to $repo_dir"
    else
        echo "Repository $repo_dir already exists, skipping download."
    fi

    for model in $models; do
        echo "Installing pipeline-zoo model: $model"
        local src_dir="$repo_dir/storage/$model"
        local target_dir="$MODELS_PATH/pipeline-zoo-models/$model"
        if [ ! -d "$src_dir" ]; then
            echo "Error: Model $model not found in pipeline-zoo-models repository."
            cleanup_and_exit 13
        fi
        mkdir -p "$target_dir"
        cp -r "$src_dir/"* "$target_dir/"
        echo "Model $model installed to $target_dir"
    done
}

# Parse supported_models.lst and validate columns
declare -a MODEL_LINES
declare -a MODEL_NAMES
declare -a MODEL_DISPLAY_NAMES
declare -a MODEL_SOURCES
declare -a MODEL_TYPES
declare -a MODEL_DEFAULTS

while IFS= read -r line || [ -n "$line" ]; do
    # Ignore empty lines
    [[ -z "$line" ]] && continue

    # Split line into columns
    IFS='|' read -r name display_name source type default_flag extra <<<"$line"

    # Check for correct number of columns (5, no more, no less)
    if [ -z "$name" ] || [ -z "$display_name" ] || [ -z "$source" ] || [ -z "$type" ] || [ -z "$default_flag" ] || [ -n "$extra" ]; then
        echo "Error: Invalid line in $SUPPORTED_MODELS_FILE: '$line'"
        echo "Each line must contain 5 columns separated by '|': name|display_name|source|type|default_flag"
        cleanup_and_exit 5
    fi

    MODEL_LINES+=("$line")
    MODEL_NAMES+=("$name")
    MODEL_DISPLAY_NAMES+=("$display_name")
    MODEL_SOURCES+=("$source")
    MODEL_TYPES+=("$type")
    MODEL_DEFAULTS+=("$default_flag")
done < "$SUPPORTED_MODELS_FILE"

# SORT MODELS BY MODEL_TYPE
# 1. Find all unique MODEL_TYPES and sort them
mapfile -t SORTED_TYPES < <(printf "%s\n" "${MODEL_TYPES[@]}" | sort -u)

# 2. Reorder all model arrays according to sorted MODEL_TYPES, preserving file order within each type
declare -a SORTED_MODEL_LINES
declare -a SORTED_MODEL_NAMES
declare -a SORTED_MODEL_DISPLAY_NAMES
declare -a SORTED_MODEL_SOURCES
declare -a SORTED_MODEL_TYPES
declare -a SORTED_MODEL_DEFAULTS

for type in "${SORTED_TYPES[@]}"; do
    for i in "${!MODEL_NAMES[@]}"; do
        if [ "${MODEL_TYPES[$i]}" == "$type" ]; then
            SORTED_MODEL_LINES+=("${MODEL_LINES[$i]}")
            SORTED_MODEL_NAMES+=("${MODEL_NAMES[$i]}")
            SORTED_MODEL_DISPLAY_NAMES+=("${MODEL_DISPLAY_NAMES[$i]}")
            SORTED_MODEL_SOURCES+=("${MODEL_SOURCES[$i]}")
            SORTED_MODEL_TYPES+=("${MODEL_TYPES[$i]}")
            SORTED_MODEL_DEFAULTS+=("${MODEL_DEFAULTS[$i]}")
        fi
    done
done

# Overwrite original arrays with sorted ones
MODEL_LINES=("${SORTED_MODEL_LINES[@]}")
MODEL_NAMES=("${SORTED_MODEL_NAMES[@]}")
MODEL_DISPLAY_NAMES=("${SORTED_MODEL_DISPLAY_NAMES[@]}")
MODEL_SOURCES=("${SORTED_MODEL_SOURCES[@]}")
MODEL_TYPES=("${SORTED_MODEL_TYPES[@]}")
MODEL_DEFAULTS=("${SORTED_MODEL_DEFAULTS[@]}")

echo "Parsed supported models from $SUPPORTED_MODELS_FILE. Found ${#MODEL_NAMES[@]} models."

declare -A SELECTED_MODELS
if [ "$MODEL_INSTALLATION" == "all" ]; then
    # Select all models for installation, skip dialog
    for i in "${!MODEL_NAMES[@]}"; do
        SELECTED_MODELS["$i"]=1
    done
else
    # Preselect models that exist on disk
    for i in "${!MODEL_NAMES[@]}"; do
        model_dir="$MODELS_PATH/${MODEL_SOURCES[$i]}/${MODEL_NAMES[$i]}"
        if [ -d "$model_dir" ]; then
            SELECTED_MODELS["$i"]=1
        fi
    done
    # If first run, also preselect models with 'default' in the fifth column
    if [ ! -f "$MODELS_PATH/.models_initialized" ]; then
        for i in "${!MODEL_NAMES[@]}"; do
            if [ "${MODEL_DEFAULTS[$i]}" == "default" ]; then
                SELECTED_MODELS["$i"]=1
            fi
        done
    fi

    # Calculate dialog width based on the longest display name and type
    max_display_len=0
    for display_name in "${MODEL_DISPLAY_NAMES[@]}"; do
        (( ${#display_name} > max_display_len )) && max_display_len=${#display_name}
    done
    max_type_len=0
    for type in "${MODEL_TYPES[@]}"; do
        (( ${#type} > max_type_len )) && max_type_len=${#type}
    done
    dialog_width=$((max_display_len + max_type_len + 30))

    # Build dialog checklist options, mark preselected models as ON
    CHECKLIST_ITEMS=()
    for i in "${!MODEL_NAMES[@]}"; do
        if [ "${SELECTED_MODELS[$i]}" == "1" ]; then
            CHECKLIST_ITEMS+=("${MODEL_DISPLAY_NAMES[$i]}" "${MODEL_TYPES[$i]}" "on")
        else
            CHECKLIST_ITEMS+=("${MODEL_DISPLAY_NAMES[$i]}" "${MODEL_TYPES[$i]}" "off")
        fi
    done

    # Validate that there are models to show
    if [ "${#MODEL_NAMES[@]}" -eq 0 ]; then
        echo "Error: No models found in $SUPPORTED_MODELS_FILE."
        cleanup_and_exit 6
    fi

    # Ensure script is run in an interactive terminal
    if [ ! -t 1 ]; then
        echo "Error: No interactive terminal detected. Please run with 'docker compose run -it models' or 'make shell-models'."
        cleanup_and_exit 7
    fi

    # Always show dialog for interactive selection
    DIALOG_OUTPUT=$(
        dialog --checklist "Select models to install/remove:" 0 $dialog_width ${#MODEL_NAMES[@]} \
        "${CHECKLIST_ITEMS[@]}" \
        2>&1 >/dev/tty
    )
    dialog_exit_code=$?

    clear
    if [ $dialog_exit_code -ne 0 ]; then
        echo "Dialog cancelled by user. Exiting."
        cleanup_and_exit -1
    fi

    # Parse selected display names into array (preserve quoted strings with spaces)
    eval "SELECTED_DISPLAY_NAMES=($DIALOG_OUTPUT)"

    # Clean selected display names: remove quotes, unescape parentheses, trim spaces
    CLEANED_SELECTED_DISPLAY_NAMES=()
    for selected in "${SELECTED_DISPLAY_NAMES[@]}"; do
        selected_clean="${selected//\"/}"
        selected_clean="${selected_clean//\\(/(}"
        selected_clean="${selected_clean//\\)/)}"
        selected_clean="$(echo "$selected_clean" | sed 's/^ *//;s/ *$//')"
        CLEANED_SELECTED_DISPLAY_NAMES+=("$selected_clean")
    done
    echo "Selected models: ${CLEANED_SELECTED_DISPLAY_NAMES[*]}"

    # Reset SELECTED_MODELS and set according to dialog selection
    unset SELECTED_MODELS
    declare -A SELECTED_MODELS
    for i in "${!MODEL_DISPLAY_NAMES[@]}"; do
        for selected_clean in "${CLEANED_SELECTED_DISPLAY_NAMES[@]}"; do
            if [ "${MODEL_DISPLAY_NAMES[$i]}" == "$selected_clean" ]; then
                SELECTED_MODELS["$i"]=1
            fi
        done
    done
fi

# Prepare lists for each type to install
public_models=""
omz_models=""
pipeline_zoo_models=""

# Prepare selected models (only if not already installed)
for i in "${!MODEL_NAMES[@]}"; do
    if [ "${SELECTED_MODELS[$i]}" == "1" ]; then
        model_dir="$MODELS_PATH/${MODEL_SOURCES[$i]}/${MODEL_NAMES[$i]}"
        if [ ! -d "$model_dir" ]; then
            # Add to download list based on source
            case "${MODEL_SOURCES[$i]}" in
                public)
                    public_models+="${MODEL_NAMES[$i]},"
                    ;;
                omz)
                    omz_models+="${MODEL_NAMES[$i]},"
                    ;;
                pipeline-zoo-models)
                    pipeline_zoo_models+="${MODEL_NAMES[$i]},"
                    ;;
                *)
                    echo "Error: Unknown model source for ${MODEL_NAMES[$i]}: ${MODEL_SOURCES[$i]}"
                    cleanup_and_exit 8
                    ;;
            esac
        fi
    fi
done

# Remove trailing commas from model lists
public_models="${public_models%,}"
omz_models="${omz_models%,}"
pipeline_zoo_models="${pipeline_zoo_models%,}"

echo "Public models to install: $public_models"
echo "OMZ models to install: $omz_models"
echo "Pipeline-zoo models to install: $pipeline_zoo_models"

# Install selected models by source type
if [ -n "$public_models" ]; then
    echo "Installing public models."
    download_public_models "$public_models"
fi
if [ -n "$omz_models" ]; then
    echo "Installing OMZ models."
    download_omz_models "$omz_models"
fi
if [ -n "$pipeline_zoo_models" ]; then
    echo "Installing pipeline-zoo models."
    download_pipeline_zoo_models "$pipeline_zoo_models"
fi

# Remove unselected models from disk (skip for MODEL_INSTALLATION=all)
if [ "$MODEL_INSTALLATION" != "all" ]; then
    for i in "${!MODEL_NAMES[@]}"; do
        if [ -z "${SELECTED_MODELS[$i]}" ]; then
            model_dir="$MODELS_PATH/${MODEL_SOURCES[$i]}/${MODEL_NAMES[$i]}"
            if [ -d "$model_dir" ]; then
                echo "Removing model directory: $model_dir"
                rm -rf "$model_dir"
            fi
        fi
    done
fi

echo "Model management complete."

cleanup_and_exit 0
