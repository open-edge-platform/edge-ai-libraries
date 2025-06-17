ARG BASE_IMAGE
ARG USER

FROM ${BASE_IMAGE}

USER root

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
        pip install --no-cache-dir --upgrade pip && \
        pip install --no-cache-dir geti-sdk==2.7.1 && \
        # clean up Rust installation files
        rm -rf /root/.cargo /root/.rustup; \
    else \
        pip install --no-cache-dir --upgrade pip && \
        pip install --no-cache-dir geti-sdk==2.7.1; \
    fi && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache


# Uninstall cuda-python installed by Geti SDK because of proprietary license causing OSPDT issue
RUN pip3 uninstall --no-cache-dir -y cuda-python aiohappyeyeballs

USER ${USER}
