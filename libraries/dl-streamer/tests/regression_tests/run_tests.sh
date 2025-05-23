#!/bin/bash
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================


set -e

SCRIPTDIR="$(dirname "$(readlink -fm "$0")")"
RUN_PREFIX=""
OUTPUT_TYPE="json"
TEST_CONFIG_DIR="pipeline_test/configs_ov2"
TOOL_DEFAULT_PARAMS="-f --disable_tqdm --edistance_thr=0"

show_help() {
    echo "usage: ./run_tests.sh --video-examples-path=<path> --models-path=<path> --test-configs=\"<json-names>\" [-- <additional tool parameters>]"
    echo "  --video-examples-path Path to folder with media files"
    echo "  --models-path         Path to folder with NN models"
    echo "  --timeout             Timeout for tests"
    echo "  --test-configs        List of configs to run in form of space separated list"
    echo "                        Config should be located inside '$TEST_CONFIG_DIR' relative to this script"
    echo "                        Example: \"regression_test.json watermark.json\""
    echo ""
    echo "  [--image-name]          Name of docker image"
    echo "  [--results-path=<path>] Path to folder for tests results"
    echo "  [--report-name=<name>]  Base name for test reports"
    echo "  [--on-host]             Run tests on local host, without docker image. DLS installed via apt on bare metal system."
    exit 0
}

error() {
    red=`tput -T xterm-256color setaf 1`
    reset=`tput -T xterm-256color sgr0`

    printf "${red}%s ${reset}%s\n" "$1" "$2" >&2
    exit 1
}

for i in "$@"
do
case $i in
    -h|--help)
        show_help
        exit 0
    ;;
    --video-examples-path=*)
        VIDEO_EXAMPLES_PATH="${i#*=}"
        shift
    ;;
    --models-path=*)
        MODELS_PATH="${i#*=}"
        shift
    ;;
    --image-name=*)
        IMAGE_NAME="${i#*=}"
        shift
    ;;
    --timeout=*)
        TIMEOUT="${i#*=}"
        shift
    ;;
    --test-configs=*)
        TEST_CONFIGS="${i#*=}"
        shift
    ;;
    --results-path=*)
        RESULTS_PATH="${i#*=}"
        shift
    ;;
    --report-name=*)
        BASE_REPORT_NAME="${i#*=}"
        shift
    ;;
    --on-host)
        RUN_LOCAL_APTGET=true
        shift
    ;;
    --) # End of input
        shift; break
    ;;
    *) # unknown option
        error 'ERROR: Unknown option: ' $i
    ;;
esac
done

# Check required parameters
[ -z "$MODELS_PATH" ] && error 'ERROR: Path to models is not provided'
[ -z "$VIDEO_EXAMPLES_PATH" ] && error 'ERROR: Path to video examples is not provided'
[ -z "$TEST_CONFIGS" ] && error 'ERROR: configs are not provided'

# Set paths
if [[ "$RUN_LOCAL_APTGET" = true ]]; then
    echo ".. Running test(s) on local system .."
    HOME_DIR=$SCRIPTDIR
else
    echo ".. Running test(s) on docker system .."
    HOME_DIR=/home/dlstreamer
    [ -z "$IMAGE_NAME" ] && error 'ERROR: Target docker image name is not provided'
fi

# Initialize and parse string with test configs
CONFIGS_TO_RUN=""
read -ra configs_arr <<<"$TEST_CONFIGS"
for cfg in "${configs_arr[@]}"; do
    cfg_path="$SCRIPTDIR/$TEST_CONFIG_DIR/$cfg"

    if [ ! -f "$cfg_path" ]; then
        error "ERROR: Config file ($cfg) is not found at: " $'\n\t'"$cfg_path"
    fi
    # Append the config file name to the CONFIGS_TO_RUN string
    CONFIGS_TO_RUN+="$HOME_DIR/$TEST_CONFIG_DIR/$cfg "
done
echo "Configs to run (paths as would be inside container):"
echo "${CONFIGS_TO_RUN//' '/$'\n'}" # Replace space with newline for better readability

# Initialize report name
if [[ -z "$BASE_REPORT_NAME" ]]; then
    BASE_REPORT_NAME="test-results"
fi

# Initialize results path
if [[ -z "$RESULTS_PATH" ]]; then
    RESULTS_PATH="$SCRIPTDIR/run-results"
fi
if [[ ! -d "$RESULTS_PATH" ]]; then
    echo "Creating folder for results: $RESULTS_PATH"
    $RUN_PREFIX mkdir -m 777 -p $RESULTS_PATH/metadata
fi

# Run command for tool
RUN_CMD="$HOME_DIR/pipeline_test/entry_point.sh -c ${CONFIGS_TO_RUN} "
RUN_CMD+="--xml-report $RESULTS_PATH/$BASE_REPORT_NAME.xml "
RUN_CMD+="--xlsx-report $RESULTS_PATH/$BASE_REPORT_NAME.xlsx "
RUN_CMD+="$TOOL_DEFAULT_PARAMS "
RUN_CMD+="--results-path $RESULTS_PATH"
if [[ -n "$TIMEOUT" ]]; then
    if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]]; then
        error "Incorrectly defined timeout"
    fi
    RUN_CMD+="--timeout $TIMEOUT "
fi
RUN_CMD+="$*" # Remaining options

# Extra parameters for docker run
EXTRA_PARAMS=""
RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')
if [[ -n "$RENDER_GROUP_ID" ]]; then
    EXTRA_PARAMS+="--group-add $RENDER_GROUP_ID "
fi


# Run tests in local host enviroment without docker image
if [[ "$RUN_LOCAL_APTGET" = true ]]; then
    echo "*************************** RUNNING ON HOST TESTS ***************************"
    # /tmp/results and []/pf-tests/video-examples are hardcoded in regression tests scripts
    # create symbolic links to directories mapped in docker environment
    echo "Creating symbolic link to: $RESULTS_PATH/metadata"
    if [ -L /tmp/results ]; then
        rm /tmp/results
    fi
    ln -s $RESULTS_PATH/metadata /tmp/results
    echo "Creating symbolic link to: $VIDEO_EXAMPLES_PATH"
    if [ -L /tmp/video-examples ]; then
        rm /tmp/video-examples
    fi
    ln -s $VIDEO_EXAMPLES_PATH /tmp/video-examples
    # adjust directories to local enviroment as necessary
    echo "Running tests at local system with DLS installed via apt-get"
    export LIBVA_DRIVER_NAME=iHD
    export GST_PLUGIN_PATH=/opt/intel/dlstreamer/build/intel64/Release/lib:/opt/intel/dlstreamer/gstreamer/lib/gstreamer-1.0:/opt/intel/dlstreamer/gstreamer/lib/
    export LD_LIBRARY_PATH=/opt/intel/dlstreamer/gstreamer/lib:/opt/intel/dlstreamer/build/intel64/Release/lib:/opt/intel/dlstreamer/lib/gstreamer-1.0:/usr/lib:/opt/intel/dlstreamer/build/intel64/Release/lib:/opt/opencv:/opt/openh264:/opt/rdkafka:/opt/ffmpeg:/usr/local/lib/gstreamer-1.0:/usr/local/lib
    export LIBVA_DRIVERS_PATH=/usr/lib/x86_64-linux-gnu/dri
    export GST_VA_ALL_DRIVERS=1
    export LABELS_PATH=$DOCKER_HOME_DIR/dlstreamer/samples/labels
    export MODEL_PROC_PATH=$DOCKER_HOME_DIR/dlstreamer/samples/gstreamer/model_proc
    export MODEL_PROCS_PATH=$DOCKER_HOME_DIR/dlstreamer/samples/gstreamer/model_proc
    export MODELS_PATH=$MODELS_PATH
    export PYTHONPATH=/opt/intel/dlstreamer/gstreamer/lib/python3/dist-packages:/home/labrat/intel/dlstreamer/python:/opt/intel/dlstreamer/gstreamer/lib/python3/dist-packages:
    export PATH=/python3venv/bin:/opt/intel/dlstreamer/gstreamer/bin:/opt/intel/dlstreamer/build/intel64/Release/bin:$PATH
    export TERM=xterm
    export GI_TYPELIB_PATH=/opt/intel/dlstreamer/gstreamer/lib/girepository-1.0:/usr/lib/x86_64-linux-gnu/girepository-1.0
    echo "LIBVA_DRIVER_NAME: ${LIBVA_DRIVER_NAME}"
    echo "GST_PLUGIN_PATH: ${GST_PLUGIN_PATH}"
    echo "LD_LIBRARY_PATH: ${LD_LIBRARY_PATH}"
    echo "LIBVA_DRIVERS_PATH: ${LIBVA_DRIVERS_PATH}"
    echo "GST_VA_ALL_DRIVERS: ${GST_VA_ALL_DRIVERS}"
    echo "MODEL_PROCS_PATH: ${MODEL_PROC_PATH}"
    echo "PYTHONPATH: ${PYTHONPATH}"
    echo "TERM: ${TERM}"
    echo "MODELS_PATH: ${MODELS_PATH}"
    echo "GST_VAAPI_DRM_DEVICE: ${GST_VAAPI_DRM_DEVICE}"
    echo "GST_VAAPI_ALL_DRIVERS: ${GST_VAAPI_ALL_DRIVERS}"
    echo "GI_TYPELIB_PATH: ${GI_TYPELIB_PATH}"
    echo "Starting test in local host mode"

    # Run on host tests
    bash $RUN_CMD
    echo "*************************** EXECUTION FINISHED ***************************"

    # Clean-up
    if [ -L /tmp/results ]; then
        rm /tmp/results
        echo "Removed symbolic link /tmp/results"
    fi
    if [ -L /tmp/video-examples ]; then
        echo "Removed symbolic link /tmp/video-examples"
    fi
    exit
else
    echo "*************************** RUNNING DOCKER TESTS ***************************"
    echo "Creating symbolic link to: $RESULTS_PATH/metadata"
    if [ -L /tmp/results ]; then
        rm /tmp/results
    fi
    ln -s $RESULTS_PATH/metadata /tmp/results
    echo "Creating symbolic link to: $VIDEO_EXAMPLES_PATH"
    if [ -L /tmp/video-examples ]; then
        rm /tmp/video-examples
    fi
    ln -s $VIDEO_EXAMPLES_PATH /tmp/video-examples
    if [ -e /dev/accel ]; then
        echo "NPU /dev/accel exists. Adding --device=/dev/accel to docker run command."
        DEVICE_ACCEL="--device=/dev/accel"
    fi

    # Run Docker
    echo "Starting test in local host mode"
    [ -z "$RUN_PREFIX" ] && set -x
    $RUN_PREFIX docker run --rm \
        --device=/dev/dri \
        $DEVICE_ACCEL \
        -v $VIDEO_EXAMPLES_PATH:$HOME_DIR/video-examples \
        -v $RESULTS_PATH:/tmp/results \
        -v $MODELS_PATH:/tmp/models \
        -e MODELS_PATH=/tmp/models \
        -e MODEL_PROCS_PATH=$HOME_DIR/dlstreamer/samples/gstreamer/model_proc \
        -e LABELS_PATH=$HOME_DIR/dlstreamer/samples/labels \
        -e ZE_ENABLE_ALT_DRIVERS=libze_intel_vpu.so \
        $EXTRA_PARAMS \
        $IMAGE_NAME \
        $RUN_CMD
    echo "*************************** EXECUTION FINISHED ***************************"

    # Clean-up
    if [ -L /tmp/results ]; then
        rm /tmp/results
        echo "Removed symbolic link /tmp/results"
    fi
    if [ -L /tmp/video-examples ]; then
        echo "Removed symbolic link /tmp/video-examples"
    fi
fi