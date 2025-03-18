#!/bin/bash -e
#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#


SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
TOOLS_DIR=$(dirname "$SCRIPT_DIR")
SOURCE_DIR=$(dirname "$TOOLS_DIR")
OUTPUT_DIR=$(realpath $( pwd ))
FORCE=
RUN_PREFIX=
OPEN_MODEL_ZOO_TOOLS_IMAGE=${OPEN_MODEL_ZOO_TOOLS_IMAGE:-"${CACHE_PREFIX}intel/dlstreamer"}
OPEN_MODEL_ZOO_VERSION=${OPEN_MODEL_ZOO_VERSION:-"2022.3.0-ubuntu22-gpu555-devel"}
NAME="dlstreamer-pipeline-server-model-downloader"

DL_STREAMER_VERSION=
MODE=
MODEL_LIST=$SOURCE_DIR/"models_list/models.list.yml"
DRY_RUN=
NON_INTERACTIVE=

show_help() {
  echo "usage: model_downloader.sh"
  echo "  [--output absolute path where to save models]"
  echo "  [--model-list input file with model names and properties]"
  echo "  [--force force download and conversion of existing models]"
  echo "  [--open-model-zoo-version specify the version of OpenVINO(TM) image to be used for downloading models from Open Model Zoo]"
  echo "  [--dry-run print commands without executing]"
  exit 0
}

error() {
  printf '%s %s\n' "$1" "$2" >&2
  exit 1
}

while [[ "$#" -gt 0 ]]; do
    case $1 in
    -h | -\? | --help)
        show_help # Display a usage synopsis.
        exit
        ;;
    --dry-run)
        DRY_RUN="--dry-run"
        ;;
    --force)
        FORCE="--force"
        ;;
    --open-model-zoo-image)
        if [ "$2" ]; then
            OPEN_MODEL_ZOO_TOOLS_IMAGE=$2
            shift
        else
            error 'ERROR: "--open-model-zoo-image" requires an argument.'
        fi
        ;;
    --open-model-zoo-version)
        if [ "$2" ]; then
            OPEN_MODEL_ZOO_VERSION=$2
            shift
        else
            error 'ERROR: "--open-model-zoo-version" requires an argument.'
        fi
        ;;
    --output) # Takes an option argument; ensure it has been specified.
        if [ "$2" ]; then
            OUTPUT_DIR=$2
            shift
        else
            error 'ERROR: "--output" requires a non-empty option argument.'
        fi
        ;;
    --model-list)
        if [ "$2" ]; then
            MODEL_LIST=$(realpath $2)
            shift
        else
            error 'ERROR: "--model-list" requires a non-empty option argument.'
        fi
        ;;
    --)
        shift
        break
        ;;
    -?*)
        error 'ERROR: Unknown option: ' $1
        ;;
    ?*)
        error 'ERROR: Unknown option: ' $1
        ;;
    *)
        break
        ;;
    esac
    shift
done

YML_DIR=$(dirname "${MODEL_LIST}")
YML_FILE_NAME=$(basename "${MODEL_LIST}")
VOLUME_MOUNT+="-v $TOOLS_DIR:/home/pipeline-server/tools -v $YML_DIR:/models_yml -v $OUTPUT_DIR:/output"
DL_STREAMER_VERSION=""

if [[ "$OPEN_MODEL_ZOO_TOOLS_IMAGE" == *"openvino/"* ]]; then
    case $OPEN_MODEL_ZOO_VERSION in
        2021.2)
            DL_STREAMER_VERSION="v1.3"
            ;;
        2021.4*)
            DL_STREAMER_VERSION="v1.5"
            ;;
        *)
            error 'ERROR: Unsupported Open Model Zoo version: ' $OPEN_MODEL_ZOO_VERSION
    esac
fi

if [ ! -z "$TEAMCITY_VERSION" ]; then
    NON_INTERACTIVE=--non-interactive
fi

if [ ! -d "$OUTPUT_DIR/models" ]; then
    mkdir $OUTPUT_DIR/models
    echo "Created output models folder as UID: $UID"
fi

if [ ! -z "$DL_STREAMER_VERSION" ]; then
    MODEL_PROC_VERSION="--model-proc-version $DL_STREAMER_VERSION"
fi

$SOURCE_DIR/docker/run.sh --user "$UID" -e PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python -e HOME=/tmp $NON_INTERACTIVE --name $NAME --image $OPEN_MODEL_ZOO_TOOLS_IMAGE:$OPEN_MODEL_ZOO_VERSION $VOLUME_MOUNT $DRY_RUN --entrypoint /bin/bash --entrypoint-args "\"-i\" \"-c\" \"pip3 install -r /home/pipeline-server/tools/model_downloader/requirements.txt ; python3 -u /home/pipeline-server/tools/model_downloader $MODEL_PROC_VERSION --model-list /models_yml/$YML_FILE_NAME --output /output $FORCE\""
