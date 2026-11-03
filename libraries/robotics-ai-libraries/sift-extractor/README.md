# SIFT Extractor (Robotics AI Libraries)

Thin robotics packaging wrapper around the horizontal
[`sift-extractor`](../../sift-extractor) core. **No kernels are copied** into this
tree — the shared libraries link `sift_extractor::sift_extractor`.

This is a **ROS-distro packaged C++ library** (Humble/Jammy, Jazzy/Noble), not
a standalone `rclcpp` node. Use it from your ROS node or SIFT-capable SLAM by
linking `sift_lze` and calling `extract()`.

Suite tutorials:
`edge-ai-suites/robotics-ai-suite/docs/.../perception/sift-extractor/`
(especially **Integrate into a SIFT-capable SLAM**).

## Why a wrapper

- ORB-aligned install layout and Humble/Jammy + Jazzy/Noble debian packaging for
  the Robotics AI Suite.
- Multi-camera `extract()` API similar to `orb_extractor`, with OpenCV and
  OpenCV-free libraries.
- Core remains OpenCV/ROS free.

## Descriptor contract

SIFT descriptors are **128-D float (L2)**. They are **not** drop-in replacements
for ORB binary descriptors / Hamming matching. They **are** meant to replace an
unoptimized SIFT extract step in a stack that already matches with L2.

## What a consumer needs to do

1. **Install** `libsift-lze` and `libsift-lze-dev` (or `make build ROS_DISTRO=…`
   and `dpkg -i` the produced debs).
2. **Link** with CMake: `find_package(siftlze REQUIRED)` and
   `target_link_libraries(... PRIVATE sift_lze)` (or `sift_lze_ocvfree`).
3. **Construct** one `sift_lze` (max features, octaves, contrast, camera count,
   backend) and call `extract()` per frame (or multi-cam batch of same-size
   images).
4. **Keep** your L2 matcher / float vocabulary; feed `cv::KeyPoint` +
   `CV_32F` Nx128 descriptors into the existing pipeline.
5. **Tune** contrast/octaves for parity with your previous front-end; set
   `SIFT_BACKEND=opencl|sycl|auto` if needed.
6. **Runtime**: Intel GPU OpenCL ICD; Level Zero + oneAPI SYCL when using SYCL.
   There is no silent CPU fallback.

## Build (local)

```bash
# Install or export the core first, then:
cmake -S . -B build -DCMAKE_PREFIX_PATH=/path/to/sift_extractor/prefix
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

Environment override: `SIFT_BACKEND=auto|opencl|sycl`.

## Packages

| Deb | Contents |
| --- | --- |
| `libsift-lze` | `libsift_lze.so`, `libsift_lze_ocvfree.so`, core runtime libs |
| `libsift-lze-dev` | headers, CMake (`find_package(siftlze)`), pkg-config, samples |
| `sift-extractor-lze-test` | smoke tests |

```bash
make build ROS_DISTRO=humble   # jammy
make build ROS_DISTRO=jazzy    # noble
```

`debian/rules` builds the sibling core (`../../sift-extractor`) into a staging
prefix, then builds this wrapper against it.

## Consumer snippet

```cmake
find_package(siftlze REQUIRED)
target_link_libraries(my_app PRIVATE sift_lze)          # OpenCV API
# or: target_link_libraries(my_app PRIVATE sift_lze_ocvfree)
```

```cpp
#include "sift_lze.h"
sift_lze extractor(0, 5, 1.0f, 1, "auto");
std::vector<std::vector<cv::KeyPoint>> keypts;
std::vector<cv::Mat> descriptors;
extractor.extract(gray, cv::noArray(), keypts, descriptors);
// Match descriptors[0] with L2.
```

Samples: `/opt/intel/sift_lze/samples/` after installing `libsift-lze-dev`,
or `samples/tutorial.md` in this tree.
