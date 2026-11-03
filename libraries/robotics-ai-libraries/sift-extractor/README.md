# SIFT Extractor (Robotics AI Libraries)

Thin robotics packaging wrapper around the horizontal
[`sift-extractor`](../../sift-extractor) core. **No kernels are copied** into this
tree — the shared libraries link `sift_extractor::sift_extractor`.

## Why a wrapper

- ORB-aligned install layout and Humble/Jammy + Jazzy/Noble debian packaging for
  the Robotics AI Suite.
- Multi-camera `extract()` API similar to `orb_extractor`, with OpenCV and
  OpenCV-free libraries.
- Core remains OpenCV/ROS free.

## Descriptor contract

SIFT descriptors are **128-D float (L2)**. They are **not** drop-in replacements
for ORB binary descriptors / Hamming matching.

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

Unsupported without Intel GPU ICD / Level Zero + matching oneAPI SYCL runtime
when the SYCL backend is enabled. Disclose gaps to consumers; there is no silent
CPU fallback in this wrapper.
