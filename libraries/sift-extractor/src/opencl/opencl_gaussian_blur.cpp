#define CL_TARGET_OPENCL_VERSION 120

#include "opencl_gaussian_blur.hpp"

#include <CL/cl.h>
#include <CL/cl_ext.h>

#include <algorithm>
#include <cmath>
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
  cl_program program = nullptr;
  cl_kernel horizontal = nullptr;
  cl_kernel vertical = nullptr;
  cl_kernel dog = nullptr;
  cl_kernel downsample = nullptr;
  Buffer input;
  Buffer second_input;
  Buffer temporary;
  Buffer output;
  Buffer weights;

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

  Impl() {
    cl_int status = CL_SUCCESS;
    device = select_intel_gpu();
    context = clCreateContext(nullptr, 1, &device, nullptr, nullptr, &status);
    check_opencl(status, "clCreateContext");

    queue = clCreateCommandQueue(context, device, 0, &status);
    if (status != CL_SUCCESS) {
      clReleaseContext(context);
      context = nullptr;
      check_opencl(status, "clCreateCommandQueue");
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
    if (downsample)
      clReleaseKernel(downsample);
    if (dog)
      clReleaseKernel(dog);
    if (vertical)
      clReleaseKernel(vertical);
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

} // namespace sift_extractor::detail
