# SIFT LZE sample

Thin robotics wrapper around the horizontal `sift_extractor` core.
This package is a **library**, not a ROS topic node — link it from your node
or SIFT-capable SLAM. See the suite doc **Integrate into a SIFT-capable SLAM**
under `perception/sift-extractor/`.

```bash
sift_feature_extract --image=/path/to/gray_or_bgr.png --images=1 --backend=auto
```

- `--images=N` repeats the same frame N times (same-size multi-camera path).
- Descriptors are **float 128-D (L2)**. Do not use Hamming distance or ORB matchers.
- `SIFT_BACKEND=opencl|sycl|auto` overrides `--backend` when set.

## Minimal CMake consumer

```cmake
find_package(siftlze REQUIRED)
find_package(OpenCV REQUIRED)
add_executable(my_node main.cpp)
target_link_libraries(my_node PRIVATE sift_lze ${OpenCV_LIBS})
```
