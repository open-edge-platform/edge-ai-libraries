# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# 1. Base image (Python + Linux)
FROM python:3.10-slim

# 2. Set working directory inside container
WORKDIR /app

# Make src-layout imports work + unbuffered logs
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AVIF_JOBS=8 \
    OMP_NUM_THREADS=8 \
    MKL_NUM_THREADS=8 \
    OPENBLAS_NUM_THREADS=8 \
    NUMEXPR_NUM_THREADS=8

# 3. System deps for OpenCV / YOLO
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libavif-bin \
    libomp5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# --- REQUIRED CHANGE: ensure pip can pick up prebuilt wheels (tokenizers) ---
RUN pip install --no-cache-dir -U pip setuptools wheel

# 3b. Intel NPU user-space driver + Level Zero runtime
ARG NPU_DRIVER_RELEASE=v1.35.0
ARG NPU_DRIVER_TARBALL=linux-npu-driver-v1.35.0.20260722-29947505341-ubuntu2404.tar.gz
ARG NPU_DRIVER_SHA256=398343e53fdac6023ad0856ef88bb6011b1e12447a112be55e85e27ef7f96c66
ARG LEVEL_ZERO_RELEASE=v1.28.2
ARG LEVEL_ZERO_DEB=level-zero_1.28.2+u24.04_amd64.deb
ARG LEVEL_ZERO_DEB_SHA256=df339abcc8872b3d30887b8845c62a9768db943debcdd96a900b573a02a12cae

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates libtbb12 build-essential cmake \
    && mkdir -p /tmp/npu-driver && cd /tmp/npu-driver \
    && wget -q "https://github.com/intel/linux-npu-driver/releases/download/${NPU_DRIVER_RELEASE}/${NPU_DRIVER_TARBALL}" \
    && echo "${NPU_DRIVER_SHA256}  ${NPU_DRIVER_TARBALL}" | sha256sum -c - \
    && tar -xf "${NPU_DRIVER_TARBALL}" \
    && wget -q "https://github.com/oneapi-src/level-zero/releases/download/${LEVEL_ZERO_RELEASE}/${LEVEL_ZERO_DEB}" \
    && echo "${LEVEL_ZERO_DEB_SHA256}  ${LEVEL_ZERO_DEB}" | sha256sum -c - \
    && dpkg -i *.deb \
    && apt-get update && apt-get install -y -f --no-install-recommends \
    && cd / && rm -rf /tmp/npu-driver

# 3c. Intel iGPU compute runtime (OpenCL + Level Zero GPU driver) to support `intel:igpu`
ARG GPU_RUNTIME_RELEASE=26.18.38308.1
ARG IGC_RELEASE=v2.34.4
ARG IGC_BUILD=2.34.4+21428
ARG GMMLIB_VERSION=22.10.0
ARG IGC_CORE_DEB=intel-igc-core-2_${IGC_BUILD}_amd64.deb
ARG IGC_CORE_SHA256=0ce1e715ec5bf30b1304b42acfbda34cc514a0f616dd48c6a31973c4075d8d09
ARG IGC_OPENCL_DEB=intel-igc-opencl-2_${IGC_BUILD}_amd64.deb
ARG IGC_OPENCL_SHA256=09a71e8b6ad432ed0511b09fa4f580c1b44534a60ccb0545212507bf67dc0d1b
ARG GMMLIB_DEB=libigdgmm12_${GMMLIB_VERSION}_amd64.deb
ARG GMMLIB_SHA256=6031a63d6e8a12ce61c14efc15f2c8e727061286e3820b8594e6d00615e04d54
ARG OPENCL_ICD_DEB=intel-opencl-icd_${GPU_RUNTIME_RELEASE}-0_amd64.deb
ARG OPENCL_ICD_SHA256=b2d0c924e56b3f9e5837774d68b0c67461b8633035d93ca18b1a8e3e5ead15fa
ARG LEVEL_ZERO_GPU_DEB=libze-intel-gpu1_${GPU_RUNTIME_RELEASE}-0_amd64.deb
ARG LEVEL_ZERO_GPU_SHA256=12b8254e6d3415c32cee9cd13943030b991d91212445c79fe1cc27176a72eca4

RUN apt-get update && apt-get install -y --no-install-recommends ocl-icd-libopencl1 \
    && mkdir -p /tmp/gpu-runtime && cd /tmp/gpu-runtime \
    && wget -q "https://github.com/intel/intel-graphics-compiler/releases/download/${IGC_RELEASE}/${IGC_CORE_DEB}" \
    && echo "${IGC_CORE_SHA256}  ${IGC_CORE_DEB}" | sha256sum -c - \
    && wget -q "https://github.com/intel/intel-graphics-compiler/releases/download/${IGC_RELEASE}/${IGC_OPENCL_DEB}" \
    && echo "${IGC_OPENCL_SHA256}  ${IGC_OPENCL_DEB}" | sha256sum -c - \
    && wget -q "https://github.com/intel/compute-runtime/releases/download/${GPU_RUNTIME_RELEASE}/${GMMLIB_DEB}" \
    && echo "${GMMLIB_SHA256}  ${GMMLIB_DEB}" | sha256sum -c - \
    && wget -q "https://github.com/intel/compute-runtime/releases/download/${GPU_RUNTIME_RELEASE}/${OPENCL_ICD_DEB}" \
    && echo "${OPENCL_ICD_SHA256}  ${OPENCL_ICD_DEB}" | sha256sum -c - \
    && wget -q "https://github.com/intel/compute-runtime/releases/download/${GPU_RUNTIME_RELEASE}/${LEVEL_ZERO_GPU_DEB}" \
    && echo "${LEVEL_ZERO_GPU_SHA256}  ${LEVEL_ZERO_GPU_DEB}" | sha256sum -c - \
    && dpkg -i *.deb \
    && apt-get update && apt-get install -y -f --no-install-recommends \
    && cd / && rm -rf /tmp/gpu-runtime

# 3a. Build & install zlib-ng as a drop-in replacement for system zlib
ARG ZLIB_NG_VERSION=2.3.3
ARG ZLIB_NG_SHA256=f9c65aa9c852eb8255b636fd9f07ce1c406f061ec19a2e7d508b318ca0c907d1
RUN wget -q "https://github.com/zlib-ng/zlib-ng/archive/refs/tags/${ZLIB_NG_VERSION}.tar.gz" -O /tmp/zlib-ng.tar.gz \
    && echo "${ZLIB_NG_SHA256}  /tmp/zlib-ng.tar.gz" | sha256sum -c - \
    && mkdir -p /tmp/zlib-ng && tar -xf /tmp/zlib-ng.tar.gz -C /tmp/zlib-ng --strip-components=1 \
    && cmake -S /tmp/zlib-ng -B /tmp/zlib-ng/build \
        -DZLIB_COMPAT=ON \
        -DZLIB_ENABLE_TESTS=OFF \
        -DWITH_GTEST=OFF \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr \
    && cmake --build /tmp/zlib-ng/build -j"$(nproc)" \
    && cmake --install /tmp/zlib-ng/build \
    && ldconfig \
    && rm -rf /tmp/zlib-ng* \
    && apt-get purge -y --auto-remove build-essential cmake wget \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy dependency list first (important for caching)
COPY requirements.txt /tmp/

# 5. Install Python dependencies
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 6. Copy application code + assets
COPY src/ /app/src/

# 7. Copy configs
COPY configs/ /app/configs/

# 8. Copy models
COPY models/obj_det_models/ /app/models/obj_det_models/

# 9. Run as non-root
RUN useradd -r -u 1999 -s /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["curl", "-f", "http://localhost:5999/"]

# 10. Default command to run your app
ENTRYPOINT ["python", "-m", "semantic_img_comp.main"]