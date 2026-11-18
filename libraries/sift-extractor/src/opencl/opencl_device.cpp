// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#define CL_TARGET_OPENCL_VERSION 120

#include "sift_extractor/opencl_device.hpp"

#include <CL/cl.h>
#include <CL/cl_ext.h>

#include <stdexcept>
#include <string>
#include <vector>

namespace sift_extractor {
namespace {

void check_opencl(cl_int status, const char *operation) {
  if (status != CL_SUCCESS) {
    throw std::runtime_error(std::string(operation) +
                             " failed with OpenCL status " +
                             std::to_string(status));
  }
}

template <typename Value>
Value get_device_value(cl_device_id device, cl_device_info parameter,
                       const char *operation) {
  Value value{};
  check_opencl(clGetDeviceInfo(device, parameter, sizeof(value), &value, nullptr),
               operation);
  return value;
}

std::string get_platform_string(cl_platform_id platform,
                                cl_platform_info parameter,
                                const char *operation) {
  std::size_t size = 0;
  check_opencl(clGetPlatformInfo(platform, parameter, 0, nullptr, &size),
               operation);
  std::vector<char> value(size);
  check_opencl(clGetPlatformInfo(platform, parameter, value.size(), value.data(),
                                 nullptr),
               operation);
  return std::string(value.data());
}

std::string get_device_string(cl_device_id device, cl_device_info parameter,
                              const char *operation) {
  std::size_t size = 0;
  check_opencl(clGetDeviceInfo(device, parameter, 0, nullptr, &size), operation);
  std::vector<char> value(size);
  check_opencl(clGetDeviceInfo(device, parameter, value.size(), value.data(),
                               nullptr),
               operation);
  return std::string(value.data());
}

} // namespace

std::vector<OpenCLDeviceInfo> enumerate_opencl_devices() {
  cl_uint platform_count = 0;
  const cl_int platform_status =
      clGetPlatformIDs(0, nullptr, &platform_count);
  if (platform_status == CL_PLATFORM_NOT_FOUND_KHR)
    return {};
  check_opencl(platform_status, "clGetPlatformIDs(count)");

  std::vector<cl_platform_id> platforms(platform_count);
  check_opencl(clGetPlatformIDs(platform_count, platforms.data(), nullptr),
               "clGetPlatformIDs(list)");

  std::vector<OpenCLDeviceInfo> result;
  for (cl_platform_id platform : platforms) {
    cl_uint device_count = 0;
    const cl_int device_status =
        clGetDeviceIDs(platform, CL_DEVICE_TYPE_ALL, 0, nullptr, &device_count);
    if (device_status == CL_DEVICE_NOT_FOUND)
      continue;
    check_opencl(device_status, "clGetDeviceIDs(count)");

    std::vector<cl_device_id> devices(device_count);
    check_opencl(clGetDeviceIDs(platform, CL_DEVICE_TYPE_ALL, device_count,
                                devices.data(), nullptr),
                 "clGetDeviceIDs(list)");

    const std::string platform_name = get_platform_string(
        platform, CL_PLATFORM_NAME, "clGetPlatformInfo(name)");
    const std::string platform_version = get_platform_string(
        platform, CL_PLATFORM_VERSION, "clGetPlatformInfo(version)");

    for (cl_device_id device : devices) {
      OpenCLDeviceInfo info;
      info.platform_name = platform_name;
      info.platform_version = platform_version;
      info.name = get_device_string(device, CL_DEVICE_NAME,
                                    "clGetDeviceInfo(name)");
      info.vendor = get_device_string(device, CL_DEVICE_VENDOR,
                                      "clGetDeviceInfo(vendor)");
      info.version = get_device_string(device, CL_DEVICE_VERSION,
                                       "clGetDeviceInfo(version)");
      info.driver_version = get_device_string(
          device, CL_DRIVER_VERSION, "clGetDeviceInfo(driver version)");
      info.compute_units = get_device_value<cl_uint>(
          device, CL_DEVICE_MAX_COMPUTE_UNITS,
          "clGetDeviceInfo(compute units)");
      info.global_memory_bytes = static_cast<std::size_t>(
          get_device_value<cl_ulong>(device, CL_DEVICE_GLOBAL_MEM_SIZE,
                                     "clGetDeviceInfo(global memory)"));
      info.local_memory_bytes = static_cast<std::size_t>(
          get_device_value<cl_ulong>(device, CL_DEVICE_LOCAL_MEM_SIZE,
                                     "clGetDeviceInfo(local memory)"));
      info.image_support = get_device_value<cl_bool>(
                               device, CL_DEVICE_IMAGE_SUPPORT,
                               "clGetDeviceInfo(image support)") == CL_TRUE;
      result.push_back(std::move(info));
    }
  }

  return result;
}

} // namespace sift_extractor
