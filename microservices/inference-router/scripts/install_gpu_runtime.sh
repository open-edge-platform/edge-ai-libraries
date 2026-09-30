#!/bin/bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Install the Intel GPU user-space runtime into the image (build-time only).
#
# OpenVINO's GPU plugin ships in the pip package, but needs the Intel user-space
# runtime (compute-runtime + Level Zero + IGC compiler) inside the image. The
# host only supplies the kernel driver and /dev/dri, which live in a different
# mount namespace and are invisible to the in-container process. Without this,
# IR_DEVICE=GPU cannot enumerate the GPU.
#
# compute-runtime and IGC are tightly coupled: the compute-runtime .debs pin an
# exact IGC version (>= X and << X+~), so bump INTEL_CR_VER and INTEL_IGC_VER
# together per the compute-runtime release notes. This pairing is verified to
# expose the Intel iGPU/dGPU via openvino.Core().available_devices.
set -eux

INTEL_CR_VER="${INTEL_CR_VER:-26.22.38646.4}"
INTEL_GMM_VER="${INTEL_GMM_VER:-22.10.0}"
INTEL_IGC_VER="${INTEL_IGC_VER:-2.36.3}"
INTEL_IGC_BUILD="${INTEL_IGC_BUILD:-21719}"

apt-get update
apt-get install -y --no-install-recommends \
    curl ca-certificates libze1 ocl-icd-libopencl1

CR="https://github.com/intel/compute-runtime/releases/download/${INTEL_CR_VER}"
IGC="https://github.com/intel/intel-graphics-compiler/releases/download/v${INTEL_IGC_VER}"

workdir="$(mktemp -d)"
cd "$workdir"
curl -sSL -o igc-core.deb   "${IGC}/intel-igc-core-2_${INTEL_IGC_VER}%2B${INTEL_IGC_BUILD}_amd64.deb"
curl -sSL -o igc-opencl.deb "${IGC}/intel-igc-opencl-2_${INTEL_IGC_VER}%2B${INTEL_IGC_BUILD}_amd64.deb"
curl -sSL -o gmm.deb        "${CR}/libigdgmm12_${INTEL_GMM_VER}_amd64.deb"
curl -sSL -o opencl-icd.deb "${CR}/intel-opencl-icd_${INTEL_CR_VER}-0_amd64.deb"
curl -sSL -o ze-gpu.deb     "${CR}/libze-intel-gpu1_${INTEL_CR_VER}-0_amd64.deb"
dpkg -i ./*.deb

cd /
rm -rf "$workdir" /var/lib/apt/lists/*
