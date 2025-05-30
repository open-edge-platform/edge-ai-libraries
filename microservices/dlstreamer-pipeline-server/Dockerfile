#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

# Specify all Docker arguments for the Dockerfile
ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE} AS dlstreamer-pipeline-server
LABEL description="DL Streamer Pipeline Server"
LABEL vendor="Intel Corporation"

ARG DLSTREAMER_VERSION=2025.0.1.2

SHELL ["/bin/bash", "-xo", "pipefail", "-c"]

RUN \
    apt-get update && \
    apt-get install -y -q --no-install-recommends gnupg=\* ca-certificates=\* wget=\* libtbb-dev=\* cmake=\* git=\* git-lfs=\* vim=\* numactl=\* && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Intel® NPU drivers (optional)
RUN export no_proxy= && \
    mkdir debs && \
    dpkg --purge --force-remove-reinstreq intel-driver-compiler-npu intel-fw-npu intel-level-zero-npu level-zero && \
    wget -q https://github.com/oneapi-src/level-zero/releases/download/v1.17.44/level-zero_1.17.44+u22.04_amd64.deb -P ./debs && \
    wget -q --no-check-certificate -nH --accept-regex="ubuntu22" --cut-dirs=5 -r https://github.com/intel/linux-npu-driver/releases/expanded_assets/v1.13.0 -P ./debs && \
    apt-get install -y -q --no-install-recommends ./debs/*.deb && \
    rm -r -f debs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -f /etc/ssl/certs/Intel*

# Intel® Data Center GPU Flex Series drivers (optional)
# hadolint ignore=SC1091
RUN export no_proxy= && \
    apt-get update && \
    . /etc/os-release && \
    if [[ ! "jammy" =~ ${VERSION_CODENAME} ]]; then \
        echo "Ubuntu version ${VERSION_CODENAME} not supported"; \
    else \
        wget --no-check-certificate -qO- https://repositories.intel.com/gpu/intel-graphics.key | gpg --dearmor --output /usr/share/keyrings/gpu-intel-graphics.gpg && \
        echo "deb [arch=amd64 signed-by=/usr/share/keyrings/gpu-intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu jammy client" | \
        tee /etc/apt/sources.list.d/intel-gpu-"${VERSION_CODENAME}".list && \
        apt-get update; \
    fi && \
    apt-get install -y --no-install-recommends \
    intel-opencl-icd=\* ocl-icd-opencl-dev=\* intel-level-zero-gpu=\* level-zero=\* \
    libmfx1=\* libmfxgen1=\* libvpl2=\* intel-media-va-driver-non-free=\* \
    libgbm1=\* libigdgmm12=\* libxatracker2=\* libdrm-amdgpu1=\* \
    va-driver-all=\* vainfo=\* hwinfo=\* clinfo=\* && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN export no_proxy= && \
    echo "deb https://apt.repos.intel.com/openvino/2025 ubuntu22 main" | tee /etc/apt/sources.list.d/intel-openvino-2025.list && \
    wget -q https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB && \
    apt-key add GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB && \
    wget -q -O- https://eci.intel.com/sed-repos/gpg-keys/GPG-PUB-KEY-INTEL-SED.gpg | tee /usr/share/keyrings/sed-archive-keyring.gpg > /dev/null && \
    echo "deb [signed-by=/usr/share/keyrings/sed-archive-keyring.gpg] https://eci.intel.com/sed-repos/jammy sed main" | tee /etc/apt/sources.list.d/sed.list && \
    echo "deb-src [signed-by=/usr/share/keyrings/sed-archive-keyring.gpg] https://eci.intel.com/sed-repos/jammy sed main" | tee -a /etc/apt/sources.list.d/sed.list && \
    bash -c 'echo -e "Package: *\nPin: origin eci.intel.com\nPin-Priority: 1000" > /etc/apt/preferences.d/sed'

ARG DEBIAN_FRONTEND=noninteractive

RUN export no_proxy= && \
    apt-get update -y && \
    apt-get install -y -q --no-install-recommends intel-dlstreamer=${DLSTREAMER_VERSION} && \
    apt-get clean -y && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -ms /bin/bash dlstreamer && \
    chown -R dlstreamer: /opt && \
    chmod -R u+rw /opt

RUN \
    mkdir /python3venv && \
    chown -R dlstreamer: /python3venv && \
    chmod -R u+w /python3venv

ENV LIBVA_DRIVER_NAME=iHD
ENV GST_PLUGIN_PATH=/opt/intel/dlstreamer/build/intel64/Release/lib:/opt/intel/dlstreamer/gstreamer/lib/gstreamer-1.0:/opt/intel/dlstreamer/gstreamer/lib/:
ENV LD_LIBRARY_PATH=/opt/intel/dlstreamer/gstreamer/lib:/opt/intel/dlstreamer/build/intel64/Release/lib:/opt/intel/dlstreamer/lib/gstreamer-1.0:/usr/lib:/opt/intel/dlstreamer/build/intel64/Release/lib:/opt/opencv:/opt/openh264:/opt/rdkafka:/opt/ffmpeg:/usr/local/lib/gstreamer-1.0:/usr/local/lib
ENV LIBVA_DRIVERS_PATH=/usr/lib/x86_64-linux-gnu/dri
ENV GST_VA_ALL_DRIVERS=1
ENV MODEL_PROC_PATH=/opt/intel/dlstreamer/samples/gstreamer/model_proc
ENV PATH=/python3venv/bin:/opt/intel/dlstreamer/gstreamer/bin:/opt/intel/dlstreamer/build/intel64/Release/bin:$PATH
ENV PYTHONPATH=/opt/intel/dlstreamer/gstreamer/lib/python3/dist-packages:/opt/intel/dlstreamer/python:/opt/intel/dlstreamer/gstreamer/lib/python3/dist-packages
ENV TERM=xterm
ENV GI_TYPELIB_PATH=/opt/intel/dlstreamer/gstreamer/lib/girepository-1.0:/usr/lib/x86_64-linux-gnu/girepository-1.0

RUN \
    usermod -a -G video dlstreamer && \
    ln -s /opt/intel/dlstreamer /home/dlstreamer/dlstreamer

WORKDIR /home/dlstreamer
USER dlstreamer

RUN \
    python3 -m venv /python3venv && \
    /python3venv/bin/pip3 install --no-cache-dir --upgrade pip && \
    /python3venv/bin/pip3 install --no-cache-dir --no-dependencies PyGObject==3.50.0 setuptools==75.8.0

# DL Streamer Runtime ends

######################## DL Streamer Pipeline Server builder ################################

ENV DLSTREAMER_DIR=/opt/intel/dlstreamer
ENV GSTREAMER_DIR=$DLSTREAMER_DIR/gstreamer

USER root

WORKDIR /home/pipeline-server

RUN export no_proxy= && \
    apt-get update --allow-releaseinfo-change && apt-get install -y --no-install-recommends git autoconf  \
    automake \
    libglib2.0-dev \
    libusb-1.0-0-dev \
    libtool \
    zlib1g-dev \
    make \
    zip \
    unzip \
    libopencv-dev \
    libcjson-dev && \
    rm -rf /var/lib/apt/lists/*


RUN apt-get update && apt-get install -y --no-install-recommends wget && \
    wget -qO- https://cmake.org/files/v3.15/cmake-3.15.0-Linux-x86_64.tar.gz | \
    tar --strip-components=1 -xz -C /usr/local

ARG CMAKE_INSTALL_PREFIX
ARG UTILS_LIB_VERSION
ARG MSGBUS_LIB_VERSION

COPY packages/eii-utils-${UTILS_LIB_VERSION}-Linux.deb ${WORKDIR}
COPY packages/util-${UTILS_LIB_VERSION}.zip ${WORKDIR}

COPY packages/eii-messagebus-${MSGBUS_LIB_VERSION}-Linux.deb ${WORKDIR}
COPY packages/UDFLoader.zip ${WORKDIR}
COPY packages/udfs.zip ${WORKDIR}

# Installation of utils, eiimessagebus and debian packages. Needed for UDFLoader build
RUN dpkg -i /home/pipeline-server/eii-utils-${UTILS_LIB_VERSION}-Linux.deb && \
    dpkg -i /home/pipeline-server/eii-messagebus-${MSGBUS_LIB_VERSION}-Linux.deb && \
    rm -rf eii-*.deb

RUN unzip UDFLoader.zip -d /home/pipeline-server && \
    unzip udfs.zip -d /home/pipeline-server && \
    unzip util-${UTILS_LIB_VERSION}.zip -d /home/pipeline-server && \
    rm -rf udfs.zip UDFLoader.zip util-*.zip

COPY ./plugins/gst-udf-loader/ /home/pipeline-server/gst-udf-loader

RUN apt-get install -y --no-install-recommends python3-dev

# Build UDF loader lib
RUN /bin/bash -c "echo $PATH && \
                  pip3 install numpy==1.26.4 && \
                  pip3 install Cython==0.29.34 && \
                  cd /home/pipeline-server/UDFLoader && \
                  rm -rf build && \
                  mkdir build && \
                  cd build && \
                  cmake -DCMAKE_INSTALL_INCLUDEDIR=$CMAKE_INSTALL_PREFIX/include -DCMAKE_INSTALL_PREFIX=$CMAKE_INSTALL_PREFIX -DWITH_TESTS=${RUN_TESTS} -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE} \
                  .. && \
                  make && \
                  if [ "${RUN_TESTS}" = "ON" ] ; then \
                     cd ./tests && \
                     source ./source.sh && \
                     ./frame-tests && \
                     ./udfloader-tests && \
                     cd .. ; \
                  fi && \
                  make install"

ENV LD_LIBRARY_PATH=${CMAKE_INSTALL_PREFIX}/lib:${CMAKE_INSTALL_PREFIX}/lib/udfs:${DLSTREAMER_DIR}/lib:${DLSTREAMER_DIR}/lib/gstreamer-1.0:${LD_LIBRARY_PATH}:/root/.local/bin \
    LIBRARY_PATH=/opt/intel/dlstreamer/gstreamer/lib/:${LIBRARY_PATH} \
    CPLUS_INCLUDE_PATH=${CPLUS_INCLUDE_PATH}:${DLSTREAMER_DIR}/include/dlstreamer/gst/videoanalytics:${DLSTREAMER_DIR}/include/dlstreamer/gst/metadata:/root/.local/bin:${DLSTREAMER_DIR}/gstreamer/include/gstreamer-1.0/ \
    C_INCLUDE_PATH=${C_INCLUDE_PATH}:${DLSTREAMER_DIR}/gstreamer/include/gstreamer-1.0/ \
    PYTHONPATH=$PYTHONPATH:/usr/local/lib/:/root/.local/bin \
    PATH=${DLSTREAMER_DIR}/gstreamer/bin:${DLSTREAMER_DIR}/gstreamer/bin/gstreamer-1.0:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/root/.local/bin \
    PKG_CONFIG_PATH=/usr/share/pkgconfig:/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/lib/pkgconfig:/opt/intel/dlstreamer/gstreamer/lib/pkgconfig:/opt/intel/dlstreamer/build/intel64/Release/lib/pkgconfig:

RUN export no_proxy= && \
    apt-get update && \
    apt-get install -y -q --no-install-recommends libdrm-dev=\* && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Build gst-udf-loader plugin
RUN /bin/bash -c "cd /home/pipeline-server/gst-udf-loader/ \
    && if [ -d \"build\" ] ; then rm -rf build ; fi \
    && mkdir build \
    && cd gst_plugin && sed -i '/dlstreamer_gst_meta/c\\\t/opt/intel/dlstreamer/build/intel64/Release/lib/libdlstreamer_gst_meta.so' CMakeLists.txt && cd .. \
    && cd build \
    && cmake -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE} -DCMAKE_INSTALL_INCLUDEDIR=${CMAKE_INSTALL_PREFIX}/include -DCMAKE_INSTALL_PREFIX=${CMAKE_INSTALL_PREFIX} .. \
    && make"

############################# DL Streamer Pipeline Server runtime ################################

USER root

WORKDIR /home/pipeline-server

ENV DEBIAN_FRONTEND=noninteractive
ENV LD_RUN_PATH="/usr/lib"
ENV LIBRARY_PATH=$LD_RUN_PATH:$LIBVA_DRIVERS_PATH
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$LIBVA_DRIVERS_PATH:"usr/local/lib"
ENV PKG_CONFIG_PATH="/usr/lib/x86_64-linux-gnu/pkgconfig"
ENV TERM="xterm"
ENV GST_DEBUG="1"

ARG CMAKE_INSTALL_PREFIX

RUN cp ${CMAKE_INSTALL_PREFIX}/lib/libeiiudfloader.so ${DLSTREAMER_DIR}/gstreamer/lib
RUN cp /home/pipeline-server/gst-udf-loader/build/gst_plugin/libgstudfloader.so ${DLSTREAMER_DIR}/gstreamer/lib

ARG USER
ARG UID

RUN useradd -ms /bin/bash -G video,audio,users,plugdev ${USER} -o -u $UID && \
    chown ${USER}:${USER} -R /home/pipeline-server /root

RUN mkdir -p /home/${USER}/ && chown -R ${USER}:${USER} /home/${USER}

ENV cl_cache_dir=/home/.cl_cache \
    XDG_RUNTIME_DIR=/home/.xdg_runtime_dir \
    LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/usr/local/lib:/home/pipeline-server:/usr/local/lib/udfs \
    PYTHONPATH=$PYTHONPATH:/opt/intel/eii/lib:/home/pipeline-server/:/home/pipeline-server/udfs:/home/pipeline-server/server:/usr/local/lib/

RUN mkdir -p $cl_cache_dir && chmod -R g+s $cl_cache_dir && chown ${USER}:users $cl_cache_dir
ENV XDG_RUNTIME_DIR=/home/.xdg_runtime_dir
RUN mkdir -p $XDG_RUNTIME_DIR && chmod -R g+s $XDG_RUNTIME_DIR && chown ${USER}:users $XDG_RUNTIME_DIR

ENV LD_LIBRARY_PATH ${LD_LIBRARY_PATH}:/usr/local/lib:/home/pipeline-server:${CMAKE_INSTALL_PREFIX}/lib:${CMAKE_INSTALL_PREFIX}/lib/udfs

### To install other/newer Genicam camera SDKs add the installation steps here

RUN apt-get update && apt-get install -y --no-install-recommends git

ENV PATH=$PATH:/home/pipeline-server/.local/bin

COPY ./tests/requirements.txt /home/pipeline-server/tests/requirements.txt
RUN pip3 install -r /home/pipeline-server/tests/requirements.txt

# Install for ntp timestamping
RUN pip3 install ntplib==0.4.0

#Patch and install OpenVINO model api
COPY ./docker/model_api.patch /home/pipeline-server/model_api.patch
RUN pip3 install openvino-model-api==0.2.5
RUN cd /usr/local/lib/python3.10/dist-packages/model_api && \
    git apply /home/pipeline-server/model_api.patch   

# Install Geti SDK
RUN pip3 install geti-sdk==2.7.1

# Uninstall cuda-python installed by Geti SDK because of proprietary license causing OSPDT issue
RUN pip3 uninstall -y cuda-python aiohappyeyeballs

# Install schedule for python job scheduling
RUN pip3 install schedule==1.2.1

# Install opcua
RUN pip3 install asyncua==1.1.5

# Downgrading Flask due to an atttribute error(JSONEncoder)
RUN pip3 uninstall -y Flask && \
    pip3 install Flask==2.2.5

# Visualizer webtrc requirements
RUN apt-get update && apt-get install libnice10 libnice-dev -y --no-install-recommends
#RUN cp /usr/lib/x86_64-linux-gnu/gstreamer-1.0/libgstnice.so /opt/intel/dlstreamer/lib/gstreamer-1.0

WORKDIR /thirdparty

USER root
RUN pip3 install pydantic==2.8.2

RUN apt-get update && apt-get install libxtst6 -y --no-install-recommends
RUN pip3 install deep_sort_realtime

ARG DOWNLOAD_GPL_SOURCES

ARG UBUNTU_COPYLEFT_DEPS=""

ARG PYTHON_COPYLEFT_DEPS="https://git.launchpad.net/launchpadlib \
                          https://github.com/GNOME/pygobject \
                          https://github.com/FreeOpcUa/opcua-asyncio \
                          https://github.com/Lucretiel/autocommand \
                          https://github.com/certifi/python-certifi \
                          https://git.launchpad.net/wadllib \
                          https://git.launchpad.net/ubuntu/+source/python-apt \
                          https://git.launchpad.net/lazr.restfulclient \
                          https://git.launchpad.net/lazr.uri"

ARG PYTHON_NO_REPO_SOURCE="https://files.pythonhosted.org/packages/32/12/0409b3992c9a023d1521d9352d4c41bb1d43684ccb82899e716103e2bd88/bubblewrap-1.2.0.zip"

COPY ./thirdparty/third_party_deb_apk_deps.txt /thirdparty/
COPY ./thirdparty/third_party_programs.txt /thirdparty/

RUN if [ "$DOWNLOAD_GPL_SOURCES" = "yes" ]; then \
        sed -Ei 's/# deb-src /deb-src /' /etc/apt/sources.list && \
        apt-get update && \
        root_dir=$PWD && \
        mkdir -p ./apt-sources/dlstreamer-pipeline-server && cd ./apt-sources/dlstreamer-pipeline-server && \
        cp ../../third_party_deb_apk_deps.txt . && \
        for line in $(cat third_party_deb_apk_deps.txt | xargs -n1); \
        do \
        package=$(echo $line); \
        grep -l GPL /usr/share/doc/${package}/copyright; \
        exit_status=$?; \
        if [ $exit_status -eq 0 ]; then \
            apt-get source -q --download-only $package;  \
        fi \
        done && \
        cd $root_dir && \
        echo "Cloning Debian and Ubuntu github deps..." && \
        mkdir -p ./github-sources/Ubuntu_Deb && cd ./github-sources/Ubuntu_Deb && \
        for f in `echo $UBUNTU_COPYLEFT_DEPS | xargs -n1`; do git clone $f && \
        cd "$(basename "$f")" && \
        rm -rf .git && \
        cd ..; done && \
        cd ../ && \
        mkdir -p Python && cd Python && \
        echo "Cloning Python github dependency" && \
        for f in `echo $PYTHON_COPYLEFT_DEPS | xargs -n1`; do git clone $f && \
        wget $PYTHON_NO_REPO_SOURCE && \
        cd "$(basename "$f")" && \
        rm -rf .git && \
        cd ..; done && \
        cd $root_dir && \
        echo "Download source for $(ls | wc -l) third-party packages: $(du -sh)"; \
        rm -rf /var/lib/apt/lists/*;\
    fi


WORKDIR /home/pipeline-server

USER $USER

# Install gRPC
COPY packages/gRPC-py-2.0.0.zip ${WORKDIR}
RUN mkdir -p grpc && unzip -o gRPC-py-2.0.0.zip -d grpc && \
    rm -rf gRPC-py-2.0.0.zip

RUN pip3 install --no-cache-dir grpcio==1.66.0 grpcio-tools==1.66.0

# Copy source code
COPY ./docker/run.sh .
COPY ./utils/*.py ./utils/
COPY ./src/ ./src

# Install server requirements
USER root
RUN pip3 install PyYAML==5.4.1 --no-build-isolation && \
    pip3 install -r  /home/pipeline-server/src/server/requirements.service.txt \
                 -r /home/pipeline-server/src/server/requirements.webrtc.txt \
                 -r /home/pipeline-server/src/server/requirements.txt && \
    python3 -m pip install --upgrade Werkzeug==3.1.3 orjson==3.10.12 packaging==24.2 boto3==1.36.17 influxdb-client==1.48.0 marshmallow==4.0.0
USER ${USER}

# OpenTelemetry
USER root
RUN pip3 install --no-cache -r  /home/pipeline-server/src/opentelemetry/requirements.txt
RUN pip3 install --upgrade opentelemetry-exporter-otlp
USER ${USER}

# Disable OpenVINO Telemetry
RUN opt_in_out --opt_out

# Create Models directory
RUN mkdir -p /home/pipeline-server/models

# Copy python UDFs for user_defined_pipelines/udfloader_sample pipeline
COPY ./user_scripts/udfs/python/dummy.py /home/pipeline-server/udfs/python/dummy.py
COPY ./user_scripts/udfs/python/add_label.py /home/pipeline-server/udfs/python/add_label.py
COPY ./user_scripts/udfs/python/dummy_publisher.py /home/pipeline-server/udfs/python/dummy_publisher.py
COPY ./user_scripts/udfs/python/geti_udf/ /home/pipeline-server/udfs/python/geti_udf/

# Copy unit tests
COPY ./tests /home/pipeline-server/tests

# Copy geti pallet defect detection sample
COPY ./resources/models/geti /home/pipeline-server/resources/models/geti
COPY ./resources/videos/classroom.avi /home/pipeline-server/resources/videos/classroom.avi
COPY ./resources/videos/warehouse.avi /home/pipeline-server/resources/videos/warehouse.avi
COPY ./resources/videos/person-bicycle-car-detection.mp4 /home/pipeline-server/resources/videos/person-bicycle-car-detection.mp4
#COPY ./pipelines/user_defined_pipelines/person_detection /home/pipeline-server/pipelines/user_defined_pipelines/person_detection

# Copy GVAPYTHON samples
COPY ./user_scripts/gvapython/geti/ /home/pipeline-server/gvapython/geti
COPY ./user_scripts/gvapython/mqtt_publisher/ /home/pipeline-server/gvapython/mqtt_publisher
COPY ./user_scripts/gvapython/timestamp/ /home/pipeline-server/gvapython/timestamp
COPY ./user_scripts/gvapython/gva_event_meta /home/pipeline-server/gvapython/gva_event_meta

# Copy default config
COPY ./configs/default/config.json /home/pipeline-server/config.json

ENV PYTHONPATH=$PYTHONPATH:/home/pipeline-server/udfs/python/geti_udf
ENV PYTHONPATH $PYTHONPATH:/home/pipeline-server/grpc:/home/pipeline-server/grpc/protos

ENTRYPOINT ["./run.sh"]
