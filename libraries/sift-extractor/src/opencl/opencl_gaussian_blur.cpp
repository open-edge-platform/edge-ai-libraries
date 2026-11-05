// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#define CL_TARGET_OPENCL_VERSION 120

#include "opencl_gaussian_blur.hpp"
#include "opencl_gaussian_pyramid.hpp"

#include <CL/cl.h>
#include <CL/cl_ext.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace sift_extractor::detail {
namespace {

constexpr const char *kernel_source = R"CLC(
__kernel void gaussian_horizontal(__global const float *source,
                                  __global float *temporary,
                                  __global const float *weights,
                                  const int width, const int height,
                                  const int radius) {
  const int x = (int)get_global_id(0);
  const int y = (int)get_global_id(1);
  if (x >= width || y >= height)
    return;

  float sum = 0.0f;
  for (int offset = -radius; offset <= radius; ++offset) {
    const int sample_x = clamp(x + offset, 0, width - 1);
    sum += source[y * width + sample_x] * weights[offset + radius];
  }
  temporary[y * width + x] = sum;
}

__kernel void gaussian_vertical(__global const float *temporary,
                                __global float *destination,
                                __global const float *weights,
                                const int width, const int height,
                                const int radius) {
  const int x = (int)get_global_id(0);
  const int y = (int)get_global_id(1);
  if (x >= width || y >= height)
    return;

  float sum = 0.0f;
  for (int offset = -radius; offset <= radius; ++offset) {
    const int sample_y = clamp(y + offset, 0, height - 1);
    sum += temporary[sample_y * width + x] * weights[offset + radius];
  }
  destination[y * width + x] = sum;
}

__kernel void gaussian_vertical_dog(__global const float *temporary,
                                    __global float *destination,
                                    __global const float *weights,
                                    const int width, const int height,
                                    const int radius,
                                    __global const float *lower,
                                    __global float *difference) {
  const int x = (int)get_global_id(0);
  const int y = (int)get_global_id(1);
  if (x >= width || y >= height) return;
  float sum = 0.0f;
  for (int offset = -radius; offset <= radius; ++offset) {
    const int sample_y = clamp(y + offset, 0, height - 1);
    sum += temporary[sample_y * width + x] * weights[offset + radius];
  }
  const int index = y * width + x;
  destination[index] = sum;
  difference[index] = sum - lower[index];
}

__kernel void gaussian_fused(__global const float *source,
                             __global float *destination,
                             __global const float *weights,
                             const int width, const int height,
                             const int radius,
                             __global const float *lower,
                             __global float *difference,
                             const int write_difference) {
  __local float horizontal_tile[16 * 40];
  const int local_x = (int)get_local_id(0);
  const int local_y = (int)get_local_id(1);
  const int pixel_x = (int)get_global_id(0);
  const int pixel_y = (int)get_global_id(1);
  for (int tile_y = local_y; tile_y < 16 + 2 * radius; tile_y += 16) {
    const int sample_y = clamp((int)get_group_id(1) * 16 + tile_y - radius, 0, height - 1);
    float sum = 0.0f;
    for (int offset = -radius; offset <= radius; ++offset) {
      const int sample_x = clamp(pixel_x + offset, 0, width - 1);
      sum += source[sample_y * width + sample_x] * weights[offset + radius];
    }
    horizontal_tile[tile_y * 16 + local_x] = sum;
  }
  barrier(CLK_LOCAL_MEM_FENCE);
  if (pixel_x >= width || pixel_y >= height) return;
  float sum = 0.0f;
  for (int offset = -radius; offset <= radius; ++offset)
    sum += horizontal_tile[(local_y + radius + offset) * 16 + local_x] * weights[offset + radius];
  const int index = pixel_y * width + pixel_x;
  destination[index] = sum;
  if (write_difference) difference[index] = sum - lower[index];
}

__kernel void difference_of_gaussians(__global const float *first,
                                      __global const float *second,
                                      __global float *destination,
                                      const int width, const int height) {
  const int x = (int)get_global_id(0);
  const int y = (int)get_global_id(1);
  if (x >= width || y >= height)
    return;
  const int index = y * width + x;
  destination[index] = first[index] - second[index];
}

__kernel void downsample_by_two(__global const float *source,
                                __global float *destination,
                                const int width, const int height,
                                const int output_width,
                                const int output_height) {
  const int x = (int)get_global_id(0);
  const int y = (int)get_global_id(1);
  if (x >= output_width || y >= output_height)
    return;
  destination[y * output_width + x] = source[(2 * y) * width + (2 * x)];
}
)CLC";

void check_opencl(cl_int status, const char *operation) {
  if (status != CL_SUCCESS) {
    throw std::runtime_error(std::string(operation) + " failed with OpenCL status " +
                             std::to_string(status));
  }
}

cl_device_id select_intel_gpu() {
  cl_uint platform_count = 0;
  const cl_int platform_status =
      clGetPlatformIDs(0, nullptr, &platform_count);
  if (platform_status == CL_PLATFORM_NOT_FOUND_KHR || platform_count == 0)
    throw std::runtime_error("No OpenCL platforms are available");
  check_opencl(platform_status, "clGetPlatformIDs(count)");

  std::vector<cl_platform_id> platforms(platform_count);
  check_opencl(clGetPlatformIDs(platform_count, platforms.data(), nullptr),
               "clGetPlatformIDs(list)");

  for (cl_platform_id platform : platforms) {
    size_t vendor_size = 0;
    if (clGetPlatformInfo(platform, CL_PLATFORM_VENDOR, 0, nullptr,
                          &vendor_size) != CL_SUCCESS)
      continue;
    std::vector<char> vendor(vendor_size);
    if (clGetPlatformInfo(platform, CL_PLATFORM_VENDOR, vendor.size(),
                          vendor.data(), nullptr) != CL_SUCCESS)
      continue;
    if (std::string(vendor.data()).find("Intel") == std::string::npos)
      continue;

    cl_uint device_count = 0;
    const cl_int device_status = clGetDeviceIDs(
        platform, CL_DEVICE_TYPE_GPU, 0, nullptr, &device_count);
    if (device_status == CL_DEVICE_NOT_FOUND || device_count == 0)
      continue;
    check_opencl(device_status, "clGetDeviceIDs(count)");

    std::vector<cl_device_id> devices(device_count);
    check_opencl(clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, device_count,
                                devices.data(), nullptr),
                 "clGetDeviceIDs(list)");
    return devices.front();
  }

  throw std::runtime_error("No Intel OpenCL GPU is available");
}

cl_mem create_buffer(cl_context context, cl_mem_flags flags, size_t bytes,
                     void *host_ptr = nullptr) {
  cl_int status = CL_SUCCESS;
  cl_mem buffer = clCreateBuffer(context, flags, bytes, host_ptr, &status);
  check_opencl(status, "clCreateBuffer");
  return buffer;
}

} // namespace

struct OpenCLGaussianBlur::Impl {
  struct Buffer {
    cl_mem memory = nullptr;
    size_t capacity = 0;
  };

  cl_device_id device = nullptr;
  cl_context context = nullptr;
  cl_command_queue queue = nullptr;
  bool profiling = false;
  cl_program program = nullptr;
  cl_kernel horizontal = nullptr;
  cl_kernel vertical = nullptr;
  cl_kernel vertical_dog = nullptr;
  cl_kernel fused_gaussian = nullptr;
  cl_kernel dog = nullptr;
  cl_kernel downsample = nullptr;
  Buffer input;
  Buffer pyramid_input;
  Buffer second_input;
  Buffer temporary;
  Buffer output;
  Buffer weights;
  std::vector<Buffer> gaussian_levels;
  Buffer gaussian_volume;
  std::vector<size_t> gaussian_plane_bytes;
  bool gaussian_packed = false;
  std::vector<Buffer> dog_levels;
  std::vector<Buffer> dog_volumes;
  std::vector<size_t> dog_plane_bytes;
  int dog_intervals = 0;
  std::vector<Buffer> pyramid_weights;
  std::vector<std::vector<float>> cached_kernels;

  cl_kernel fused_vertical_kernel() {
    if (!vertical_dog) {
      cl_int status = CL_SUCCESS;
      vertical_dog = clCreateKernel(program, "gaussian_vertical_dog", &status);
      check_opencl(status, "clCreateKernel(fused Gaussian DoG)");
    }
    return vertical_dog;
  }

  cl_mem ensure_buffer(Buffer &buffer, cl_mem_flags flags, size_t bytes) {
    if (buffer.memory && buffer.capacity >= bytes)
      return buffer.memory;
    cl_mem replacement = create_buffer(context, flags, bytes);
    if (buffer.memory)
      clReleaseMemObject(buffer.memory);
    buffer.memory = replacement;
    buffer.capacity = bytes;
    return buffer.memory;
  }

  void write_buffer(cl_mem buffer, const void *source, size_t bytes,
                    const char *operation) {
    check_opencl(clEnqueueWriteBuffer(queue, buffer, CL_TRUE, 0, bytes, source,
                                      0, nullptr, nullptr), operation);
  }

  explicit Impl(cl_command_queue shared_queue = nullptr) {
    cl_int status = CL_SUCCESS;
    if (shared_queue) {
      cl_command_queue_properties properties = 0;
      check_opencl(clGetCommandQueueInfo(shared_queue, CL_QUEUE_PROPERTIES,
          sizeof(properties), &properties, nullptr), "clGetCommandQueueInfo(properties)");
      if (properties & CL_QUEUE_OUT_OF_ORDER_EXEC_MODE_ENABLE)
        throw std::invalid_argument("Gaussian stages require an in-order queue");
      profiling = (properties & CL_QUEUE_PROFILING_ENABLE) != 0;
      check_opencl(clGetCommandQueueInfo(shared_queue, CL_QUEUE_DEVICE,
          sizeof(device), &device, nullptr), "clGetCommandQueueInfo(device)");
      check_opencl(clGetCommandQueueInfo(shared_queue, CL_QUEUE_CONTEXT,
          sizeof(context), &context, nullptr), "clGetCommandQueueInfo(context)");
      check_opencl(clRetainContext(context), "clRetainContext");
      status = clRetainCommandQueue(shared_queue);
      if (status != CL_SUCCESS) {
        clReleaseContext(context);
        check_opencl(status, "clRetainCommandQueue");
      }
      queue = shared_queue;
    } else {
      device = select_intel_gpu();
      context = clCreateContext(nullptr, 1, &device, nullptr, nullptr, &status);
      check_opencl(status, "clCreateContext");
      queue = clCreateCommandQueue(context, device, 0, &status);
      if (status != CL_SUCCESS) {
        clReleaseContext(context);
        context = nullptr;
        check_opencl(status, "clCreateCommandQueue");
      }
    }

    const size_t source_length = std::char_traits<char>::length(kernel_source);
    const char *source_pointer = kernel_source;
    program = clCreateProgramWithSource(context, 1, &source_pointer,
                                        &source_length, &status);
    if (status != CL_SUCCESS) {
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      queue = nullptr;
      context = nullptr;
      check_opencl(status, "clCreateProgramWithSource");
    }

    status = clBuildProgram(program, 1, &device, "-cl-std=CL1.2", nullptr,
                            nullptr);
    if (status != CL_SUCCESS) {
      size_t log_size = 0;
      clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, 0, nullptr,
                            &log_size);
      std::vector<char> log(log_size + 1, '\0');
      clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, log_size,
                            log.data(), nullptr);
      clReleaseProgram(program);
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      program = nullptr;
      queue = nullptr;
      context = nullptr;
      throw std::runtime_error(std::string("OpenCL Gaussian kernel build failed: ") +
                               log.data());
    }

    horizontal = clCreateKernel(program, "gaussian_horizontal", &status);
    if (status != CL_SUCCESS) {
      clReleaseProgram(program);
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      program = nullptr;
      queue = nullptr;
      context = nullptr;
      check_opencl(status, "clCreateKernel(gaussian_horizontal)");
    }

    vertical = clCreateKernel(program, "gaussian_vertical", &status);
    if (status != CL_SUCCESS) {
      clReleaseKernel(horizontal);
      clReleaseProgram(program);
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      horizontal = nullptr;
      program = nullptr;
      queue = nullptr;
      context = nullptr;
      check_opencl(status, "clCreateKernel(gaussian_vertical)");
    }

    dog = clCreateKernel(program, "difference_of_gaussians", &status);
    if (status != CL_SUCCESS) {
      clReleaseKernel(vertical);
      clReleaseKernel(horizontal);
      clReleaseProgram(program);
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      vertical = nullptr;
      horizontal = nullptr;
      program = nullptr;
      queue = nullptr;
      context = nullptr;
      check_opencl(status, "clCreateKernel(difference_of_gaussians)");
    }

    downsample = clCreateKernel(program, "downsample_by_two", &status);
    if (status != CL_SUCCESS) {
      clReleaseKernel(dog);
      clReleaseKernel(vertical);
      clReleaseKernel(horizontal);
      clReleaseProgram(program);
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      dog = nullptr;
      vertical = nullptr;
      horizontal = nullptr;
      program = nullptr;
      queue = nullptr;
      context = nullptr;
      check_opencl(status, "clCreateKernel(downsample_by_two)");
    }
  }

  ~Impl() {
    for (auto &buffer : pyramid_weights)
      if (buffer.memory) clReleaseMemObject(buffer.memory);
    for (auto &buffer : dog_levels)
      if (buffer.memory) clReleaseMemObject(buffer.memory);
    for (auto &buffer : dog_volumes)
      if (buffer.memory) clReleaseMemObject(buffer.memory);
    for (auto &buffer : gaussian_levels)
      if (buffer.memory) clReleaseMemObject(buffer.memory);
    if (gaussian_volume.memory) clReleaseMemObject(gaussian_volume.memory);
    if (weights.memory)
      clReleaseMemObject(weights.memory);
    if (output.memory)
      clReleaseMemObject(output.memory);
    if (temporary.memory)
      clReleaseMemObject(temporary.memory);
    if (second_input.memory)
      clReleaseMemObject(second_input.memory);
    if (input.memory)
      clReleaseMemObject(input.memory);
    if (pyramid_input.memory)
      clReleaseMemObject(pyramid_input.memory);
    if (downsample)
      clReleaseKernel(downsample);
    if (dog)
      clReleaseKernel(dog);
    if (vertical)
      clReleaseKernel(vertical);
    if (vertical_dog)
      clReleaseKernel(vertical_dog);
    if (fused_gaussian)
      clReleaseKernel(fused_gaussian);
    if (horizontal)
      clReleaseKernel(horizontal);
    if (program)
      clReleaseProgram(program);
    if (queue)
      clReleaseCommandQueue(queue);
    if (context)
      clReleaseContext(context);
  }
};

OpenCLGaussianBlur::OpenCLGaussianBlur() : impl_(new Impl()) {}

OpenCLGaussianBlur::OpenCLGaussianBlur(_cl_command_queue *queue)
  : impl_(new Impl(queue)) {}

OpenCLGaussianBlur::~OpenCLGaussianBlur() { delete impl_; }

std::vector<float> OpenCLGaussianBlur::apply(const std::vector<float> &image,
                                             int width, int height,
                                             const std::vector<float> &kernel) {
  if (width <= 0 || height <= 0 || kernel.empty() || (kernel.size() & 1u) == 0)
    throw std::invalid_argument("Image dimensions and odd kernel size are required");
  if (image.size() != static_cast<size_t>(width) * height)
    throw std::invalid_argument("Image buffer size does not match dimensions");
  for (float weight : kernel) {
    if (!std::isfinite(weight))
      throw std::invalid_argument("Gaussian weights must be finite");
  }

  const size_t bytes = image.size() * sizeof(float);
  const size_t weight_bytes = kernel.size() * sizeof(float);
  cl_mem source = impl_->ensure_buffer(impl_->input, CL_MEM_READ_ONLY, bytes);
  cl_mem temporary = impl_->ensure_buffer(impl_->temporary, CL_MEM_READ_WRITE,
                                           bytes);
  cl_mem destination = impl_->ensure_buffer(impl_->output, CL_MEM_WRITE_ONLY,
                                             bytes);
  cl_mem weights = impl_->ensure_buffer(impl_->weights, CL_MEM_READ_ONLY,
                                         weight_bytes);
  impl_->write_buffer(source, image.data(), bytes,
                      "clEnqueueWriteBuffer(blur source)");
  impl_->write_buffer(weights, kernel.data(), weight_bytes,
                      "clEnqueueWriteBuffer(blur weights)");

  try {
    const int radius = static_cast<int>(kernel.size() / 2);
    check_opencl(clSetKernelArg(impl_->horizontal, 0, sizeof(source), &source),
                 "clSetKernelArg(horizontal source)");
    check_opencl(clSetKernelArg(impl_->horizontal, 1, sizeof(temporary),
                                &temporary),
                 "clSetKernelArg(horizontal temporary)");
    check_opencl(clSetKernelArg(impl_->horizontal, 2, sizeof(weights), &weights),
                 "clSetKernelArg(horizontal weights)");
    check_opencl(clSetKernelArg(impl_->horizontal, 3, sizeof(width), &width),
                 "clSetKernelArg(horizontal width)");
    check_opencl(clSetKernelArg(impl_->horizontal, 4, sizeof(height), &height),
                 "clSetKernelArg(horizontal height)");
    check_opencl(clSetKernelArg(impl_->horizontal, 5, sizeof(radius), &radius),
                 "clSetKernelArg(horizontal radius)");

    const size_t global_size[2] = {static_cast<size_t>(width),
                                   static_cast<size_t>(height)};
    check_opencl(clEnqueueNDRangeKernel(impl_->queue, impl_->horizontal, 2,
                                        nullptr, global_size, nullptr, 0, nullptr,
                                        nullptr),
                 "clEnqueueNDRangeKernel(horizontal)");

    check_opencl(clSetKernelArg(impl_->vertical, 0, sizeof(temporary),
                                &temporary),
                 "clSetKernelArg(vertical temporary)");
    check_opencl(clSetKernelArg(impl_->vertical, 1, sizeof(destination),
                                &destination),
                 "clSetKernelArg(vertical destination)");
    check_opencl(clSetKernelArg(impl_->vertical, 2, sizeof(weights), &weights),
                 "clSetKernelArg(vertical weights)");
    check_opencl(clSetKernelArg(impl_->vertical, 3, sizeof(width), &width),
                 "clSetKernelArg(vertical width)");
    check_opencl(clSetKernelArg(impl_->vertical, 4, sizeof(height), &height),
                 "clSetKernelArg(vertical height)");
    check_opencl(clSetKernelArg(impl_->vertical, 5, sizeof(radius), &radius),
                 "clSetKernelArg(vertical radius)");
    check_opencl(clEnqueueNDRangeKernel(impl_->queue, impl_->vertical, 2,
                                        nullptr, global_size, nullptr, 0, nullptr,
                                        nullptr),
                 "clEnqueueNDRangeKernel(vertical)");

    std::vector<float> output(image.size());
    check_opencl(clEnqueueReadBuffer(impl_->queue, destination, CL_TRUE, 0,
                                     bytes, output.data(), 0, nullptr, nullptr),
                 "clEnqueueReadBuffer(blurred image)");

    return output;
  } catch (...) {
    throw;
  }
}

std::vector<float> OpenCLGaussianBlur::difference_of_gaussians(
    const std::vector<float> &first, const std::vector<float> &second,
    int width, int height) {
  if (width <= 0 || height <= 0)
    throw std::invalid_argument("Image dimensions must be positive");
  const size_t element_count = static_cast<size_t>(width) * height;
  if (first.size() != element_count || second.size() != element_count)
    throw std::invalid_argument("DoG image buffers must match dimensions");
  for (size_t i = 0; i < element_count; ++i) {
    if (!std::isfinite(first[i]) || !std::isfinite(second[i]))
      throw std::invalid_argument("DoG input values must be finite");
  }

  const size_t bytes = element_count * sizeof(float);
  cl_mem first_buffer = impl_->ensure_buffer(impl_->input, CL_MEM_READ_ONLY,
                                              bytes);
  cl_mem second_buffer = impl_->ensure_buffer(impl_->second_input,
                                               CL_MEM_READ_ONLY, bytes);
  cl_mem destination = impl_->ensure_buffer(impl_->output, CL_MEM_WRITE_ONLY,
                                             bytes);
  impl_->write_buffer(first_buffer, first.data(), bytes,
                      "clEnqueueWriteBuffer(DoG first)");
  impl_->write_buffer(second_buffer, second.data(), bytes,
                      "clEnqueueWriteBuffer(DoG second)");

  try {
    check_opencl(clSetKernelArg(impl_->dog, 0, sizeof(first_buffer),
                                &first_buffer),
                 "clSetKernelArg(DoG first)");
    check_opencl(clSetKernelArg(impl_->dog, 1, sizeof(second_buffer),
                                &second_buffer),
                 "clSetKernelArg(DoG second)");
    check_opencl(clSetKernelArg(impl_->dog, 2, sizeof(destination),
                                &destination),
                 "clSetKernelArg(DoG destination)");
    check_opencl(clSetKernelArg(impl_->dog, 3, sizeof(width), &width),
                 "clSetKernelArg(DoG width)");
    check_opencl(clSetKernelArg(impl_->dog, 4, sizeof(height), &height),
                 "clSetKernelArg(DoG height)");

    const size_t global_size[2] = {static_cast<size_t>(width),
                                   static_cast<size_t>(height)};
    check_opencl(clEnqueueNDRangeKernel(impl_->queue, impl_->dog, 2, nullptr,
                                        global_size, nullptr, 0, nullptr,
                                        nullptr),
                 "clEnqueueNDRangeKernel(DoG)");

    std::vector<float> result(element_count);
    check_opencl(clEnqueueReadBuffer(impl_->queue, destination, CL_TRUE, 0,
                                     bytes, result.data(), 0, nullptr, nullptr),
                 "clEnqueueReadBuffer(DoG)");

    return result;
  } catch (...) {
    throw;
  }
}

std::vector<float> OpenCLGaussianBlur::downsample_by_two(
    const std::vector<float> &image, int width, int height, int &output_width,
    int &output_height) {
  if (width <= 0 || height <= 0)
    throw std::invalid_argument("Image dimensions must be positive");
  if (image.size() != static_cast<size_t>(width) * height)
    throw std::invalid_argument("Image buffer size does not match dimensions");
  output_width = (width + 1) / 2;
  output_height = (height + 1) / 2;
  const size_t input_bytes = image.size() * sizeof(float);
  const size_t output_count =
      static_cast<size_t>(output_width) * output_height;
  const size_t output_bytes = output_count * sizeof(float);
  cl_mem source = impl_->ensure_buffer(impl_->input, CL_MEM_READ_ONLY,
                                        input_bytes);
  cl_mem destination = impl_->ensure_buffer(impl_->output, CL_MEM_WRITE_ONLY,
                                             output_bytes);
  impl_->write_buffer(source, image.data(), input_bytes,
                      "clEnqueueWriteBuffer(downsample source)");
  try {
    check_opencl(clSetKernelArg(impl_->downsample, 0, sizeof(source), &source),
                 "clSetKernelArg(downsample source)");
    check_opencl(clSetKernelArg(impl_->downsample, 1, sizeof(destination),
                                &destination),
                 "clSetKernelArg(downsample destination)");
    check_opencl(clSetKernelArg(impl_->downsample, 2, sizeof(width), &width),
                 "clSetKernelArg(downsample width)");
    check_opencl(clSetKernelArg(impl_->downsample, 3, sizeof(height), &height),
                 "clSetKernelArg(downsample height)");
    check_opencl(clSetKernelArg(impl_->downsample, 4, sizeof(output_width),
                                &output_width),
                 "clSetKernelArg(downsample output width)");
    check_opencl(clSetKernelArg(impl_->downsample, 5, sizeof(output_height),
                                &output_height),
                 "clSetKernelArg(downsample output height)");

    const size_t global_size[2] = {static_cast<size_t>(output_width),
                                   static_cast<size_t>(output_height)};
    check_opencl(clEnqueueNDRangeKernel(impl_->queue, impl_->downsample, 2,
                                        nullptr, global_size, nullptr, 0, nullptr,
                                        nullptr),
                 "clEnqueueNDRangeKernel(downsample)");

    std::vector<float> result(output_count);
    check_opencl(clEnqueueReadBuffer(impl_->queue, destination, CL_TRUE, 0,
                                     output_bytes, result.data(), 0, nullptr,
                                     nullptr),
                 "clEnqueueReadBuffer(downsample)");
    return result;
  } catch (...) {
    throw;
  }
}

void OpenCLGaussianBlur::build_pyramid(
    const std::vector<float> &image, std::vector<GaussianLevel> &gaussian,
    std::vector<DoGLevel> &differences,
  const std::vector<std::vector<float>> &kernels, int intervals,
  std::vector<_cl_mem *> *device_differences,
  std::vector<_cl_mem *> *device_gaussian, bool wait_for_completion) {
  const size_t image_bytes = image.size() * sizeof(float);
  cl_mem input = impl_->ensure_buffer(impl_->pyramid_input,
    CL_MEM_READ_ONLY | CL_MEM_ALLOC_HOST_PTR, image_bytes);
  cl_mem temporary = impl_->ensure_buffer(impl_->temporary, CL_MEM_READ_WRITE,
                                         image_bytes);
  impl_->gaussian_levels.resize(std::max(impl_->gaussian_levels.size(), gaussian.size()));
  impl_->dog_levels.resize(std::max(impl_->dog_levels.size(), differences.size()));
  impl_->pyramid_weights.resize(std::max(impl_->pyramid_weights.size(), kernels.size()));
  impl_->cached_kernels.resize(std::max(impl_->cached_kernels.size(), kernels.size()));
  cl_uint alignment_bits = 0;
  check_opencl(clGetDeviceInfo(impl_->device, CL_DEVICE_MEM_BASE_ADDR_ALIGN,
    sizeof(alignment_bits), &alignment_bits, nullptr), "Pyramid buffer alignment");
  const size_t alignment_bytes = std::max<size_t>(1, (static_cast<size_t>(alignment_bits) + 7) / 8);
  cl_ulong maximum_allocation = 0;
  check_opencl(clGetDeviceInfo(impl_->device, CL_DEVICE_MAX_MEM_ALLOC_SIZE,
    sizeof(maximum_allocation), &maximum_allocation, nullptr), "Pyramid allocation limit");
  const size_t packed_limit = static_cast<size_t>(std::min<cl_ulong>(maximum_allocation,
    static_cast<size_t>(std::numeric_limits<int>::max()) * sizeof(float)));
  std::vector<size_t> plane_bytes, plane_offsets;
  size_t packed_bytes = 0;
  bool packed_gaussian = true;
  for (const auto &level : gaussian) {
    const size_t bytes = static_cast<size_t>(level.width) * level.height * sizeof(float);
    plane_bytes.push_back(bytes);
    plane_offsets.push_back(packed_bytes);
    if (!packed_gaussian || bytes > packed_limit - packed_bytes) {
      packed_gaussian = false;
      continue;
    }
    packed_bytes += bytes;
    const size_t padding = (alignment_bytes - packed_bytes % alignment_bytes) % alignment_bytes;
    if (padding > packed_limit - packed_bytes) packed_gaussian = false;
    else packed_bytes += padding;
  }
  if (impl_->gaussian_plane_bytes != plane_bytes || impl_->gaussian_packed != packed_gaussian) {
    impl_->gaussian_plane_bytes.clear();
    for (auto &buffer : impl_->gaussian_levels) {
      if (buffer.memory) clReleaseMemObject(buffer.memory);
      buffer = {};
    }
    cl_mem volume = packed_gaussian ? impl_->ensure_buffer(impl_->gaussian_volume,
      CL_MEM_READ_WRITE, packed_bytes) : nullptr;
    if (!packed_gaussian && impl_->gaussian_volume.memory) {
      clReleaseMemObject(impl_->gaussian_volume.memory);
      impl_->gaussian_volume = {};
    }
    for (size_t index = 0; index < gaussian.size(); ++index) {
      auto &buffer = impl_->gaussian_levels[index];
      if (volume) {
        cl_buffer_region region{plane_offsets[index], plane_bytes[index]};
        cl_int status = CL_SUCCESS;
        buffer.memory = clCreateSubBuffer(volume, CL_MEM_READ_WRITE,
          CL_BUFFER_CREATE_TYPE_REGION, &region, &status);
        check_opencl(status, "clCreateSubBuffer(Gaussian level)");
        buffer.capacity = plane_bytes[index];
      } else {
        impl_->ensure_buffer(buffer, CL_MEM_READ_WRITE, plane_bytes[index]);
      }
    }
    impl_->gaussian_plane_bytes = std::move(plane_bytes);
    impl_->gaussian_packed = packed_gaussian;
  }
  if (device_gaussian) device_gaussian->resize(gaussian.size());
  for (size_t index = 0; index < gaussian.size(); ++index) {
    auto &level = gaussian[index];
    const size_t count = static_cast<size_t>(level.width) * level.height;
    if (!device_gaussian) level.pixels.resize(count);
    cl_mem memory = impl_->ensure_buffer(impl_->gaussian_levels[index], CL_MEM_READ_WRITE,
                                         count * sizeof(float));
    if (device_gaussian) (*device_gaussian)[index] = memory;
    if (!kernels[index].empty() && kernels[index] != impl_->cached_kernels[index]) {
      const size_t bytes = kernels[index].size() * sizeof(float);
      std::vector<float> cached = kernels[index];
      cl_mem replacement = create_buffer(impl_->context,
          CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, bytes, cached.data());
      auto &buffer = impl_->pyramid_weights[index];
      if (buffer.memory) clReleaseMemObject(buffer.memory);
      buffer = {replacement, bytes};
      impl_->cached_kernels[index] = std::move(cached);
    }
  }
  if (device_differences) device_differences->resize(differences.size());
  const size_t dog_scales = static_cast<size_t>(intervals + 2);
  const size_t dog_octaves = differences.size() / dog_scales;
  if (impl_->dog_intervals != intervals) {
    for (auto &buffer : impl_->dog_levels) {
      if (buffer.memory) clReleaseMemObject(buffer.memory);
      buffer = {};
    }
    std::fill(impl_->dog_plane_bytes.begin(), impl_->dog_plane_bytes.end(), 0);
    impl_->dog_intervals = intervals;
  }
  impl_->dog_volumes.resize(std::max(impl_->dog_volumes.size(), dog_octaves));
  impl_->dog_plane_bytes.resize(std::max(impl_->dog_plane_bytes.size(), dog_octaves));
  for (size_t octave = 0; octave < dog_octaves; ++octave) {
    const auto &level = differences[octave * dog_scales];
    const size_t bytes = static_cast<size_t>(level.width) * level.height * sizeof(float);
    if (impl_->dog_plane_bytes[octave] == bytes) continue;
    impl_->dog_plane_bytes[octave] = 0;
    for (size_t scale = 0; scale < dog_scales; ++scale) {
      auto &buffer = impl_->dog_levels[octave * dog_scales + scale];
      if (buffer.memory) clReleaseMemObject(buffer.memory);
      buffer = {};
    }
    const bool aligned = bytes % alignment_bytes == 0 &&
      bytes <= std::numeric_limits<size_t>::max() / dog_scales;
    cl_mem volume = aligned ? impl_->ensure_buffer(impl_->dog_volumes[octave],
      CL_MEM_READ_WRITE, bytes * dog_scales) : nullptr;
    for (size_t scale = 0; scale < dog_scales; ++scale) {
      auto &buffer = impl_->dog_levels[octave * dog_scales + scale];
      if (volume) {
        cl_buffer_region region{scale * bytes, bytes};
        cl_int status = CL_SUCCESS;
        buffer.memory = clCreateSubBuffer(volume, CL_MEM_READ_WRITE,
          CL_BUFFER_CREATE_TYPE_REGION, &region, &status);
        check_opencl(status, "clCreateSubBuffer(DoG level)");
        buffer.capacity = bytes;
      } else {
        impl_->ensure_buffer(buffer, CL_MEM_READ_WRITE, bytes);
      }
    }
    impl_->dog_plane_bytes[octave] = bytes;
  }
  for (size_t index = 0; index < differences.size(); ++index) {
    auto &level = differences[index];
    const size_t count = static_cast<size_t>(level.width) * level.height;
    if (!device_differences) level.pixels.resize(count);
    cl_mem memory = impl_->ensure_buffer(impl_->dog_levels[index], CL_MEM_READ_WRITE,
                                         count * sizeof(float));
    if (device_differences) (*device_differences)[index] = memory;
  }

  struct ConvolutionProfile {
    std::vector<std::pair<int, cl_event>> events;
    ~ConvolutionProfile() {
      for (const auto &entry : events)
        if (entry.second) clReleaseEvent(entry.second);
    }
  } profile;
  void *mapped_input = nullptr;
  try {
    const auto upload_start = std::chrono::steady_clock::now();
    cl_int map_status = CL_SUCCESS;
    mapped_input = clEnqueueMapBuffer(impl_->queue, input, CL_TRUE,
      CL_MAP_WRITE_INVALIDATE_REGION, 0, image_bytes, 0, nullptr, nullptr, &map_status);
    check_opencl(map_status, "clEnqueueMapBuffer(pyramid input)");
    std::copy(image.begin(), image.end(), static_cast<float *>(mapped_input));
    check_opencl(clEnqueueUnmapMemObject(impl_->queue, input, mapped_input,
      0, nullptr, nullptr), "clEnqueueUnmapMemObject(pyramid input)");
    mapped_input = nullptr;
    const auto upload_end = std::chrono::steady_clock::now();
    const size_t levels_per_octave = static_cast<size_t>(intervals + 3);
    for (size_t index = 0; index < gaussian.size(); ++index) {
      const auto &level = gaussian[index];
      cl_mem destination = impl_->gaussian_levels[index].memory;
      cl_mem source = index == 0 ? input : impl_->gaussian_levels[index - 1].memory;
      const size_t global_size[2] = {static_cast<size_t>(level.width),
                                    static_cast<size_t>(level.height)};
      bool fused_difference = false;
      if (level.octave > 0 && level.scale == 0) {
        const size_t source_index = index - levels_per_octave + intervals;
        const auto &previous = gaussian[source_index];
        source = impl_->gaussian_levels[source_index].memory;
        check_opencl(clSetKernelArg(impl_->downsample, 0, sizeof(source), &source), "pyramid downsample source");
        check_opencl(clSetKernelArg(impl_->downsample, 1, sizeof(destination), &destination), "pyramid downsample destination");
        check_opencl(clSetKernelArg(impl_->downsample, 2, sizeof(int), &previous.width), "pyramid downsample width");
        check_opencl(clSetKernelArg(impl_->downsample, 3, sizeof(int), &previous.height), "pyramid downsample height");
        check_opencl(clSetKernelArg(impl_->downsample, 4, sizeof(int), &level.width), "pyramid downsample output width");
        check_opencl(clSetKernelArg(impl_->downsample, 5, sizeof(int), &level.height), "pyramid downsample output height");
        check_opencl(clEnqueueNDRangeKernel(impl_->queue, impl_->downsample, 2, nullptr,
            global_size, nullptr, 0, nullptr, nullptr), "pyramid downsample launch");
      } else if (kernels[index].empty()) {
        check_opencl(clEnqueueCopyBuffer(impl_->queue, source, destination, 0, 0,
          static_cast<size_t>(level.width) * level.height * sizeof(float),
          0, nullptr, nullptr), "pyramid level copy");
      } else {
        cl_mem weights = impl_->pyramid_weights[index].memory;
        const int radius = static_cast<int>(kernels[index].size() / 2);
        const bool fused_passes = radius <= 12;
        cl_kernel vertical = impl_->vertical;
        if (fused_passes) {
          if (!impl_->fused_gaussian) {
            cl_int status = CL_SUCCESS;
            impl_->fused_gaussian = clCreateKernel(impl_->program, "gaussian_fused", &status);
            check_opencl(status, "clCreateKernel(fused Gaussian passes)");
          }
          vertical = impl_->fused_gaussian;
          const int write_difference = level.scale > 0;
          check_opencl(clSetKernelArg(vertical, 6, sizeof(source), &source), "fused default lower");
          check_opencl(clSetKernelArg(vertical, 7, sizeof(destination), &destination), "fused default difference");
          check_opencl(clSetKernelArg(vertical, 8, sizeof(write_difference), &write_difference), "fused difference flag");
        }
        if (level.scale > 0) {
          if (!fused_passes) vertical = impl_->fused_vertical_kernel();
          cl_mem lower = impl_->gaussian_levels[index - 1].memory;
          const size_t dog_index = static_cast<size_t>(level.octave) * (intervals + 2) + level.scale - 1;
          cl_mem difference = impl_->dog_levels[dog_index].memory;
          check_opencl(clSetKernelArg(vertical, 6, sizeof(lower), &lower), "fused DoG lower");
          check_opencl(clSetKernelArg(vertical, 7, sizeof(difference), &difference), "fused DoG output");
          fused_difference = true;
        }
        for (int pass = 0; pass < (fused_passes ? 1 : 2); ++pass) {
          cl_kernel kernel = fused_passes ? vertical : (pass == 0 ? impl_->horizontal : vertical);
          cl_mem pass_source = pass == 0 ? source : temporary;
          cl_mem pass_destination = fused_passes ? destination : (pass == 0 ? temporary : destination);
          check_opencl(clSetKernelArg(kernel, 0, sizeof(cl_mem), &pass_source), "pyramid blur source");
          check_opencl(clSetKernelArg(kernel, 1, sizeof(cl_mem), &pass_destination), "pyramid blur destination");
          check_opencl(clSetKernelArg(kernel, 2, sizeof(weights), &weights), "pyramid blur weights");
          check_opencl(clSetKernelArg(kernel, 3, sizeof(int), &level.width), "pyramid blur width");
          check_opencl(clSetKernelArg(kernel, 4, sizeof(int), &level.height), "pyramid blur height");
          check_opencl(clSetKernelArg(kernel, 5, sizeof(radius), &radius), "pyramid blur radius");
          cl_event *event = nullptr;
          if (impl_->profiling) {
            profile.events.emplace_back(fused_passes ? 2 : pass, nullptr);
            event = &profile.events.back().second;
          }
          const size_t local_size[2] = {16, 16};
          const size_t fused_size[2] = {(global_size[0] + 15) / 16 * 16,
                                        (global_size[1] + 15) / 16 * 16};
          check_opencl(clEnqueueNDRangeKernel(impl_->queue, kernel, 2, nullptr,
              fused_passes ? fused_size : global_size, fused_passes ? local_size : nullptr,
              0, nullptr, event), "pyramid blur launch");
        }
      }
      if (level.scale > 0 && !fused_difference) {
        cl_mem lower = impl_->gaussian_levels[index - 1].memory;
        const size_t dog_index = static_cast<size_t>(level.octave) * (intervals + 2) + level.scale - 1;
        cl_mem difference = impl_->dog_levels[dog_index].memory;
        check_opencl(clSetKernelArg(impl_->dog, 0, sizeof(destination), &destination), "pyramid DoG upper");
        check_opencl(clSetKernelArg(impl_->dog, 1, sizeof(lower), &lower), "pyramid DoG lower");
        check_opencl(clSetKernelArg(impl_->dog, 2, sizeof(difference), &difference), "pyramid DoG destination");
        check_opencl(clSetKernelArg(impl_->dog, 3, sizeof(int), &level.width), "pyramid DoG width");
        check_opencl(clSetKernelArg(impl_->dog, 4, sizeof(int), &level.height), "pyramid DoG height");
        check_opencl(clEnqueueNDRangeKernel(impl_->queue, impl_->dog, 2, nullptr,
            global_size, nullptr, 0, nullptr, nullptr), "pyramid DoG launch");
      }
    }
    for (size_t index = 0; index < gaussian.size(); ++index) {
      if (device_gaussian) break;
      auto &pixels = gaussian[index].pixels;
      check_opencl(clEnqueueReadBuffer(impl_->queue, impl_->gaussian_levels[index].memory,
          CL_FALSE, 0, pixels.size() * sizeof(float), pixels.data(), 0, nullptr, nullptr),
          "clEnqueueReadBuffer(pyramid Gaussian)");
    }
    for (size_t index = 0; index < differences.size(); ++index) {
      if (device_differences) break;
      auto &pixels = differences[index].pixels;
      check_opencl(clEnqueueReadBuffer(impl_->queue, impl_->dog_levels[index].memory,
          CL_FALSE, 0, pixels.size() * sizeof(float), pixels.data(), 0, nullptr, nullptr),
          "clEnqueueReadBuffer(pyramid DoG)");
    }
    const auto submit_end = std::chrono::steady_clock::now();
    if (wait_for_completion || !device_gaussian || !device_differences || impl_->profiling)
      check_opencl(clFinish(impl_->queue), "clFinish(pyramid)");
    const auto finish_end = std::chrono::steady_clock::now();
    if (impl_->profiling) {
      double horizontal_ms = 0.0, vertical_ms = 0.0, fused_ms = 0.0;
      for (const auto &entry : profile.events) {
        cl_ulong start = 0, end = 0;
        check_opencl(clGetEventProfilingInfo(entry.second, CL_PROFILING_COMMAND_START,
          sizeof(start), &start, nullptr), "profile convolution start");
        check_opencl(clGetEventProfilingInfo(entry.second, CL_PROFILING_COMMAND_END,
          sizeof(end), &end, nullptr), "profile convolution end");
        (entry.first == 2 ? fused_ms : (entry.first == 0 ? horizontal_ms : vertical_ms)) +=
          static_cast<double>(end - start) * 1.0e-6;
      }
      std::fprintf(stderr, "OPENCL_PYRAMID_PROFILE convolutions=%zu horizontal_device_ms=%.3f vertical_device_ms=%.3f fused_device_ms=%.3f input_upload_ms=%.3f submit_ms=%.3f finish_ms=%.3f\n",
        profile.events.size(), horizontal_ms, vertical_ms, fused_ms,
        std::chrono::duration<double, std::milli>(upload_end - upload_start).count(),
        std::chrono::duration<double, std::milli>(submit_end - upload_end).count(),
        std::chrono::duration<double, std::milli>(finish_end - submit_end).count());
    }
  } catch (...) {
    if (mapped_input)
      clEnqueueUnmapMemObject(impl_->queue, input, mapped_input, 0, nullptr, nullptr);
    clFinish(impl_->queue);
    throw;
  }
}

} // namespace sift_extractor::detail
