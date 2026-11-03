// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#define CL_TARGET_OPENCL_VERSION 120

#include "sift_extractor/opencl_matcher.hpp"

#include <CL/cl.h>

#include <cmath>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

namespace sift_extractor::experimental {
namespace {

void check_opencl(cl_int status, const char *operation) {
  if (status != CL_SUCCESS) {
    throw std::runtime_error(std::string(operation) +
                             " failed with OpenCL status " +
                             std::to_string(status));
  }
}

constexpr const char *kMatchKernelSource = R"CLC(
#define TILE 16
#define DESCRIPTOR_SIZE 128

__kernel void match_sift_descriptors(
    __global const float *query_desc,
    __global const float *train_desc,
    __global const float *train_xy,
    __global int *match_index,
    __global float *best_score,
    __global float *ambiguity,
    __global float *match_x,
    __global float *match_y,
    const int query_count,
    const int train_count) {
  __local float train_tile[TILE * DESCRIPTOR_SIZE];
  const int lane = get_local_id(0);
  const int query_index = get_group_id(0) * TILE + lane;

  float query[DESCRIPTOR_SIZE];
  float best = -1.0f;
  float second = -1.0f;
  int best_index = -1;

  if (query_index < query_count) {
    const int base = query_index * DESCRIPTOR_SIZE;
    for (int d = 0; d < DESCRIPTOR_SIZE; d += 4) {
      query[d + 0] = query_desc[base + d + 0];
      query[d + 1] = query_desc[base + d + 1];
      query[d + 2] = query_desc[base + d + 2];
      query[d + 3] = query_desc[base + d + 3];
    }
  }

  for (int base = 0; base < train_count; base += TILE) {
    const int load_index = base + lane;
    if (load_index < train_count) {
      const int src = load_index * DESCRIPTOR_SIZE;
      const int dst = lane * DESCRIPTOR_SIZE;
      for (int d = 0; d < DESCRIPTOR_SIZE; d += 4) {
        train_tile[dst + d + 0] = train_desc[src + d + 0];
        train_tile[dst + d + 1] = train_desc[src + d + 1];
        train_tile[dst + d + 2] = train_desc[src + d + 2];
        train_tile[dst + d + 3] = train_desc[src + d + 3];
      }
    }
    barrier(CLK_LOCAL_MEM_FENCE);

    const int tile_count = min(TILE, train_count - base);
    if (query_index < query_count) {
      for (int candidate = 0; candidate < tile_count; ++candidate) {
        float dot = 0.0f;
        const int cand_base = candidate * DESCRIPTOR_SIZE;
        for (int d = 0; d < DESCRIPTOR_SIZE; d += 4) {
          float4 q = (float4)(query[d + 0], query[d + 1], query[d + 2],
                              query[d + 3]);
          float4 t = (float4)(train_tile[cand_base + d + 0],
                              train_tile[cand_base + d + 1],
                              train_tile[cand_base + d + 2],
                              train_tile[cand_base + d + 3]);
          float4 p = q * t;
          dot += p.x + p.y + p.z + p.w;
        }
        if (dot > best) {
          second = best;
          best = dot;
          best_index = base + candidate;
        } else if (dot > second) {
          second = dot;
        }
      }
    }
    barrier(CLK_LOCAL_MEM_FENCE);
  }

  if (query_index < query_count) {
    match_index[query_index] = best_index;
    best_score[query_index] = best;
    ambiguity[query_index] =
        (second >= 0.0f) ? (second / (best + 1.0e-6f)) : 1.0f;
    match_x[query_index] =
        (best_index >= 0) ? train_xy[best_index * 2 + 0] : 0.0f;
    match_y[query_index] =
        (best_index >= 0) ? train_xy[best_index * 2 + 1] : 0.0f;
  }
}
)CLC";

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
  cl_device_id device = nullptr;
  cl_context context = nullptr;
  cl_command_queue queue = nullptr;
  cl_program program = nullptr;
  cl_kernel kernel = nullptr;

  Impl() {
    device = pick_gpu_device();
    cl_int status = CL_SUCCESS;
    context = clCreateContext(nullptr, 1, &device, nullptr, nullptr, &status);
    check_opencl(status, "clCreateContext(matcher)");
    queue = clCreateCommandQueue(context, device, 0, &status);
    check_opencl(status, "clCreateCommandQueue(matcher)");
    const char *source = kMatchKernelSource;
    const size_t length = std::char_traits<char>::length(kMatchKernelSource);
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
  if (query.empty())
    return {};
  if (train.empty()) {
    return std::vector<SiftMatchResult>(query.size());
  }

  std::vector<float> query_desc;
  std::vector<float> train_desc;
  std::vector<float> query_xy_unused;
  std::vector<float> train_xy;
  pack_descriptors(query, query_desc, query_xy_unused);
  pack_descriptors(train, train_desc, train_xy);

  const int query_count = static_cast<int>(query.size());
  const int train_count = static_cast<int>(train.size());
  cl_int status = CL_SUCCESS;

  cl_mem d_query = clCreateBuffer(
      impl_->context, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR,
      query_desc.size() * sizeof(float), query_desc.data(), &status);
  check_opencl(status, "clCreateBuffer(query descriptors)");
  cl_mem d_train = clCreateBuffer(
      impl_->context, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR,
      train_desc.size() * sizeof(float), train_desc.data(), &status);
  check_opencl(status, "clCreateBuffer(train descriptors)");
  cl_mem d_xy = clCreateBuffer(impl_->context,
                               CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR,
                               train_xy.size() * sizeof(float), train_xy.data(),
                               &status);
  check_opencl(status, "clCreateBuffer(train xy)");
  cl_mem d_match = clCreateBuffer(impl_->context, CL_MEM_WRITE_ONLY,
                                  query.size() * sizeof(cl_int), nullptr,
                                  &status);
  check_opencl(status, "clCreateBuffer(match index)");
  cl_mem d_score = clCreateBuffer(impl_->context, CL_MEM_WRITE_ONLY,
                                  query.size() * sizeof(float), nullptr,
                                  &status);
  check_opencl(status, "clCreateBuffer(best score)");
  cl_mem d_amb = clCreateBuffer(impl_->context, CL_MEM_WRITE_ONLY,
                                query.size() * sizeof(float), nullptr, &status);
  check_opencl(status, "clCreateBuffer(ambiguity)");
  cl_mem d_mx = clCreateBuffer(impl_->context, CL_MEM_WRITE_ONLY,
                               query.size() * sizeof(float), nullptr, &status);
  check_opencl(status, "clCreateBuffer(match x)");
  cl_mem d_my = clCreateBuffer(impl_->context, CL_MEM_WRITE_ONLY,
                               query.size() * sizeof(float), nullptr, &status);
  check_opencl(status, "clCreateBuffer(match y)");

  check_opencl(clSetKernelArg(impl_->kernel, 0, sizeof(d_query), &d_query),
               "set query");
  check_opencl(clSetKernelArg(impl_->kernel, 1, sizeof(d_train), &d_train),
               "set train");
  check_opencl(clSetKernelArg(impl_->kernel, 2, sizeof(d_xy), &d_xy), "set xy");
  check_opencl(clSetKernelArg(impl_->kernel, 3, sizeof(d_match), &d_match),
               "set match");
  check_opencl(clSetKernelArg(impl_->kernel, 4, sizeof(d_score), &d_score),
               "set score");
  check_opencl(clSetKernelArg(impl_->kernel, 5, sizeof(d_amb), &d_amb),
               "set ambiguity");
  check_opencl(clSetKernelArg(impl_->kernel, 6, sizeof(d_mx), &d_mx), "set mx");
  check_opencl(clSetKernelArg(impl_->kernel, 7, sizeof(d_my), &d_my), "set my");
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
  check_opencl(clEnqueueReadBuffer(impl_->queue, d_match, CL_FALSE, 0,
                                   match_index.size() * sizeof(cl_int),
                                   match_index.data(), 0, nullptr, nullptr),
               "read match");
  check_opencl(clEnqueueReadBuffer(impl_->queue, d_score, CL_FALSE, 0,
                                   scores.size() * sizeof(float), scores.data(),
                                   0, nullptr, nullptr),
               "read score");
  check_opencl(clEnqueueReadBuffer(impl_->queue, d_amb, CL_FALSE, 0,
                                   amb.size() * sizeof(float), amb.data(), 0,
                                   nullptr, nullptr),
               "read ambiguity");
  check_opencl(clEnqueueReadBuffer(impl_->queue, d_mx, CL_FALSE, 0,
                                   mx.size() * sizeof(float), mx.data(), 0,
                                   nullptr, nullptr),
               "read mx");
  check_opencl(clEnqueueReadBuffer(impl_->queue, d_my, CL_TRUE, 0,
                                   my.size() * sizeof(float), my.data(), 0,
                                   nullptr, nullptr),
               "read my");

  clReleaseMemObject(d_query);
  clReleaseMemObject(d_train);
  clReleaseMemObject(d_xy);
  clReleaseMemObject(d_match);
  clReleaseMemObject(d_score);
  clReleaseMemObject(d_amb);
  clReleaseMemObject(d_mx);
  clReleaseMemObject(d_my);

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

} // namespace sift_extractor::experimental
