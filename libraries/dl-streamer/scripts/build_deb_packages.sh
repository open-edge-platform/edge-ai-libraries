#!/bin/bash
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

# Variables
DLSTREAMER_VERSION="2025.0.1.3"
DEB_PKGS_DOCKERFILE_U22="./docker/onebinary/ubuntu22/dlstreamer_deb_package_ubuntu22.Dockerfile"
DEB_PKGS_DOCKERFILE_U24="./docker/onebinary/ubuntu24/dlstreamer_deb_package_ubuntu24.Dockerfile"
DLSTREAMER_BUILD="local"
IMAGE_NAME="dls_debs_temp_image"
CONTAINER_NAME="dls_debs_temp_container"
DEBS_DESTINATION_PATH="./deb_packages"

# Show help message
show_help() {
    cat <<EOF

Usage: $(basename "$0") [OPTIONS]

Script for building DL Streamer Debian packages

Options:
  -h, --help                            Show this help message and exit
  --ubuntu_version=[ubuntu22|ubuntu24]  Choosing Ubuntu version to build .deb packages (default: ubuntu24)

Examples:
  $(basename "$0")
  $(basename "$0") --ubuntu_version=ubuntu22
  $(basename "$0") --help

EOF
}

# Set inputs
ubuntu_version="ubuntu24"
for i in "$@"; do
    case $i in
        -h|--help)
            show_help
            exit 0
        ;;
        --ubuntu_version=*)
            ubuntu_version="${i#*=}"
            if [[ "$ubuntu_version" != "ubuntu22" ]] && [[ "$ubuntu_version" != "ubuntu24" ]]; then
                echo "Error! Wrong Ubuntu version parameter. Supported versions: ubuntu22 | ubuntu24"
                exit 1
            fi
            shift
        ;;
        *)
            echo "Unknown option: $i"
            show_help
            exit 1
        ;;
    esac
done
DLSTREAMER_BUILD="$ubuntu_version.local"
echo "Ubuntu version to build Debian packages: $ubuntu_version"
echo "DL Streamer version: $DLSTREAMER_VERSION"
echo "DL Streamer build: $DLSTREAMER_BUILD"
echo ""
echo "This script is going to create unsinged Debian package(s)"
read -p "Do you want to continue? [y/N] " -n 1 -r
echo    # move to a new line
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Exiting the script."
    exit 0
fi

# Check directory
if [ "$(dirname "$0")" != "./scripts" ]; then
    echo "NOTE! Script must be executed from the main DL Streamer directory."
    echo "Please go to the main directory and re-run the script."
    echo "Exiting."
    exit 1
fi

# Build Docker image
if [ "$ubuntu_version" == "ubuntu22" ]; then
    DOCKERFILE=$DEB_PKGS_DOCKERFILE_U22
elif [ "$ubuntu_version" == "ubuntu24" ]; then
    DOCKERFILE=$DEB_PKGS_DOCKERFILE_U24
else
    echo " Unsupported Ubuntu version. Exiting."
fi
docker build -f $DOCKERFILE -t $IMAGE_NAME:latest --build-arg DLSTREAMER_VERSION=$DLSTREAMER_VERSION --build-arg DLSTREAMER_BUILD_NUMBER=$DLSTREAMER_BUILD .

# Create container, extract .deb and cleanup
echo "Running container to extract .deb files..."
docker run --name "$CONTAINER_NAME" "$IMAGE_NAME" bash -c '
    mkdir -p /debs_to_copy
    shopt -s nullglob
    files=(/intel-dlstreamer*.deb)
    if [ ${#files[@]} -eq 0 ]; then
        echo "No .deb files found in /"
        exit 1
    fi
    cp "${files[@]}" /debs_to_copy/
'
echo "Copying files from container to host..."
mkdir -p "$DEBS_DESTINATION_PATH"
docker cp "$CONTAINER_NAME:/debs_to_copy/." "$DEBS_DESTINATION_PATH"
echo "Cleaning up container..."
docker rm "$CONTAINER_NAME"
echo "Finished."
echo "Packages available in $DEBS_DESTINATION_PATH:"
ls "$DEBS_DESTINATION_PATH"
