<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Packaging and distribution

## Artifacts

| Artifact | Contents | How to build |
|----------|----------|--------------|
| **CMake install** | headers, `liboptical_flow_sdk`, CMake + pkg-config | `cmake --install` |
| **Debian** | `liboptical-flow-sdk0`, `liboptical-flow-sdk-dev`, `python3-optical-flow-sdk` | `./scripts/build_deb.sh` |
| **Python wheel** | `optical_flow_sdk` + `_native` (CPU, static-linked) | `./scripts/build_wheel.sh` |

Default app API is `OpticalFlow` / `SparsePyrLK` with `Backend` selection.
OpenCL/SYCL types remain advanced escape hatches in the C++ `-dev` package.

## Debian (CPU + OpenCL)

```bash
cd libraries/optical-flow-sdk
./scripts/build_deb.sh
sudo apt install ../liboptical-flow-sdk0_*.deb \
  ../liboptical-flow-sdk-dev_*.deb \
  ../python3-optical-flow-sdk_*.deb
```

C++ consumers:

```cmake
find_package(optical_flow_sdk REQUIRED)
target_link_libraries(app PRIVATE optical_flow_sdk::optical_flow_sdk)
```

## Wheel (CPU)

Self-contained: static C++ linked into `_native.so` (no separate `.so`
dependency). OpenCL/SYCL are not in the default wheel; use Debian packages or
a custom CMake build for GPU.

```bash
./scripts/build_wheel.sh
python3 -m pip install dist/optical_flow_sdk-*.whl
python3 python/samples/calc_flow_dis.py
```

## Source / CMake (all backends)

```bash
cmake -S . -B build-release \
  -DCMAKE_BUILD_TYPE=Release \
  -DOPTICALFLOW_ENABLE_CPU=ON \
  -DOPTICALFLOW_ENABLE_OPENCL=ON \
  -DOPTICALFLOW_BUILD_SHARED=ON \
  -DOPTICALFLOW_BUILD_PYTHON=ON \
  -DOPTICALFLOW_INSTALL_PYTHON=ON \
  -DCMAKE_INSTALL_PREFIX=/usr/local
cmake --build build-release --parallel
sudo cmake --install build-release
```
