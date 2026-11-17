// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#define CL_TARGET_OPENCL_VERSION 120

#include "sift_extractor/opencl_matcher.hpp"

#include "opencl_match_kernel.hpp"

#include <CL/cl.h>

#include <cmath>
#include <cstring>
#include <mutex>
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

cl_device_id pick_gpu_device() {
  cl_uint platform_count = 0;
  check_opencl(clGetPlatformIDs(0, nullptr, &platform_count),
               "clGetPlatformIDs(count)");
  if (platform_count == 0)
    throw std::runtime_error("No OpenCL platforms available for matcher");
  std::vector<cl_platform_id> platforms(platform_count);
  check_opencl(clGetPlatformIDs(platform_count, platforms.data(), nullptr),
               "clGetPlatformIDs(list)");
  for (cl_platform_id platform : platforms) {
    cl_uint device_count = 0;
    const cl_int status =
        clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, 0, nullptr, &device_count);
    if (status == CL_DEVICE_NOT_FOUND || device_count == 0)
      continue;
    check_opencl(status, "clGetDeviceIDs(count)");
    std::vector<cl_device_id> devices(device_count);
    check_opencl(clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, device_count,
                                devices.data(), nullptr),
                 "clGetDeviceIDs(list)");
    return devices.front();
  }
  throw std::runtime_error("No OpenCL GPU device available for matcher");
}

void pack_descriptors(const std::vector<SiftFeature> &features,
                      std::vector<float> &descriptors,
                      std::vector<float> &xy) {
  descriptors.resize(features.size() * 128u);
  xy.resize(features.size() * 2u);
  for (std::size_t i = 0; i < features.size(); ++i) {
    std::memcpy(descriptors.data() + i * 128u, features[i].descriptor.data(),
                128u * sizeof(float));
    xy[i * 2u] = features[i].x;
    xy[i * 2u + 1u] = features[i].y;
  }
}

} // namespace

struct OpenCLMatcher::Impl {
  // Serializes match(): OpenCL queue/buffers/self-cache are not re-entrant, and
  // Python bindings may release the GIL around match().
  std::mutex mutex;
  cl_device_id device = nullptr;
  cl_context context = nullptr;
  cl_command_queue queue = nullptr;
  cl_program program = nullptr;
  cl_kernel kernel = nullptr;
  cl_mem d_query = nullptr;
  cl_mem d_train = nullptr;
  cl_mem d_xy = nullptr;
  cl_mem d_match = nullptr;
  cl_mem d_score = nullptr;
  cl_mem d_amb = nullptr;
  cl_mem d_mx = nullptr;
  cl_mem d_my = nullptr;
  size_t query_desc_bytes = 0;
  size_t train_desc_bytes = 0;
  size_t xy_bytes = 0;
  size_t match_bytes = 0;
  size_t score_bytes = 0;
  size_t amb_bytes = 0;
  size_t mx_bytes = 0;
  size_t my_bytes = 0;
  const SiftFeature *cached_self = nullptr;
  size_t cached_self_count = 0;
  bool train_aliases_query = false;

  cl_mem ensure(cl_mem &buffer, size_t &capacity, size_t bytes, cl_mem_flags flags) {
    if (buffer && capacity >= bytes)
      return buffer;
    if (buffer)
      clReleaseMemObject(buffer);
    cl_int status = CL_SUCCESS;
    buffer = clCreateBuffer(context, flags, bytes, nullptr, &status);
    check_opencl(status, "clCreateBuffer(matcher scratch)");
    capacity = bytes;
    return buffer;
  }

  void invalidate_self_cache() {
    cached_self = nullptr;
    cached_self_count = 0;
  }

  Impl() {
    device = pick_gpu_device();
    cl_int status = CL_SUCCESS;
    context = clCreateContext(nullptr, 1, &device, nullptr, nullptr, &status);
    check_opencl(status, "clCreateContext(matcher)");
    queue = clCreateCommandQueue(context, device, 0, &status);
    check_opencl(status, "clCreateCommandQueue(matcher)");
    const char *source = kOpenCLSiftMatchKernelSource;
    const size_t length =
        std::char_traits<char>::length(kOpenCLSiftMatchKernelSource);
    program = clCreateProgramWithSource(context, 1, &source, &length, &status);
    check_opencl(status, "clCreateProgramWithSource(matcher)");
    status = clBuildProgram(program, 1, &device, nullptr, nullptr, nullptr);
    if (status != CL_SUCCESS) {
      size_t log_size = 0;
      clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, 0, nullptr,
                            &log_size);
      std::vector<char> log(log_size);
      clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, log.size(),
                            log.data(), nullptr);
      throw std::runtime_error(std::string("clBuildProgram(matcher) failed: ") +
                               log.data());
    }
    kernel = clCreateKernel(program, "match_sift_descriptors", &status);
    check_opencl(status, "clCreateKernel(match_sift_descriptors)");
  }

  ~Impl() {
    if (train_aliases_query)
      d_train = nullptr;
    for (cl_mem *buffer : {&d_query, &d_train, &d_xy, &d_match, &d_score, &d_amb,
                           &d_mx, &d_my}) {
      if (*buffer)
        clReleaseMemObject(*buffer);
    }
    if (kernel)
      clReleaseKernel(kernel);
    if (program)
      clReleaseProgram(program);
    if (queue)
      clReleaseCommandQueue(queue);
    if (context)
      clReleaseContext(context);
  }
};

OpenCLMatcher::OpenCLMatcher() : impl_(std::make_unique<Impl>()) {}
OpenCLMatcher::~OpenCLMatcher() = default;

std::vector<SiftMatchResult>
OpenCLMatcher::match(const std::vector<SiftFeature> &query,
                     const std::vector<SiftFeature> &train) {
  std::lock_guard<std::mutex> lock(impl_->mutex);
  if (query.empty())
    return {};
  if (train.empty()) {
    return std::vector<SiftMatchResult>(query.size());
  }

  const bool self_match = &query == &train;
  const int query_count = static_cast<int>(query.size());
  const int train_count = static_cast<int>(train.size());
  const size_t query_bytes = query.size() * 128u * sizeof(float);
  const size_t train_bytes = train.size() * 128u * sizeof(float);
  const size_t xy_bytes = train.size() * 2u * sizeof(float);

  // Warm self-match: keep descriptors/xy resident across repeated calls on the
  // same host vector (ladder Match timing; mirrors SYCL retained MatchSiftData).
  const bool warm_self =
      self_match && impl_->cached_self == query.data() &&
      impl_->cached_self_count == query.size() && impl_->d_query != nullptr &&
      impl_->train_aliases_query;

  if (!warm_self) {
    std::vector<float> query_desc;
    std::vector<float> train_desc;
    std::vector<float> query_xy_unused;
    std::vector<float> train_xy;
    pack_descriptors(query, query_desc, query_xy_unused);
    if (self_match) {
      train_xy.swap(query_xy_unused);
    } else {
      pack_descriptors(train, train_desc, train_xy);
    }

    // If train aliases query, drop the alias before possibly reallocating query.
    if (impl_->train_aliases_query) {
      impl_->d_train = nullptr;
      impl_->train_desc_bytes = 0;
      impl_->train_aliases_query = false;
    }
    impl_->ensure(impl_->d_query, impl_->query_desc_bytes, query_bytes,
                  CL_MEM_READ_ONLY);
    // Blocking writes: host staging vectors are released when this scope ends.
    check_opencl(clEnqueueWriteBuffer(impl_->queue, impl_->d_query, CL_TRUE, 0,
                                      query_bytes, query_desc.data(), 0, nullptr,
                                      nullptr),
                 "upload query descriptors");
    if (self_match) {
      if (impl_->d_train)
        clReleaseMemObject(impl_->d_train);
      impl_->d_train = impl_->d_query;
      impl_->train_desc_bytes = impl_->query_desc_bytes;
      impl_->train_aliases_query = true;
    } else {
      impl_->ensure(impl_->d_train, impl_->train_desc_bytes, train_bytes,
                    CL_MEM_READ_ONLY);
      check_opencl(clEnqueueWriteBuffer(impl_->queue, impl_->d_train, CL_TRUE, 0,
                                        train_bytes, train_desc.data(), 0,
                                        nullptr, nullptr),
                   "upload train descriptors");
    }
    impl_->ensure(impl_->d_xy, impl_->xy_bytes, xy_bytes, CL_MEM_READ_ONLY);
    check_opencl(clEnqueueWriteBuffer(impl_->queue, impl_->d_xy, CL_TRUE, 0,
                                      xy_bytes, train_xy.data(), 0, nullptr,
                                      nullptr),
                 "upload train xy");
    if (self_match) {
      impl_->cached_self = query.data();
      impl_->cached_self_count = query.size();
    } else {
      impl_->invalidate_self_cache();
    }
  }

  impl_->ensure(impl_->d_match, impl_->match_bytes,
                query.size() * sizeof(cl_int), CL_MEM_WRITE_ONLY);
  impl_->ensure(impl_->d_score, impl_->score_bytes,
                query.size() * sizeof(float), CL_MEM_WRITE_ONLY);
  impl_->ensure(impl_->d_amb, impl_->amb_bytes, query.size() * sizeof(float),
                CL_MEM_WRITE_ONLY);
  impl_->ensure(impl_->d_mx, impl_->mx_bytes, query.size() * sizeof(float),
                CL_MEM_WRITE_ONLY);
  impl_->ensure(impl_->d_my, impl_->my_bytes, query.size() * sizeof(float),
                CL_MEM_WRITE_ONLY);

  check_opencl(clSetKernelArg(impl_->kernel, 0, sizeof(impl_->d_query),
                              &impl_->d_query),
               "set query");
  check_opencl(clSetKernelArg(impl_->kernel, 1, sizeof(impl_->d_train),
                              &impl_->d_train),
               "set train");
  check_opencl(clSetKernelArg(impl_->kernel, 2, sizeof(impl_->d_xy), &impl_->d_xy),
               "set xy");
  check_opencl(clSetKernelArg(impl_->kernel, 3, sizeof(impl_->d_match),
                              &impl_->d_match),
               "set match");
  check_opencl(clSetKernelArg(impl_->kernel, 4, sizeof(impl_->d_score),
                              &impl_->d_score),
               "set score");
  check_opencl(clSetKernelArg(impl_->kernel, 5, sizeof(impl_->d_amb),
                              &impl_->d_amb),
               "set ambiguity");
  check_opencl(clSetKernelArg(impl_->kernel, 6, sizeof(impl_->d_mx), &impl_->d_mx),
               "set mx");
  check_opencl(clSetKernelArg(impl_->kernel, 7, sizeof(impl_->d_my), &impl_->d_my),
               "set my");
  check_opencl(
      clSetKernelArg(impl_->kernel, 8, sizeof(query_count), &query_count),
      "set query_count");
  check_opencl(
      clSetKernelArg(impl_->kernel, 9, sizeof(train_count), &train_count),
      "set train_count");

  constexpr size_t tile = 16;
  const size_t local = tile;
  const size_t groups = (static_cast<size_t>(query_count) + tile - 1u) / tile;
  const size_t global = groups * tile;
  check_opencl(clEnqueueNDRangeKernel(impl_->queue, impl_->kernel, 1, nullptr,
                                      &global, &local, 0, nullptr, nullptr),
               "clEnqueueNDRangeKernel(match)");

  std::vector<cl_int> match_index(query.size());
  std::vector<float> scores(query.size());
  std::vector<float> amb(query.size());
  std::vector<float> mx(query.size());
  std::vector<float> my(query.size());
  check_opencl(clEnqueueReadBuffer(impl_->queue, impl_->d_match, CL_FALSE, 0,
                                   match_index.size() * sizeof(cl_int),
                                   match_index.data(), 0, nullptr, nullptr),
               "read match");
  check_opencl(clEnqueueReadBuffer(impl_->queue, impl_->d_score, CL_FALSE, 0,
                                   scores.size() * sizeof(float), scores.data(),
                                   0, nullptr, nullptr),
               "read score");
  check_opencl(clEnqueueReadBuffer(impl_->queue, impl_->d_amb, CL_FALSE, 0,
                                   amb.size() * sizeof(float), amb.data(), 0,
                                   nullptr, nullptr),
               "read ambiguity");
  check_opencl(clEnqueueReadBuffer(impl_->queue, impl_->d_mx, CL_FALSE, 0,
                                   mx.size() * sizeof(float), mx.data(), 0,
                                   nullptr, nullptr),
               "read mx");
  check_opencl(clEnqueueReadBuffer(impl_->queue, impl_->d_my, CL_TRUE, 0,
                                   my.size() * sizeof(float), my.data(), 0,
                                   nullptr, nullptr),
               "read my");

  std::vector<SiftMatchResult> results(query.size());
  for (std::size_t i = 0; i < query.size(); ++i) {
    results[i].match = static_cast<int>(match_index[i]);
    results[i].score = scores[i];
    results[i].ambiguity = amb[i];
    results[i].match_x = mx[i];
    results[i].match_y = my[i];
  }
  return results;
}

} // namespace sift_extractor
