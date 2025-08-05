# PCL Optimized with Intel oneAPI DPC++

Point-Cloud Library (PCL) contains common algorithms for 3-D point cloud processing.

For the PCL module with CUDA code, DPCT is used to migrate the CUDA code to DPC++ implementation. For the PCL module without CUDA code, Intel® VTune Profiler is used to identify the performance bottlenecks and OMP is used to enable multi-processing via compiler directives.

![benchmark](README.assets/pcl_performance.png)

## Changes to 3rd party source

This work depends on a patched open-source [pcl](https://github.com/PointCloudLibrary/pcl) repository.

The following patches are provided to enhance the PCL source:

| Directory          | Enhancement                     |
| ------------------ | ------------------------------- |
| [patches](patches) | Support Intel oneAPI            |
| [patches](patches) | Build PCL as Debian package     |

## Launch PCL Intel oneAPI DPC++ Benchmark

To start the benchmark, run the following commands:

Check that all PCL algorithms run successfully on Intel® GPU via Level-Zero API:

```
$ cd /opt/intel/pcl/oneapi/tests
$ export SYCL_CACHE_PERSISTENT=1
$ export ONEAPI_DEVICE_SELECTOR=level_zero:gpu
$ find . -name "*test_*" -not -name "*_performance" -not -name "*_perf" -not -name "*greedy*" -exec {} \; | tee /tmp/pcl_functional_test_gpu.log
```

> [!IMPORTANT]
> Consider the known limitations of Intel® Gen9.x Graphics Level0 API call will fail due to data-size hardware offload limits with the following PCL tests:
> * PCL_OneAPI_Octree.OneAPI_Octree_approxNearestSearch
> * PCL_OneAPI_Octree.OneAPI_Octree_Radius_Search_Function
> * PCL_OctreeOneAPI.OneAPI_Octree_KNNSearch
> * PCL_ONEAPI_MLS.test_radius_configuration
> * PCL.SampleConsensusInitialAlignment_DPCPP_CPU

It is recommended to ignore those sub-tests with Intel® Gen9.x Graphics hardware:

```
$ find . -name "*test_*" -not -name "*_performance" -not -name "*_perf" -not -name "*outlier*" -not -name "*greedy*" -not -name "*octree*" -not -name "*mls*" -not -name "*scia*" -exec {} \; | tee /tmp/pcl_functional_test_gpu.log
```

Check that all PCL algorithms run successfully on Intel® CPU:

```
$ cd /opt/intel/pcl/oneapi/tests
$ export SYCL_CACHE_PERSISTENT=1
$ export ONEAPI_DEVICE_SELECTOR=opencl:cpu
$ find . -name "*test_*" -not -name "*_performance" -not -name "*_perf" -not -name "*greedy*" -exec {} \; | tee /tmp/pcl_functional_test_gpu.log
```

Run individual performances of each oneAPI optimized PCL algorithms alternatively on Intel® GPU via level0 API and Intel® CPU:

```
$ cd /opt/intel/pcl/oneapi
$ export ONEAPI_DEVICE_SELECTOR=level_zero:gpu
```

OR

```
$ cd /opt/intel/pcl/oneapi
$ export ONEAPI_DEVICE_SELECTOR=opencl:cpu
```

## Interpret PCL Intel oneAPI DPC++ Benchmark results¶

Each PCL benchmarks logs computing latency in milliseconds between Intel® oneAPI DPC++ level0 GPU versus plain CPU execution.

```
./tests/test_oneapi_kdtree_perf ./data/test_P.pcd ./data/test_Q.pcd
[==========] Running 7 tests from 1 test suite.
[----------] Global test environment set-up.
[----------] 7 tests from PCL
[ RUN      ] PCL.KdTreeFLANN_radiusSearch
OneAPI time for kdtree radius search 33.1814 milliseconds
CPU time for kdtree radius search 269.944 milliseconds
[       OK ] PCL.KdTreeFLANN_radiusSearch (131366 ms)
[ RUN      ] PCL.KdTreeFLANN_fixedRadiusSearch_native_buffer
OneAPI time for kdtree radius search 27.1908 milliseconds
CPU time for kdtree radius search 267.957 milliseconds
[       OK ] PCL.KdTreeFLANN_fixedRadiusSearch_native_buffer (1535 ms)
[ RUN      ] PCL.KdTreeFLANN_fixedRadiusSearch_std_vector
OneAPI time for kdtree radius search 37.5182 milliseconds
CPU time for kdtree radius search 267.964 milliseconds
[       OK ] PCL.KdTreeFLANN_fixedRadiusSearch_std_vector (1569 ms)
[ RUN      ] PCL.KdTreeFLANN_fixedRadiusSearchUnSort
OneAPI time for kdtree radius search 5.135 milliseconds
CPU time for kdtree radius search 129.396 milliseconds
[       OK ] PCL.KdTreeFLANN_fixedRadiusSearchUnSort (687 ms)
[ RUN      ] PCL.KdTreeFLANN_knnSearch
OneAPI time for kdtree k-nearest neighbor search 1.922 milliseconds
CPU time for kdtree k-nearest neighbor search 35.3504 milliseconds
[       OK ] PCL.KdTreeFLANN_knnSearch (211 ms)
[ RUN      ] PCL.KdTreeFLANN_knnSearch_native_buffer_2d
OneAPI time for kdtree k-nearest neighbor search 2.103 milliseconds
CPU time for kdtree k-nearest neighbor search 35.225 milliseconds
[       OK ] PCL.KdTreeFLANN_knnSearch_native_buffer_2d (207 ms)
[ RUN      ] PCL.KdTreeFLANN_knnSearch_native_buffer_1d
OneAPI time for kdtree k-nearest neighbor search 1.9728 milliseconds
CPU time for kdtree k-nearest neighbor search 35.8558 milliseconds
[       OK ] PCL.KdTreeFLANN_knnSearch_native_buffer_1d (210 ms)
[----------] 7 tests from PCL (135785 ms total)
[----------] Global test environment tear-down
[==========] 7 tests from 1 test suite ran. (135785 ms total)
[  PASSED  ] 7 tests.
```
