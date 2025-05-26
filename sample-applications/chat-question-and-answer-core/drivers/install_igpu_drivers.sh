#!/bin/bash -x
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Script should be used only as a part of Dockerfiles

echo "Installing iGPU drivers..."

# Update package list and install dependencies
apt-get update && apt-get install -y curl ocl-icd-libopencl1 --no-install-recommends --fix-missing && rm -rf /var/lib/apt/lists/* && \

# Create a temporary directory for GPU dependencies
mkdir /tmp/gpu_deps && cd /tmp/gpu_deps

# Download the necessary .deb files
curl -L -O https://github.com/intel/intel-graphics-compiler/releases/download/v2.5.6/intel-igc-core-2_2.5.6+18417_amd64.deb
curl -L -O https://github.com/intel/intel-graphics-compiler/releases/download/v2.5.6/intel-igc-opencl-2_2.5.6+18417_amd64.deb
curl -L -O https://github.com/intel/compute-runtime/releases/download/24.52.32224.5/intel-level-zero-gpu-dbgsym_1.6.32224.5_amd64.ddeb
curl -L -O https://github.com/intel/compute-runtime/releases/download/24.52.32224.5/intel-level-zero-gpu_1.6.32224.5_amd64.deb
curl -L -O https://github.com/intel/compute-runtime/releases/download/24.52.32224.5/intel-opencl-icd-dbgsym_24.52.32224.5_amd64.ddeb
curl -L -O https://github.com/intel/compute-runtime/releases/download/24.52.32224.5/intel-opencl-icd_24.52.32224.5_amd64.deb
curl -L -O https://github.com/intel/compute-runtime/releases/download/24.52.32224.5/libigdgmm12_22.5.5_amd64.deb

# Install the downloaded .deb files
dpkg -i *.deb

# Clean up by removing the temporary directory
rm -Rf /tmp/gpu_deps

# Clean up apt cache and temporary files
apt-get clean && rm -rf /var/lib/apt/lists/* && rm -rf /tmp/*