# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

FROM ubuntu:24.04 AS base

ARG DEBIAN_FRONTEND=noninteractive
ARG BUILD_ARG=Release

LABEL description="This is the development image of Intel® Deep Learning Streamer (Intel® DL Streamer) Pipeline Framework"
LABEL vendor="Intel Corporation"

ARG GST_VERSION=1.26.1
ARG FFMPEG_VERSION=6.1.1

ARG OPENVINO_VERSION=2025.1.0

ENV DLSTREAMER_DIR=/home/dlstreamer/dlstreamer
ENV GSTREAMER_DIR=/opt/intel/dlstreamer/gstreamer
ENV INTEL_OPENVINO_DIR=/opt/intel/openvino_$OPENVINO_VERSION.0
ENV LIBVA_DRIVERS_PATH=/usr/lib/x86_64-linux-gnu/dri
ENV LIBVA_DRIVER_NAME=iHD
ENV GST_VA_ALL_DRIVERS=1

SHELL ["/bin/bash", "-xo", "pipefail", "-c"]

RUN userdel -r ubuntu

COPY scripts/DLS_install_prerequisites.sh /DLS_install_prerequisites.sh

RUN \
    chmod +x /DLS_install_prerequisites.sh && \
    /DLS_install_prerequisites.sh --on-host-or-docker=docker_ubuntu24 && \
    rm -f /DLS_install_prerequisites.sh && \
    apt-get update && \
    apt-get install -y -q --no-install-recommends libgirepository1.0-dev=\* libcairo2-dev=\* g++=\* \
    python3-pip=\* python3-gi=\* python-gi-dev=\* python3-dev=\* python3-venv=\* \
    libdrm2=\* libva2=\* libva-drm2=\* libgudev-1.0-0=\* libopus0=\* libsrtp2-1=\* \ 
    libogg0=\* libx265-199=\* libx264-164=\* libde265-0=\* libvpx9=\* \
    libjack0=\* libwayland-client0=\* libxv1=\*

RUN \
    useradd -ms /bin/bash dlstreamer && \
    mkdir /python3venv && \
    chown dlstreamer: /python3venv && \
    chmod u+w /python3venv

USER dlstreamer

RUN \
    python3 -m venv /python3venv && \
    /python3venv/bin/pip3 install --no-cache-dir --upgrade pip==24.0 && \
    /python3venv/bin/pip3 install --no-cache-dir --no-dependencies \
    meson==1.4.1 \
    ninja==1.11.1.1 \
    numpy==2.2.0 \
    tabulate==0.9.0 \
    tqdm==4.67.1 \
    junit-xml==1.9 \
    opencv-python==4.11.0.86 \
    XlsxWriter==3.2.0 \
    zxing-cpp==2.2.0 \
    pyzbar==0.1.9 \
    six==1.16.0 \
    pycairo==1.26.0 \
    PyGObject==3.50.0 \
    setuptools==78.1.1 \
    pytest==8.3.3 \
    pluggy==1.5.0 \
    exceptiongroup==1.2.2 \
    iniconfig==2.0.0

ENV PATH="/python3venv/bin:${PATH}"

USER root

FROM base AS builder

RUN \
    apt-get install -y -q --no-install-recommends wget=\* xz-utils=\* gcc-multilib=\* libglib2.0-dev=\* \
    flex=\* bison=\* autoconf=\* automake=\* libtool=\* libogg-dev=\* make=\* libva-dev=\* yasm=\* libglx-dev=\* libdrm-dev=\* \
    libtbb12=\* gpg=\* unzip=\* libgflags-dev=\* libusb-1.0=\* nasm=\* gudev-1.0=\* libde265-dev=\* libx265-dev=\* \
    libx264-dev=\* libxt-dev=\* libgles2-mesa-dev=\* wayland-protocols=\* libcurl4-openssl-dev=\* libssh2-1-dev=\* \
    cmake=\* git=\* valgrind=\* numactl=\* libvpx-dev=\* libopus-dev=\* libsrtp2-dev=\* libxv-dev=\* \
    linux-libc-dev=\* libpmix2t64=\* libhwloc15=\* libhwloc-plugins=\* libxcb1-dev=\* libx11-xcb-dev=\* && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*


FROM builder AS ffmpeg-builder
#Build ffmpeg
RUN \
    mkdir -p /src/ffmpeg && \
    wget -q --no-check-certificate https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.gz -O /src/ffmpeg/ffmpeg-${FFMPEG_VERSION}.tar.gz && \
    tar -xf /src/ffmpeg/ffmpeg-${FFMPEG_VERSION}.tar.gz -C /src/ffmpeg && \
    rm /src/ffmpeg/ffmpeg-${FFMPEG_VERSION}.tar.gz

WORKDIR /src/ffmpeg/ffmpeg-${FFMPEG_VERSION}

RUN \
    ./configure \
    --enable-pic \
    --enable-shared \
    --enable-static \
    --enable-avfilter \
    --enable-vaapi \
    --extra-cflags="-I/include" \
    --extra-ldflags="-L/lib" \
    --extra-libs=-lpthread \
    --extra-libs=-lm \
    --bindir="/bin" && \
    make -j "$(nproc)" && \
    make install

WORKDIR /copy_libs
RUN cp -a /usr/local/lib/libav* ./
RUN cp -a /usr/local/lib/libswscale* ./
RUN cp -a /usr/local/lib/libswresample* ./

FROM ffmpeg-builder AS gstreamer-builder

#Build GStreamer
WORKDIR /home/dlstreamer

RUN \
    git clone https://gitlab.freedesktop.org/gstreamer/gstreamer.git

WORKDIR /home/dlstreamer/gstreamer

RUN \
    git switch -c "$GST_VERSION" "tags/$GST_VERSION" && \
    meson setup \
    -Dexamples=disabled \
    -Dtests=disabled \
    -Dvaapi=enabled \
    -Dlibnice=enabled \
    -Dgst-examples=disabled \
    -Ddevtools=disabled \
    -Dorc=disabled \
    -Dgpl=enabled \
    -Dgst-plugins-base:nls=disabled \
    -Dgst-plugins-base:gl=disabled \
    -Dgst-plugins-base:xvideo=enabled \
    -Dgst-plugins-base:vorbis=enabled \
    -Dgst-plugins-base:pango=disabled \
    -Dgst-plugins-good:nls=disabled \
    -Dgst-plugins-good:libcaca=disabled \
    -Dgst-plugins-good:vpx=enabled \
    -Dgst-plugins-good:rtp=enabled \
    -Dgst-plugins-good:rtpmanager=enabled \
    -Dgst-plugins-good:adaptivedemux2=disabled \
    -Dgst-plugins-good:lame=disabled \
    -Dgst-plugins-good:flac=disabled \
    -Dgst-plugins-good:dv=disabled \
    -Dgst-plugins-good:soup=disabled \
    -Dgst-plugins-bad:gpl=enabled \
    -Dgst-plugins-bad:va=enabled \
    -Dgst-plugins-bad:doc=disabled \
    -Dgst-plugins-bad:nls=disabled \
    -Dgst-plugins-bad:neon=disabled \
    -Dgst-plugins-bad:directfb=disabled \
    -Dgst-plugins-bad:openni2=disabled \
    -Dgst-plugins-bad:fdkaac=disabled \
    -Dgst-plugins-bad:ladspa=disabled \
    -Dgst-plugins-bad:assrender=disabled \
    -Dgst-plugins-bad:bs2b=disabled \
    -Dgst-plugins-bad:flite=disabled \
    -Dgst-plugins-bad:rtmp=disabled \
    -Dgst-plugins-bad:sbc=disabled \
    -Dgst-plugins-bad:teletext=disabled \
    -Dgst-plugins-bad:hls-crypto=openssl \
    -Dgst-plugins-bad:libde265=enabled \
    -Dgst-plugins-bad:openh264=enabled \
    -Dgst-plugins-bad:uvch264=enabled \
    -Dgst-plugins-bad:x265=enabled \
    -Dgst-plugins-bad:curl=enabled \
    -Dgst-plugins-bad:curl-ssh2=enabled \
    -Dgst-plugins-bad:opus=enabled \
    -Dgst-plugins-bad:dtls=enabled \
    -Dgst-plugins-bad:srtp=enabled \
    -Dgst-plugins-bad:webrtc=enabled \
    -Dgst-plugins-bad:webrtcdsp=disabled \
    -Dgst-plugins-bad:dash=disabled \
    -Dgst-plugins-bad:aja=disabled \
    -Dgst-plugins-bad:openjpeg=disabled \
    -Dgst-plugins-bad:analyticsoverlay=disabled \
    -Dgst-plugins-bad:closedcaption=disabled \
    -Dgst-plugins-bad:ttml=disabled \
    -Dgst-plugins-bad:codec2json=disabled \
    -Dgst-plugins-bad:qroverlay=disabled \
    -Dgst-plugins-bad:soundtouch=disabled \
    -Dgst-plugins-bad:isac=disabled \
    -Dgst-plugins-ugly:nls=disabled \
    -Dgst-plugins-ugly:x264=enabled \
    -Dgst-plugins-ugly:gpl=enabled \
    -Dgstreamer-vaapi:encoders=enabled \
    -Dgstreamer-vaapi:drm=enabled \
    -Dgstreamer-vaapi:glx=enabled \
    -Dgstreamer-vaapi:wayland=enabled \
    -Dgstreamer-vaapi:egl=enabled \
    --buildtype=${BUILD_ARG,} \
    --prefix=${GSTREAMER_DIR} \
    --libdir=lib/ \
    --libexecdir=bin/ \
    build/ && \
    ninja -C build && \
    meson install -C build/ && \
    rm -r subprojects/gst-devtools subprojects/gst-examples

ENV PKG_CONFIG_PATH="${GSTREAMER_DIR}/lib/pkgconfig:${PKG_CONFIG_PATH}"

# Installing gst-rswebrtc-plugins
ENV RUSTFLAGS="-L ${GSTREAMER_DIR}/lib"

WORKDIR $GSTREAMER_DIR/src/gst-plugins-rs
# hadolint ignore=SC1091
RUN \
    git clone https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs.git && \
    shopt -s dotglob && \
    mv gst-plugins-rs/* . && \
    git checkout 207196a0334da74c4db9db7c565d882cb9ebc07d && \
    wget -q --no-check-certificate -O- https://sh.rustup.rs | sh -s -- -y --default-toolchain 1.85.0 && \
    source "$HOME"/.cargo/env && \
    cargo install cargo-c --version=0.10.11 --locked && \
    cargo update && \
    cargo cinstall -p gst-plugin-webrtc -p gst-plugin-rtp --libdir="${GSTREAMER_DIR}"/lib/ && \
    rm "${GSTREAMER_DIR}"/lib/gstreamer-1.0/libgstrs*.a && \
    rustup self uninstall -y && \
    rm -rf ./* && \
    strip -g "${GSTREAMER_DIR}"/lib/gstreamer-1.0/libgstrs*.so

FROM builder AS opencv-builder
# OpenCV
WORKDIR /

RUN \
    wget -q --no-check-certificate -O opencv.zip https://github.com/opencv/opencv/archive/4.10.0.zip && \
    unzip opencv.zip && \
    rm opencv.zip && \
    mv opencv-4.10.0 opencv && \
    mkdir -p opencv/build

WORKDIR /opencv/build

RUN \
    cmake \
    -DBUILD_TESTS=OFF \
    -DBUILD_PERF_TESTS=OFF \
    -DBUILD_EXAMPLES=OFF \
    -DBUILD_opencv_apps=OFF \
    -GNinja .. && \
    ninja -j "$(nproc)" && \
    ninja install

WORKDIR /copy_libs
RUN cp -a /usr/local/lib/libopencv* ./

FROM builder AS dlstreamer-dev
# Intel® DL Streamer development image

COPY --from=ffmpeg-builder /copy_libs/ /usr/local/lib/
COPY --from=ffmpeg-builder /usr/local/lib/pkgconfig/libswresample* /usr/local/lib/pkgconfig/
COPY --from=ffmpeg-builder /usr/local/lib/pkgconfig/libav* /usr/local/lib/pkgconfig/
COPY --from=ffmpeg-builder /usr/local/lib/pkgconfig/libswscale* /usr/local/lib/pkgconfig/ 
COPY --from=ffmpeg-builder /usr/local/include/ /usr/local/include/ 
COPY --from=gstreamer-builder ${GSTREAMER_DIR} ${GSTREAMER_DIR}
COPY --from=opencv-builder /usr/local/include/opencv4 /usr/local/include/opencv4
COPY --from=opencv-builder /copy_libs/ /usr/local/lib/
COPY --from=opencv-builder /usr/local/lib/cmake/opencv4 /usr/local/lib/cmake/opencv4


RUN apt-get update && apt-get install -y gnupg
RUN \
    echo "deb https://apt.repos.intel.com/openvino/2025 ubuntu24 main" | tee /etc/apt/sources.list.d/intel-openvino-2025.list && \
    wget -q https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB && \
    apt-key add GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB && \
    apt-get update && apt-get install -y openvino-${OPENVINO_VERSION}
 
ENV PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/opt/intel/dlstreamer/gstreamer/lib/pkgconfig

WORKDIR "$DLSTREAMER_DIR"

COPY . "${DLSTREAMER_DIR}"

RUN \
    mkdir build && \
    ${DLSTREAMER_DIR}/scripts/install_metapublish_dependencies.sh

WORKDIR $DLSTREAMER_DIR/build


# DLStreamer environment variables
ENV LIBDIR=${DLSTREAMER_DIR}/build/intel64/${BUILD_ARG}/lib
ENV BINDIR=${DLSTREAMER_DIR}/build/intel64/${BUILD_ARG}/bin
ENV PATH=${GSTREAMER_DIR}/bin:${BINDIR}:${PATH}
ENV PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:${LIBDIR}/pkgconfig:/usr/lib/x86_64-linux-gnu/pkgconfig:${PKG_CONFIG_PATH}
ENV LIBRARY_PATH=${GSTREAMER_DIR}/lib:${LIBDIR}:/usr/lib:/usr/local/lib:${LIBRARY_PATH}
ENV LD_LIBRARY_PATH=${GSTREAMER_DIR}/lib:${LIBDIR}:/usr/lib:/usr/local/lib:${LD_LIBRARY_PATH}
ENV LIB_PATH=$LIBDIR
ENV GST_PLUGIN_PATH=${LIBDIR}:${GSTREAMER_DIR}/lib/gstreamer-1.0:/usr/lib/x86_64-linux-gnu/gstreamer-1.0:${GST_PLUGIN_PATH}
ENV LC_NUMERIC=C
ENV C_INCLUDE_PATH=${DLSTREAMER_DIR}/include:${DLSTREAMER_DIR}/include/dlstreamer/gst/metadata:${C_INCLUDE_PATH}
ENV CPLUS_INCLUDE_PATH=${DLSTREAMER_DIR}/include:${DLSTREAMER_DIR}/include/dlstreamer/gst/metadata:${CPLUS_INCLUDE_PATH}
ENV GST_PLUGIN_SCANNER=${GSTREAMER_DIR}/bin/gstreamer-1.0/gst-plugin-scanner
ENV GI_TYPELIB_PATH=${GSTREAMER_DIR}/lib/girepository-1.0
ENV PYTHONPATH=${GSTREAMER_DIR}/lib/python3/dist-packages:${DLSTREAMER_DIR}/python:${PYTHONPATH}

# Build DLStreamer
RUN \
    cmake \
    -DCMAKE_BUILD_TYPE=${BUILD_ARG} \
    -DENABLE_PAHO_INSTALLATION=ON \
    -DENABLE_RDKAFKA_INSTALLATION=ON \
    -DENABLE_VAAPI=ON \
    -DENABLE_SAMPLES=ON \
    .. && \
    make -j "$(nproc)" && \
    usermod -a -G video dlstreamer && \
    chown -R dlstreamer:dlstreamer /home/dlstreamer

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD [ "bash", "-c", "pgrep bash > /dev/null || exit 1" ]

CMD ["/bin/bash"]
