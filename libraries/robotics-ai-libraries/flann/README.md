# FLANN Optimized with Intel oneAPI DPC++

FLANN is a 3-D processing library used to search for nearest neighbors in three-dimensional or even higher dimensional space. FLANN builds indices to the input points and provides interfaces to search for the nearest K (number of) or nearest R (radius) neighbors.

The oneAPI DPC++ Compatibility Tool (DPCT) is used to migrate the CUDA implementation into Data Parallel C++ (DPC++) for building and searching the k-dimensional tree. Additionally, some CUDA thrust functions need manual migration. The dimension and size of index space, nd_range of SYCL are adapted according to the hardware device capability of the maximum work-group size. Unified Shared Memory (USM) is used to avoid additional memory copy.

![benchmark](README.assets/flann_performance.png)

## Changes to 3rd party source

This work depends on a patched open-source [flann](https://github.com/flann-lib/flann) repository.

The following patches are provided to enhance the FLANN source:

| Directory          | Enhancement                     |
| ------------------ | ------------------------------- |
| [patches](patches) | Support Intel oneAPI            |
| [patches](patches) | Build FLANN as Debian package   |

## Launch FLANN Intel oneAPI DPC++ Benchmark

To start the benchmark, run the following commands:

Run the FLANN Test suite on Intel® GPU via Level-Zero API:

$ cd /opt/intel/flann/dpcpp/tests
$ export SYCL_CACHE_PERSISTENT=1
$ export ONEAPI_DEVICE_SELECTOR=level_zero:gpu
$ ./flanntest_dp  ../data/data_.txt | tee /tmp/flann_test_gpu.log

Run the FLANN Test suite on Intel® CPU:

$ cd /opt/intel/flann/dpcpp/tests
$ export ONEAPI_DEVICE_SELECTOR=opencl:cpu
$ ./flanntest_dp  ../data/data_.txt | tee /tmp/flann_test_cpu.log

## Interpret FLANN Intel® oneAPI DPC++ Benchmark results¶

FLANN benchmark logs computing latency in milliseconds, for various k and radius values, between Intel® oneAPI DPC++ level0 GPU and plain CPU execution.

```
[----------] 1 test from oneapi_flann_knn_performance_test
[ RUN      ] oneapi_flann_knn_performance_test.Positive
data size is 198273
data size is 191380
====kdtree dpcpp index=======================
create kdtree dpcpp: 98.935 ms
k=2 search kdtree: 50.914 ms
k=7 search kdtree: 62.323 ms
k=12 search kdtree: 97.775 ms
k=17 search kdtree: 167.936 ms
k=22 search kdtree: 232.559 ms
k=27 search kdtree: 284.624 ms
k=32 search kdtree: 330.846 ms
k=37 search kdtree: 388.697 ms
k=42 search kdtree: 447.857 ms
k=47 search kdtree: 508.655 ms
k=52 search kdtree: 568.344 ms
k=57 search kdtree: 627.265 ms
k=62 search kdtree: 716.911 ms
k=67 search kdtree: 743.552 ms
k=72 search kdtree: 829.595 ms
====kdtree single index=======================
create kdtree: 242.245 ms
k=2 search kdtree: 470.504 ms
k=7 search kdtree: 1094.13 ms
k=12 search kdtree: 2334.15 ms
k=17 search kdtree: 3226.63 ms
k=22 search kdtree: 3746.74 ms
k=27 search kdtree: 4113.68 ms
k=32 search kdtree: 4478.92 ms
k=37 search kdtree: 5092.62 ms
k=42 search kdtree: 5856.41 ms
k=47 search kdtree: 6405.64 ms
k=52 search kdtree: 6937.99 ms
k=57 search kdtree: 7455.19 ms
k=62 search kdtree: 8054.9 ms
k=67 search kdtree: 8631.63 ms
k=72 search kdtree: 13356.7 ms
[       OK ] oneapi_flann_knn_performance_test.Positive (89874 ms)
[----------] 1 test from oneapi_flann_knn_performance_test (89874 ms total)
[----------] 1 test from oneapi_flann_radius_performance_test
[ RUN      ] oneapi_flann_radius_performance_test.Positive
data size is 198273
data size is 198273
====kdtree dpcpp index=======================
create kdtree dpcpp: 95.827 ms
radius=0.01 search kdtree: 27.789 ms
radius=0.06 search kdtree: 21.541 ms
radius=0.11 search kdtree: 27.399 ms
radius=0.16 search kdtree: 27.926 ms
radius=0.21 search kdtree: 31.558 ms
radius=0.26 search kdtree: 33.077 ms
radius=0.31 search kdtree: 34.523 ms
radius=0.36 search kdtree: 34.366 ms
radius=0.41 search kdtree: 43.423 ms
radius=0.46 search kdtree: 45.014 ms
radius=0.51 search kdtree: 63.377 ms
radius=0.56 search kdtree: 67.082 ms
radius=0.61 search kdtree: 68.667 ms
radius=0.66 search kdtree: 71.914 ms
radius=0.71 search kdtree: 69.622 ms
====kdtree single index=======================
create kdtree: 337.145 ms
radius=0.01 search kdtree: 451.055 ms
radius=0.06 search kdtree: 451.089 ms
radius=0.11 search kdtree: 607.748 ms
radius=0.16 search kdtree: 625.998 ms
radius=0.21 search kdtree: 705.211 ms
radius=0.26 search kdtree: 730.814 ms
radius=0.31 search kdtree: 726.285 ms
radius=0.36 search kdtree: 745.114 ms
radius=0.41 search kdtree: 868.959 ms
radius=0.46 search kdtree: 908.484 ms
radius=0.51 search kdtree: 1079.77 ms
radius=0.56 search kdtree: 1119.06 ms
radius=0.61 search kdtree: 1127.51 ms
radius=0.66 search kdtree: 1127.1 ms
radius=0.71 search kdtree: 1137.84 ms
[       OK ] oneapi_flann_radius_performance_test.Positive (16587 ms)
[----------] 1 test from oneapi_flann_radius_performance_test (16587 ms total)
[----------] Global test environment tear-down
[==========] 4 tests from 4 test suites ran. (124442 ms total)
[  PASSED  ] 4 tests.
```
