<!--
Copyright (C) 2025 Intel Corporation

SPDX-License-Identifier: Apache-2.0
-->

# GPU ORB extractor

The library demonstrates ORB feature extractor running using CPU and GPU.
The ORB feature extractor is based on
[OpenVSLAM](https://github.com/OpenVSLAM-Community/openvslam) version.

This ORB can easily integrate to Visual SLAM. After initializing orb_extractor
object, for every input frame, call to extract function. Extract function will
return a set of keypoints and descriptors.

The ORB feature extractor consists of various CV kernels such as resize,
gaussian, fast, compute descriptor and orientation while non CV functions
like distribute_keypoints_via_tree.

All the CV related kernels have offloaded to Intel GPU using oneAPI Level Zero
interface and GPU kernels are written using C-for-Metal.
Non CV functions will run in CPU.

## System Requirements

1) Ubuntu 22.04 and Ubuntu 24.04
2) OpenCV 4.2+ with support up to OpenCV 4.6 (ROS Jazzy)
3) [Intel® Graphics Compute Runtime for oneAPI Level Zero and OpenCL™ Driver](https://github.com/intel/compute-runtime)
4) Intel oneAPI 2025.3 with SYCL compiler for GPU acceleration

## Directory structure

```text
libgpu_orb/
├── include/
│   └── orb_extractor.h
├── lib/
│   ├── libgpu_orb.so
│   ├── fastclear_genx.bin
│   ├── fastext_genx.bin
│   ├── fastnmsext_genx.bin
│   ├── gaussian_genx.bin
│   ├── resize_genx.bin
│   └── orb_descriptor_genx.bin
└── samples/
    ├── CMakeLists.txt
    ├── main.cpp
    ├── market.jpg
    └── tutorial.md
```

1) `include` - Class header that provides configurable options
   for this library
2) `lib` - Host code libgpu_orb.so and all *.bin are compiled
   GPU kernels
3) `samples` - Sample code to show how to use the library for either
   mono camera or stereo camera

## Build and run sample code

Build:

```sh
cd samples
mkdir build
cd build
cmake ../
make -j8
```

Run the sample:

```sh
./feature_extract
```

To adjust for latency and CPU utilization:

```sh
export CPU_SLEEP_TIME=<sleep duration in microseconds>
```

NOTE: Higher sleep value leads to higher latency
      and reduced CPU utilization and vice versa
