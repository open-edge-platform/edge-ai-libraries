# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

# ==============================================================================
# Build flow:
#                ubuntu:24.04
#                     |
#                     |
#                     V
#                  builder --------------------------
#                 /       \                         |
#                /         \                        |
#               V           V                       |
#      ffmpeg-builder   opencv-builder              |
#               |              |                mqqt-builder
#               V              |                    |
#       gstreamer-builder      | (copy libs)        |
#                \            /                     |
#      (copy libs)\          /                      |
#                  V        V        (copy libs)    |
#                dlstreamer-dev <-------------------|
#                      |
#                      |
#                      V
#                  deb-builder
#                      |
#                      | (copy debs)
#                      V
#                  dlstreamer
# ==============================================================================
FROM fedora:41 AS builder

ARG BUILD_ARG=Release

LABEL description="This is the development image of Intel® Deep Learning Streamer (Intel® DL Streamer) Pipeline Framework"
LABEL vendor="Intel Corporation"

ARG GST_VERSION=1.26.1
ARG FFMPEG_VERSION=6.1.1

ARG OPENVINO_VERSION=2025.1.0
ARG OPENVINO_FILENAME=openvino_toolkit_rhel8_2025.1.0.18503.6fec06580ab_x86_64

ARG DLSTREAMER_VERSION=2025.0.1.3
ARG DLSTREAMER_BUILD_NUMBER

ENV DLSTREAMER_DIR=/home/dlstreamer/dlstreamer
ENV GSTREAMER_DIR=/opt/intel/dlstreamer/gstreamer
ENV INTEL_OPENVINO_DIR=/opt/intel/openvino_$OPENVINO_VERSION
ENV LIBVA_DRIVERS_PATH=/usr/lib64/dri-nonfree
ENV LIBVA_DRIVER_NAME=iHD
ENV GST_VA_ALL_DRIVERS=1

SHELL ["/bin/bash", "-xo", "pipefail", "-c"]

RUN \
    dnf install -y \
    "https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm" \
    "https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm" && \
    dnf install -y wget libva-utils xz python3-pip python3-gobject gcc gcc-c++ glibc-devel glib2-devel \
    flex bison autoconf automake libtool libogg-devel make libva-devel yasm mesa-libGL-devel libdrm-devel \
    python3-gobject-devel python3-devel tbb gnupg2 unzip opencv-devel gflags-devel \
    gobject-introspection-devel x265-devel x264-devel libde265-devel libgudev-devel libusb1 libusb1-devel nasm python3-virtualenv \
    cairo-devel cairo-gobject-devel libXt-devel mesa-libGLES-devel wayland-protocols-devel libcurl-devel \
    libssh2-devel cmake git valgrind numactl libvpx-devel opus-devel libsrtp-devel libXv-devel \
    kernel-headers pmix pmix-devel hwloc hwloc-libs hwloc-devel libxcb-devel libX11-devel libatomic intel-media-driver && \
    dnf clean all

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

USER root

ENV PATH="/python3venv/bin:${PATH}"

# ==============================================================================
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

ENV PKG_CONFIG_PATH=/usr/local/lib/pkgconfig

WORKDIR /copy_libs
RUN cp -a /usr/local/lib/libav* ./
RUN cp -a /usr/local/lib/libswscale* ./
RUN cp -a /usr/local/lib/libswresample* ./

# ==============================================================================
FROM ffmpeg-builder AS gstreamer-builder
# hadolint
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

# ==============================================================================
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
RUN cp -a /usr/local/lib64/libopencv* ./

# ==============================================================================
FROM builder AS mqqt-builder
# Build rdkafka and Paho MQTT C client library

RUN curl -sSL https://github.com/edenhill/librdkafka/archive/v1.5.0.tar.gz | tar -xz

WORKDIR /librdkafka-1.5.0
RUN ./configure &&\
    make && make install

WORKDIR /
RUN curl -sSL https://github.com/eclipse/paho.mqtt.c/archive/v1.3.4.tar.gz | tar -xz
WORKDIR /paho.mqtt.c-1.3.4
RUN make && make install

WORKDIR /copy_libs
RUN cp -a /usr/local/lib/librdkafka* ./
RUN cp -a /usr/local/lib/libpaho-mqtt* ./

# ==============================================================================

FROM builder AS dlstreamer-dev

COPY --from=ffmpeg-builder /copy_libs/ /usr/local/lib/
COPY --from=ffmpeg-builder /usr/local/lib/pkgconfig/libswresample* /usr/local/lib/pkgconfig/
COPY --from=ffmpeg-builder /usr/local/lib/pkgconfig/libav* /usr/local/lib/pkgconfig/
COPY --from=ffmpeg-builder /usr/local/lib/pkgconfig/libswscale* /usr/local/lib/pkgconfig/ 
COPY --from=ffmpeg-builder /usr/local/include/ /usr/local/include/ 
COPY --from=gstreamer-builder ${GSTREAMER_DIR} ${GSTREAMER_DIR}
COPY --from=opencv-builder /usr/local/include/opencv4 /usr/local/include/opencv4
COPY --from=opencv-builder /copy_libs/ /usr/local/lib64/
COPY --from=opencv-builder /usr/local/lib64/cmake/opencv4 /usr/local/lib64/cmake/opencv4
COPY --from=mqqt-builder /copy_libs/ /usr/local/lib/
COPY --from=mqqt-builder /usr/local/include/librdkafka /usr/local/include/librdkafka
COPY --from=mqqt-builder /usr/local/include/MQTT* /usr/local/include/

ENV PKG_CONFIG_PATH="${GSTREAMER_DIR}/lib/pkgconfig:/usr/local/lib/pkgconfig"
# Intel® Distribution of OpenVINO™ Toolkit
RUN \
    printf "[OpenVINO]\n\
name=Intel(R) Distribution of OpenVINO\n\
baseurl=https://yum.repos.intel.com/openvino\n\
enabled=1\n\
gpgcheck=1\n\
repo_gpgcheck=1\n\
gpgkey=https://yum.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB\n" >/tmp/openvino.repo && \
    mv /tmp/openvino.repo /etc/yum.repos.d

RUN dnf install -y openvino-${OPENVINO_VERSION}


# Intel® DL Streamer
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
ENV PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:${LIBDIR}/pkgconfig:/usr/lib64/pkgconfig:${PKG_CONFIG_PATH}
ENV LIBRARY_PATH=${GSTREAMER_DIR}/lib:${LIBDIR}:/usr/lib:/usr/local/lib:${LIBRARY_PATH}
ENV LD_LIBRARY_PATH=${GSTREAMER_DIR}/lib:${LIBDIR}:/usr/lib:/usr/local/lib:${LD_LIBRARY_PATH}
ENV LIB_PATH=$LIBDIR
ENV GST_PLUGIN_PATH=${LIBDIR}:${GSTREAMER_DIR}/lib/gstreamer-1.0:/usr/lib64/gstreamer-1.0:${GST_PLUGIN_PATH}
ENV LC_NUMERIC=C
ENV C_INCLUDE_PATH=${DLSTREAMER_DIR}/include:${DLSTREAMER_DIR}/include/dlstreamer/gst/metadata:${C_INCLUDE_PATH}
ENV CPLUS_INCLUDE_PATH=${DLSTREAMER_DIR}/include:${DLSTREAMER_DIR}/include/dlstreamer/gst/metadata:${CPLUS_INCLUDE_PATH}
ENV GST_PLUGIN_SCANNER=${GSTREAMER_DIR}/bin/gstreamer-1.0/gst-plugin-scanner
ENV GI_TYPELIB_PATH=${GSTREAMER_DIR}/lib/girepository-1.0
ENV PYTHONPATH=${GSTREAMER_DIR}/lib/python3/dist-packages:${DLSTREAMER_DIR}/python:${PYTHONPATH}

# Build DLStreamer
RUN \
    if [ "${BUILD_ARG}" == "Debug" ]; then \
        C_FLAGS="-Og -g"; \
        CXX_FLAGS="-Og -g"; \
    else \
        C_FLAGS=""; \
        CXX_FLAGS=""; \
    fi && \
    cmake \
        -DCMAKE_BUILD_TYPE=${BUILD_ARG} \
        -DCMAKE_C_FLAGS="${C_FLAGS}" \
        -DCMAKE_CXX_FLAGS="${CXX_FLAGS}" \
        -DENABLE_PAHO_INSTALLATION=ON \
        -DENABLE_RDKAFKA_INSTALLATION=ON \
        -DENABLE_VAAPI=ON \
        -DENABLE_SAMPLES=ON \
        .. && \
    make -j "$(nproc)" && \
    usermod -a -G video dlstreamer && \
    chown -R dlstreamer:dlstreamer /home/dlstreamer

WORKDIR /home/dlstreamer
USER dlstreamer


FROM dlstreamer-dev AS rpm-builder

# hadolint ignore=DL3002
USER root
ENV USER=dlstreamer
ENV RPM_PKG_NAME=intel-dlstreamer-${DLSTREAMER_VERSION}

RUN \
    dnf install -y rpmdevtools patchelf && \
    dnf clean all

RUN \
    mkdir -p /${RPM_PKG_NAME}/opt/intel/ && \
    mkdir -p /${RPM_PKG_NAME}/opt/opencv/include && \
    mkdir -p /${RPM_PKG_NAME}/opt/openh264/ && \
    mkdir -p /${RPM_PKG_NAME}/opt/rdkafka && \
    mkdir -p /${RPM_PKG_NAME}/opt/ffmpeg && \
    cp -r "${DLSTREAMER_DIR}" /${RPM_PKG_NAME}/opt/intel/dlstreamer && \
    cp -rT "${GSTREAMER_DIR}" /${RPM_PKG_NAME}/opt/intel/dlstreamer/gstreamer && \
    cp /usr/lib64/libopencv*.so.410 /${RPM_PKG_NAME}/opt/opencv/ && \
    cp /usr/local/lib64/libopencv*.so.410 /${RPM_PKG_NAME}/opt/opencv/ && \
    cp "${GSTREAMER_DIR}"/lib/libopenh264.so /${RPM_PKG_NAME}/opt/openh264/libopenh264.so.7 && \
    cp /usr/local/lib/librdkafka++.so /${RPM_PKG_NAME}/opt/rdkafka/librdkafka++.so.1 && \
    cp /usr/local/lib/librdkafka.so /${RPM_PKG_NAME}/opt/rdkafka/librdkafka.so.1 && \
    find /usr/local/lib -regextype grep -regex ".*libav.*so\.[0-9]*$" -exec cp {} /${RPM_PKG_NAME}/opt/ffmpeg \; && \
    find /usr/local/lib -regextype grep -regex ".*libswscale.*so\.[0-9]*$" -exec cp {} /${RPM_PKG_NAME}/opt/ffmpeg \; && \
    find /usr/local/lib -regextype grep -regex ".*libswresample.*so\.[0-9]*$" -exec cp {} /${RPM_PKG_NAME}/opt/ffmpeg \; && \
    cp -r /usr/local/include/opencv4/* /${RPM_PKG_NAME}/opt/opencv/include && \
    cp "${DLSTREAMER_DIR}"/LICENSE /${RPM_PKG_NAME}/ && \
    rm -rf /${RPM_PKG_NAME}/opt/intel/dlstreamer/archived && \
    rm -rf /${RPM_PKG_NAME}/opt/intel/dlstreamer/docker && \
    rm -rf /${RPM_PKG_NAME}/opt/intel/dlstreamer/docs && \
    rm -rf /${RPM_PKG_NAME}/opt/intel/dlstreamer/infrastructure && \
    rm -rf /${RPM_PKG_NAME}/opt/intel/dlstreamer/tests && \
    rpmdev-setuptree && \
    tar -czf ~/rpmbuild/SOURCES/${RPM_PKG_NAME}.tar.gz -C / ${RPM_PKG_NAME} && \
    cp "${DLSTREAMER_DIR}"/docker/onebinary/fedora41/intel-dlstreamer.spec ~/rpmbuild/SPECS/ && \
    sed -i -e "s/DLSTREAMER_VERSION/${DLSTREAMER_VERSION}/g" ~/rpmbuild/SPECS/intel-dlstreamer.spec && \
    sed -i -e "s/CURRENT_DATE_TIME/$(date '+%a %b %d %Y')/g" ~/rpmbuild/SPECS/intel-dlstreamer.spec && \
    rpmbuild -bb ~/rpmbuild/SPECS/intel-dlstreamer.spec

RUN cp ~/rpmbuild/RPMS/x86_64/${RPM_PKG_NAME}* /${RPM_PKG_NAME}.${DLSTREAMER_BUILD_NUMBER}-1.fc41.x86_64.rpm

FROM fedora:41 AS dlstreamer

SHELL ["/bin/bash", "-xo", "pipefail", "-c"]

RUN \
    dnf install -y \
    "https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm" \
    "https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm" && \
    dnf clean all

RUN \
    printf "[OpenVINO]\n\
name=Intel(R) Distribution of OpenVINO\n\
baseurl=https://yum.repos.intel.com/openvino\n\
enabled=1\n\
gpgcheck=1\n\
repo_gpgcheck=1\n\
gpgkey=https://yum.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB\n" >/tmp/openvino.repo && \
    mv /tmp/openvino.repo /etc/yum.repos.d

RUN mkdir -p /rpms

COPY --from=rpm-builder /*.rpm /rpms/

# Download and install DLS rpm package
RUN \
    dnf install -y /rpms/*.rpm && \
    dnf clean all && \
    useradd -ms /bin/bash dlstreamer && \
    chown -R dlstreamer: /opt && \
    chmod -R u+rw /opt

RUN \
    mkdir /python3venv && \
    chown -R dlstreamer: /python3venv && \
    chmod -R u+w /python3venv

ENV LIBVA_DRIVER_NAME=iHD
ENV GST_PLUGIN_PATH=/opt/intel/dlstreamer/build/intel64/Release/lib:/opt/intel/dlstreamer/gstreamer/lib/gstreamer-1.0:/opt/intel/dlstreamer/gstreamer/lib/
ENV LD_LIBRARY_PATH=/opt/intel/dlstreamer/gstreamer/lib:/opt/intel/dlstreamer/build/intel64/Release/lib:/opt/intel/dlstreamer/lib/gstreamer-1.0:/usr/lib:/opt/intel/dlstreamer/build/intel64/Release/lib:/opt/opencv:/opt/openh264:/opt/rdkafka:/opt/ffmpeg:/usr/local/lib/gstreamer-1.0:/usr/local/lib
ENV LIBVA_DRIVERS_PATH=/usr/lib64/dri-nonfree
ENV GST_VA_ALL_DRIVERS=1
ENV MODEL_PROC_PATH=/opt/intel/dlstreamer/samples/gstreamer/model_proc
ENV PATH=/python3venv/bin:/opt/intel/dlstreamer/gstreamer/bin:/opt/intel/dlstreamer/build/intel64/Release/bin:$PATH
ENV PYTHONPATH=/opt/intel/dlstreamer/gstreamer/lib/python3/dist-packages:/home/dlstreamer/dlstreamer/python:/opt/intel/dlstreamer/gstreamer/lib/python3/dist-packages:
ENV TERM=xterm
ENV GI_TYPELIB_PATH=/opt/intel/dlstreamer/gstreamer/lib/girepository-1.0:/usr/lib64/girepository-1.0

RUN \
    usermod -a -G video dlstreamer && \
    ln -s /opt/intel/dlstreamer /home/dlstreamer/dlstreamer

WORKDIR /home/dlstreamer
USER dlstreamer

RUN \
    python3 -m venv /python3venv && \
    /python3venv/bin/pip3 install --no-cache-dir --upgrade pip && \
    /python3venv/bin/pip3 install --no-cache-dir --no-dependencies PyGObject==3.50.0 setuptools==78.1.1 numpy==2.2.0 tqdm==4.67.1 opencv-python==4.11.0.86

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD [ "bash", "-c", "pgrep bash > /dev/null || exit 1" ]

CMD ["/bin/bash"]
