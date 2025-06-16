#!/bin/bash
# ==============================================================================
# Copyright (C) 2024-2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
set -euxo pipefail

echo "Installing dependencies"
sudo apt-get update
sudo apt-get install -y wget vainfo xz-utils python3-pip python3-gi gcc-multilib libglib2.0-dev \
flex bison autoconf automake libtool libogg-dev make g++ libva-dev yasm libglx-dev libdrm-dev \
python-gi-dev python3-dev libtbb12 gpg unzip libopencv-dev libgflags-dev \
libgirepository1.0-dev libx265-dev libx264-dev libde265-dev gudev-1.0 libusb-1.0 nasm python3-venv \
libcairo2-dev libxt-dev libgirepository1.0-dev libgles2-mesa-dev wayland-protocols libcurl4-openssl-dev \
libssh2-1-dev cmake git valgrind numactl libvpx-dev libopus-dev libsrtp2-dev libxv-dev \
linux-libc-dev libpmix2t64 libhwloc15 libhwloc-plugins libxcb1-dev libx11-xcb-dev gnupg

echo "Setting up a Python environment"
python3 -m venv python3venv
source python3venv/bin/activate
pip install --upgrade pip==24.0
pip install meson==1.4.1 ninja==1.11.1.1

echo "Build ffmpeg"
mkdir -p ffmpeg
wget --no-check-certificate https://ffmpeg.org/releases/ffmpeg-6.1.1.tar.gz -O ffmpeg/ffmpeg-6.1.1.tar.gz
tar -xf ffmpeg/ffmpeg-6.1.1.tar.gz -C ffmpeg
rm ffmpeg/ffmpeg-6.1.1.tar.gz

cd ffmpeg/ffmpeg-6.1.1
./configure --enable-pic --enable-shared --enable-static --enable-avfilter --enable-vaapi \
    --extra-cflags="-I/include" --extra-ldflags="-L/lib" --extra-libs=-lpthread --extra-libs=-lm --bindir="/bin"
make -j "$(nproc)"
sudo make install
cd ../../

echo "Build gstreamer"
git clone https://gitlab.freedesktop.org/gstreamer/gstreamer.git
cd gstreamer
git checkout tags/1.26.1 -b 1.26.1
export PKG_CONFIG_PATH=/usr/local/lib/pkgconfig
meson setup -Dexamples=disabled -Dtests=disabled -Dvaapi=enabled -Dgst-examples=disabled --buildtype=release --prefix=/opt/intel/dlstreamer/gstreamer --libdir=lib/ --libexecdir=bin/ build/
ninja -C build
sudo env PATH="$PWD/../python3venv/bin:$PATH" meson install -C build/
cd ..

echo "Build OpenCV"
wget --no-check-certificate -O opencv.zip https://github.com/opencv/opencv/archive/4.10.0.zip
unzip opencv.zip -d .
rm opencv.zip
mv opencv-4.10.0 opencv
mkdir -p opencv/build
cd opencv/build
cmake -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_opencv_apps=OFF -GNinja ..
ninja -j "$(nproc)"
sudo env PATH="$PWD/../../python3venv/bin:$PATH" ninja install
cd ../../

echo "Install OpenVINO Toolkit"
wget https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB
sudo gpg --output /etc/apt/trusted.gpg.d/intel.gpg --dearmor GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB
echo "deb https://apt.repos.intel.com/openvino ubuntu24 main" | sudo tee /etc/apt/sources.list.d/intel-openvino.list
sudo apt update
sudo apt install openvino-2025.1.0

echo "Install metapublish dependencies"
cd libraries/dl-streamer
sudo ./scripts/install_metapublish_dependencies.sh

echo "Build DLStreamer"
mkdir -p build
cd build
export PKG_CONFIG_PATH="/opt/intel/dlstreamer/gstreamer/lib/pkgconfig:${PKG_CONFIG_PATH}"
cmake -DENABLE_PAHO_INSTALLATION=ON -DENABLE_RDKAFKA_INSTALLATION=ON -DENABLE_VAAPI=ON -DENABLE_SAMPLES=ON ..
make -j "$(nproc)"
