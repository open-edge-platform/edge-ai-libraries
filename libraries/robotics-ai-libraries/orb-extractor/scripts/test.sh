#!/bin/bash
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: Apache-2.0
set -e

echo "=== Phase 1: OpenCV-Free Tests (Packaged Version) ==="
echo "Setting up repositories and dependencies..."

if [ "${ROS_DISTRO}" == "jazzy" ]; then
    apt-get update
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:kobuk-team/intel-graphics
else
    curl https://repositories.intel.com/gpu/intel-graphics.key | gpg --yes --dearmor --output /usr/share/keyrings/intel-graphics.gpg
    echo "deb [arch=amd64,i386 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu jammy unified" | \
        tee /etc/apt/sources.list.d/intel-gpu-jammy.list
	echo "deb [trusted=yes] http://wheeljack.ch.intel.com/apt-repos/ECI/jammy isar main" > /etc/apt/sources.list.d/amr.list
	echo "deb-src [trusted=yes] http://wheeljack.ch.intel.com/apt-repos/ECI/jammy isar main" >> /etc/apt/sources.list.d/amr.list
    apt update
fi

curl https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | gpg --yes --dearmor --output /usr/share/keyrings/oneapi-archive-keyring.gpg
echo 'deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main' | tee /etc/apt/sources.list.d/oneAPI.list

apt-get update

# Install build dependencies required by debian/control
echo "Installing build dependencies..."
apt-get install -y \
    debhelper \
    pkg-config \
    cmake \
    libze-dev \
    intel-opencl-icd \
    libopencv-dev \
    libgtest-dev \
    intel-oneapi-base-toolkit

# Build the packages
echo "Building packages..."
# Clean any existing debian directory and copy the correct one for this ROS distro
rm -rf ./debian
cp -r "./${ROS_DISTRO}/debian" ./debian
# Build from root directory where CMakeLists.txt exists
dpkg-buildpackage
# Move packages to current directory
mv ../*.deb .

# Install the built packages
echo "Installing built packages..."
DEBIAN_FRONTEND=noninteractive apt install -y -f ./liborb-lze*.deb ./orb-extractor-lze-test_*.deb

# Source Intel oneAPI environment to make SYCL runtime available
if [ -f "/opt/intel/oneapi/setvars.sh" ]; then
    # shellcheck source=/dev/null
    . "/opt/intel/oneapi/setvars.sh"
fi

cd /opt/intel/orb_lze/tests/

echo "Running OpenCV-free tests..."
opencv_free_tests=(opencvfreeTest resizeTest)

for test in "${opencv_free_tests[@]}"; do
    echo "Running $test..."
    if ! "./$test" | tee "/tmp/orb_${test}_test.log" || grep -q "FAILED" "/tmp/orb_${test}_test.log"; then
        echo "❌ $test failed!"
        exit 1
    fi
    echo "✅ $test passed"
done

echo ""
echo "✅ Phase 1 complete: OpenCV-free tests passed"
echo ""

# Phase 2: Build and run OpenCV-dependent tests
echo "=== Phase 2: OpenCV Tests (Full Development Version) ==="

cd /src/tests
mkdir -p build-opencv
cd build-opencv

echo "Building OpenCV tests..."
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo -DENABLE_OPENCV_TESTS=ON
make -j"$(nproc)"

echo "Running OpenCV tests..."
opencv_tests=(fastTest gaussTest stereoTest orbdescTest imagemaskTest rectmaskTest multicameraTest multithreadTest)

for test in "${opencv_tests[@]}"; do
    echo "Running $test..."
    if ! "./$test" | tee "/tmp/orb_${test}_opencv_test.log" || grep -q "FAILED" "/tmp/orb_${test}_opencv_test.log"; then
        echo "❌ $test failed!"
        exit 1
    fi
    echo "✅ $test passed"
done

echo ""
echo "🎉 All tests passed! Both OpenCV-free and OpenCV modes validated."
