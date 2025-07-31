ARG BASE_IMAGE=ghcr.io/open-edge-platform/edge-ai-libraries/deb-final-img-ubuntu22:candidate1407
FROM ${BASE_IMAGE} AS gstudfloader-builder

USER root

ENV DEBIAN_FRONTEND=noninteractive

ENV DLSTREAMER_DIR=/opt/intel/dlstreamer

ARG WORKDIR=/home/pipeline-server
WORKDIR ${WORKDIR}

RUN export no_proxy= && \
    apt-get update --allow-releaseinfo-change && apt-get install -y --no-install-recommends git autoconf  \
    automake \
    libgirepository1.0-dev \
    libglib2.0-dev \
    libusb-1.0-0-dev \
    libtool \
    zlib1g-dev \
    make \
    zip \
    unzip \
    libopencv-dev \
    libcjson-dev \
    python3-pip \
    python3-full \
    python-gi-dev \
    python3-dev \
    libcairo2-dev && \
    rm -rf /var/lib/apt/lists/*

RUN \
    mkdir /python3venv && \
    chmod -R u+w /python3venv

RUN \
    python3 -m venv /python3venv && \
    /python3venv/bin/pip3 install --no-cache-dir --upgrade pip && \
    /python3venv/bin/pip3 install --no-cache-dir --no-dependencies PyGObject==3.50.0 setuptools==78.1.1 numpy==2.2.0 tqdm==4.67.1 opencv-python==4.11.0.86

ENV VIRTUAL_ENV=/python3venv
ENV PATH=$VIRTUAL_ENV/bin:$PATH
ENV PYTHONPATH=${DLSTREAMER_DIR}/gstreamer/lib/python3/dist-packages:${DLSTREAMER_DIR}/python:${DLSTREAMER_DIR}/gstreamer/lib/python3/dist-packages

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
                  pip3 install --no-cache-dir numpy==1.26.4 && \
                  pip3 install --no-cache-dir Cython==0.29.34 && \
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
    LIBRARY_PATH=${DLSTREAMER_DIR}/gstreamer/lib/ \
    CPLUS_INCLUDE_PATH=${DLSTREAMER_DIR}/include/dlstreamer/gst/videoanalytics:${DLSTREAMER_DIR}/include/dlstreamer/gst/metadata:/root/.local/bin:${DLSTREAMER_DIR}/gstreamer/include/gstreamer-1.0/ \
    C_INCLUDE_PATH=${DLSTREAMER_DIR}/gstreamer/include/gstreamer-1.0/ \
    PYTHONPATH=$PYTHONPATH:/usr/local/lib/:/root/.local/bin \
    PATH=$PATH:${DLSTREAMER_DIR}/gstreamer/bin:${DLSTREAMER_DIR}/gstreamer/bin/gstreamer-1.0:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/root/.local/bin \
    PKG_CONFIG_PATH=/usr/share/pkgconfig:/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/lib/pkgconfig:${DLSTREAMER_DIR}/gstreamer/lib/pkgconfig:${DLSTREAMER_DIR}/build/intel64/Release/lib/pkgconfig:

RUN export no_proxy= && \
    apt-get update && \
    apt-get install -y -q --no-install-recommends libdrm-dev=\* && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Build gst-udf-loader plugin
RUN /bin/bash -c "cd /home/pipeline-server/gst-udf-loader/ \
    && if [ -d \"build\" ] ; then rm -rf build ; fi \
    && mkdir build \
    && cd gst_plugin && sed -i '/dlstreamer_gst_meta/c\\\t/opt/intel/dlstreamer/lib/libdlstreamer_gst_meta.so' CMakeLists.txt && cd .. \
    && cd build \
    && cmake -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE} -DCMAKE_INSTALL_INCLUDEDIR=${CMAKE_INSTALL_PREFIX}/include -DCMAKE_INSTALL_PREFIX=${CMAKE_INSTALL_PREFIX} .. \
    && make"

############################# DL Streamer Pipeline Server runtime ################################

FROM ${BASE_IMAGE} AS dlstreamer-pipeline-server

USER root

ARG WORKDIR=/home/pipeline-server
WORKDIR ${WORKDIR}

RUN . /etc/os-release && \
    if [ "$VERSION_ID" = "24.04" ]; then \
        export no_proxy= && \
        apt-get update --allow-releaseinfo-change && apt-get install -y --no-install-recommends \
        python3-venv \
        libglib2.0-0 \
        libusb-1.0-0 \
        libtool \
        zlib1g \
        libopencv-core406 \
        libopencv-imgcodecs406 \
        libcjson1 \
        libxtst6 && \
        ln -sf /usr/lib/x86_64-linux-gnu/libpython3.12.so.1.0 /usr/lib/x86_64-linux-gnu/libpython3.12.so; \
    else \
        export no_proxy= && \
        apt-get update --allow-releaseinfo-change && apt-get install -y --no-install-recommends \
        python3-venv \
        libglib2.0-0 \
        libusb-1.0-0 \
        libtool \
        zlib1g \
        libopencv-core4.5d \
        libopencv-imgcodecs4.5d \
        libcjson1 \
        libxtst6 && \
        ln -sf /usr/lib/x86_64-linux-gnu/libpython3.10.so.1.0 /usr/lib/x86_64-linux-gnu/libpython3.10.so; \
    fi && \
    apt clean && \
    rm -rf /var/lib/apt/lists/*

RUN \
    mkdir /python3venv && \
    chmod -R u+w /python3venv

RUN \
    python3 -m venv --system-site-packages /python3venv && \
    /python3venv/bin/pip3 install --no-cache-dir --upgrade pip

ENV DLSTREAMER_DIR=/opt/intel/dlstreamer
ENV VIRTUAL_ENV=/python3venv
ENV PATH=$VIRTUAL_ENV/bin:$PATH
ENV PYTHONPATH=${DLSTREAMER_DIR}/gstreamer/lib/python3/dist-packages:${DLSTREAMER_DIR}/python:${DLSTREAMER_DIR}/gstreamer/lib/python3/dist-packages

ARG CMAKE_INSTALL_PREFIX

# Needed for UDFLoader runtime
COPY --from=gstudfloader-builder /usr/lib/libeii*.so /usr/lib/libsafestring.so /usr/lib/
COPY --from=gstudfloader-builder /home/pipeline-server/util/*.py /home/pipeline-server/util/
COPY --from=gstudfloader-builder ${CMAKE_INSTALL_PREFIX}/lib/udf.so ${DLSTREAMER_DIR}/gstreamer/lib
COPY --from=gstudfloader-builder ${CMAKE_INSTALL_PREFIX}/lib/libeiiudfloader.so ${DLSTREAMER_DIR}/gstreamer/lib
COPY --from=gstudfloader-builder /home/pipeline-server/gst-udf-loader/build/gst_plugin/libgstudfloader.so ${DLSTREAMER_DIR}/gstreamer/lib
COPY --from=gstudfloader-builder ${CMAKE_INSTALL_PREFIX} ${CMAKE_INSTALL_PREFIX}

ENV LD_LIBRARY_PATH=${CMAKE_INSTALL_PREFIX}/lib:${CMAKE_INSTALL_PREFIX}/lib/udfs:${DLSTREAMER_DIR}/lib:${DLSTREAMER_DIR}/lib/gstreamer-1.0:${LD_LIBRARY_PATH}:/root/.local/bin \
    PYTHONPATH=$PYTHONPATH:/usr/local/lib/:/root/.local/bin:/opt/intel/eii/lib:/home/pipeline-server/:/home/pipeline-server/udfs \
    PATH=$PATH:${DLSTREAMER_DIR}/gstreamer/bin:${DLSTREAMER_DIR}/gstreamer/bin/gstreamer-1.0:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/root/.local/bin:/home/pipeline-server/.local/bin

ENV DEBIAN_FRONTEND=noninteractive
ENV LD_RUN_PATH="/usr/lib"
ENV LIBRARY_PATH=$LD_RUN_PATH:$LIBVA_DRIVERS_PATH
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$LIBVA_DRIVERS_PATH:"usr/local/lib"
ENV PKG_CONFIG_PATH="/usr/lib/x86_64-linux-gnu/pkgconfig"
ENV TERM="xterm"
ENV GST_DEBUG="1"

ARG USER
ARG UID

RUN useradd -ms /bin/bash -G video,audio,users,plugdev ${USER} -o -u $UID && \
    chown ${USER}:${USER} -R /home/pipeline-server /root

RUN mkdir -p /home/${USER}/ && chown -R ${USER}:${USER} /home/${USER}

ENV cl_cache_dir=/home/.cl_cache \
    XDG_RUNTIME_DIR=/home/.xdg_runtime_dir \
    LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/usr/local/lib:/home/pipeline-server:/usr/local/lib/udfs

RUN mkdir -p $cl_cache_dir && chmod -R g+s $cl_cache_dir && chown ${USER}:users $cl_cache_dir
RUN mkdir -p $XDG_RUNTIME_DIR && chmod -R g+s $XDG_RUNTIME_DIR && chown ${USER}:users $XDG_RUNTIME_DIR

USER $USER

# Copy source code
COPY ./docker/run.sh .
COPY ./utils/*.py ./utils/
COPY ./src/ ./src

USER root

RUN pip3 install --no-cache-dir wheel==0.45.1 setuptools==80.9.0 packaging==25.0 && \
    pip3 uninstall --no-cache-dir -y Flask && \
    # Downgrading Flask due to an atttribute error(JSONEncoder)
    pip3 install --no-cache-dir Flask==2.2.5 && \
    pip3 install --no-cache-dir PyYAML==5.4.1 --no-build-isolation && \
    pip3 install --no-cache-dir -r /home/pipeline-server/src/requirements.txt && \
    pip3 install --no-cache-dir --upgrade Werkzeug==3.1.3 && \
    pip3 install --upgrade --no-cache-dir opentelemetry-exporter-otlp

USER ${USER}

# Disable OpenVINO Telemetry
RUN opt_in_out --opt_out

# Create Models directory
RUN mkdir -p /home/pipeline-server/models

# Create resources directories for k8s runtime uploads
RUN mkdir -p /home/pipeline-server/resources/videos
RUN mkdir -p /home/pipeline-server/resources/models
RUN mkdir -p /home/pipeline-server/resources/images

# Copy python UDFs for user_defined_pipelines/udfloader_sample pipeline
COPY ./user_scripts/udfs/python/ /home/pipeline-server/udfs/python/
ENV PYTHONPATH=$PYTHONPATH:/home/pipeline-server/udfs/python/geti_udf

# Copy GVAPYTHON samples
COPY ./user_scripts/gvapython/ /home/pipeline-server/gvapython/

# Copy default config
COPY ./configs/default/config.json /home/pipeline-server/config.json

ENTRYPOINT ["./run.sh"]


############################# DL Streamer Pipeline Server extended runtime ################################

FROM dlstreamer-pipeline-server AS dlstreamer-pipeline-server-extended

USER root

# Patch and install OpenVINO model api
COPY ./docker/model_api.patch /home/pipeline-server/model_api.patch
RUN pip3 install --no-cache-dir openvino-model-api==0.2.5

# site packages path independent of Python version (Python 3.10 for Ubuntu 22.04 and Python 3.12 for Ubuntu 24.04)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    MODEL_API_PATH=$(python3 -c "import site; print(site.getsitepackages()[0])")/model_api && \
    cd $MODEL_API_PATH && \
    git apply /home/pipeline-server/model_api.patch && \
    apt-get remove -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Ubuntu 22: Python 3.10 still often gets pre-built datumaro wheels, so Rust might be unused.
# Ubuntu 24: Python 3.12 rarely has wheels for datumaro, so it falls back to source — Rust is required here (for building datumaro - needed for geti-sdk installation).
# Detect Ubuntu version and install Rust only on Ubuntu 24
RUN . /etc/os-release && \
    if [ "$VERSION_ID" = "24.04" ]; then \
        apt-get update && \
        apt-get install -y --no-install-recommends python3-dev curl build-essential && \
        curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain 1.87.0 && \
        echo 'source $HOME/.cargo/env' >> ~/.bashrc && \
        export PATH="/root/.cargo/bin:$PATH" && \
        pip3 install --no-cache-dir geti-sdk==2.7.1 && \
        # clean up Rust installation files
        rm -rf /root/.cargo /root/.rustup; \
    else \
        pip3 install --no-cache-dir geti-sdk==2.7.1; \
    fi && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache

# Uninstall cuda-python installed by Geti SDK because of proprietary license causing OSPDT issue
RUN pip3 uninstall --no-cache-dir -y cuda-python aiohappyeyeballs

# Set environment variables up front to ensure locales work properly
ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

# ROS2 installation
RUN apt update && \
    apt install -y locales software-properties-common && \
    locale-gen en_US en_US.UTF-8 && \
    update-locale LC_ALL=${LC_ALL} LANG=${LANG} && \
    add-apt-repository universe && \
    apt update && \
    curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
        http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
        | tee /etc/apt/sources.list.d/ros2.list > /dev/null && \
    apt update && \
    . /etc/os-release && \
    if [ "$VERSION_ID" = "24.04" ]; then \
        apt install -y ros-jazzy-ros-base python3-colcon-common-extensions; \
    else \
        apt install -y ros-humble-ros-base python3-colcon-common-extensions; \
    fi && \
    apt clean && \
    rm -rf /var/lib/apt/lists/*
    
RUN pip3 install --no-cache-dir --upgrade openvino==2025.2.0 openvino-telemetry==2025.2.0

USER ${USER}