ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS dlstreamer-pipeline-server
ENV DLSTREAMER_DIR=/opt/intel/dlstreamer
ENV GSTREAMER_DIR=$DLSTREAMER_DIR/gstreamer

USER root

ENV VIRTUAL_ENV=/python3venv
ENV PATH=$VIRTUAL_ENV/bin:$PATH
ENV PYTHONPATH=/opt/intel/dlstreamer/gstreamer/lib/python3/dist-packages:/opt/intel/dlstreamer/python:/opt/intel/dlstreamer/gstreamer/lib/python3/dist-packages

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
    PATH=$PATH:${DLSTREAMER_DIR}/gstreamer/bin:${DLSTREAMER_DIR}/gstreamer/bin/gstreamer-1.0:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/root/.local/bin \
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

# site packages path independent of Python version (Python 3.10 for Ubuntu 22.04 and Python 3.12 for Ubuntu 24.04)
RUN MODEL_API_PATH=$(python3 -c "import site; print(site.getsitepackages()[0])")/model_api && \
    cd $MODEL_API_PATH && \
    git apply /home/pipeline-server/model_api.patch

# Ubuntu 22: Python 3.10 still often gets pre-built datumaro wheels, so Rust might be unused.
# Ubuntu 24: Python 3.12 rarely has wheels for datumaro, so it falls back to source — Rust is required here (for building datumaro - needed for geti-sdk installation).
# Detect Ubuntu version and install Rust only on Ubuntu 24
RUN . /etc/os-release && \
    if [ "$VERSION_ID" = "24.04" ]; then \
        apt-get update && \
        apt-get install -y --no-install-recommends curl build-essential && \
        curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain 1.87.0 && \
        echo 'source $HOME/.cargo/env' >> ~/.bashrc && \
        export PATH="/root/.cargo/bin:$PATH" && \
        pip install --upgrade pip && \
        pip install geti-sdk==2.7.1 && \
        # clean up Rust installation files
        rm -rf /root/.cargo /root/.rustup; \
    else \
        pip install --upgrade pip && \
        pip install geti-sdk==2.7.1; \
    fi && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache



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
    python3 -m pip install --upgrade Werkzeug==3.1.3 orjson==3.10.12 packaging==24.2 boto3==1.36.17
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

ENTRYPOINT ["./run.sh"]