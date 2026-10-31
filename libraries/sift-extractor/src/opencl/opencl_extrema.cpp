#define CL_TARGET_OPENCL_VERSION 120

#include "opencl_extrema.hpp"

#include <CL/cl.h>
#include <CL/cl_ext.h>

#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

namespace sift_extractor::detail {
namespace {

constexpr const char *kernel_source = R"CLC(
__kernel void find_dog_extrema(__global const float *dog,
                               __global uchar *candidate_mask,
                               const int width, const int height,
                               const int scale_count,
                               const float threshold) {
  const int x = (int)get_global_id(0) + 1;
  const int y = (int)get_global_id(1) + 1;
  const int scale = (int)get_global_id(2) + 1;
  const int inner_width = width - 2;
  const int inner_height = height - 2;
  const int scale_count_inner = scale_count - 2;
  const int mask_index =
      ((scale - 1) * inner_height + (y - 1)) * inner_width + (x - 1);
  const int plane_size = width * height;
  const int center_index = scale * plane_size + y * width + x;
  const float value = dog[center_index];

  if (fabs(value) < threshold) {
    candidate_mask[mask_index] = (uchar)0;
    return;
  }

  const int is_max = value > 0.0f;
  for (int scale_offset = -1; scale_offset <= 1; ++scale_offset) {
    const int neighbor_scale = scale + scale_offset;
    const int scale_base = neighbor_scale * plane_size;
    for (int y_offset = -1; y_offset <= 1; ++y_offset) {
      const int row_base = scale_base + (y + y_offset) * width;
      for (int x_offset = -1; x_offset <= 1; ++x_offset) {
        if (scale_offset == 0 && y_offset == 0 && x_offset == 0)
          continue;
        const float neighbor = dog[row_base + x + x_offset];
        if ((is_max && value <= neighbor) || (!is_max && value >= neighbor)) {
          candidate_mask[mask_index] = (uchar)0;
          return;
        }
      }
    }
  }
  candidate_mask[mask_index] = (uchar)1;
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

} // namespace

struct OpenCLDoGExtrema::Impl {
  cl_context context = nullptr;
  cl_command_queue queue = nullptr;
  cl_program program = nullptr;
  cl_kernel kernel = nullptr;

  Impl() {
    cl_int status = CL_SUCCESS;
    const cl_device_id device = select_intel_gpu();
    context = clCreateContext(nullptr, 1, &device, nullptr, nullptr, &status);
    check_opencl(status, "clCreateContext");
    queue = clCreateCommandQueue(context, device, 0, &status);
    if (status != CL_SUCCESS) {
      clReleaseContext(context);
      context = nullptr;
      check_opencl(status, "clCreateCommandQueue");
    }

    const char *source_pointer = kernel_source;
    const size_t source_length = std::char_traits<char>::length(kernel_source);
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
      throw std::runtime_error(std::string("OpenCL extrema kernel build failed: ") +
                               log.data());
    }

    kernel = clCreateKernel(program, "find_dog_extrema", &status);
    if (status != CL_SUCCESS) {
      clReleaseProgram(program);
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      program = nullptr;
      queue = nullptr;
      context = nullptr;
      check_opencl(status, "clCreateKernel(find_dog_extrema)");
    }
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

OpenCLDoGExtrema::OpenCLDoGExtrema() : impl_(new Impl()) {}
OpenCLDoGExtrema::~OpenCLDoGExtrema() { delete impl_; }

std::vector<ExtremaCandidate> OpenCLDoGExtrema::detect(
    const std::vector<DoGLevel> &dog_levels, float contrast_threshold) {
  if (!std::isfinite(contrast_threshold) || contrast_threshold < 0.0f)
    throw std::invalid_argument("Contrast threshold must be finite and nonnegative");
  if (dog_levels.size() < 3)
    return {};
  const int width = dog_levels.front().width;
  const int height = dog_levels.front().height;
  if (width < 3 || height < 3)
    return {};

  const int scale_count = static_cast<int>(dog_levels.size());
  const int octave = dog_levels.front().octave;
  std::vector<float> dog_data;
  dog_data.reserve(static_cast<size_t>(scale_count) * width * height);
  for (int scale = 0; scale < scale_count; ++scale) {
    const DoGLevel &level = dog_levels[static_cast<size_t>(scale)];
    if (level.octave != octave || level.scale != scale || level.width != width ||
        level.height != height ||
        level.pixels.size() != static_cast<size_t>(width) * height)
      throw std::invalid_argument("DoG levels must form one contiguous octave");
    dog_data.insert(dog_data.end(), level.pixels.begin(), level.pixels.end());
  }

  const size_t work_item_count = static_cast<size_t>(scale_count - 2) *
                                 (height - 2) * (width - 2);
  const size_t input_bytes = dog_data.size() * sizeof(float);
  cl_int status = CL_SUCCESS;
  cl_mem input = clCreateBuffer(impl_->context,
                                CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR,
                                input_bytes, dog_data.data(), &status);
  check_opencl(status, "clCreateBuffer(DoG volume)");
  cl_mem mask = clCreateBuffer(impl_->context, CL_MEM_WRITE_ONLY,
                               work_item_count * sizeof(cl_uchar), nullptr,
                               &status);
  if (status != CL_SUCCESS) {
    clReleaseMemObject(input);
    check_opencl(status, "clCreateBuffer(candidate mask)");
  }

  try {
    const int args[] = {width, height, scale_count};
    check_opencl(clSetKernelArg(impl_->kernel, 0, sizeof(input), &input),
                 "clSetKernelArg(DoG volume)");
    check_opencl(clSetKernelArg(impl_->kernel, 1, sizeof(mask), &mask),
                 "clSetKernelArg(candidate mask)");
    for (cl_uint i = 0; i < 3; ++i)
      check_opencl(clSetKernelArg(impl_->kernel, 2 + i, sizeof(args[i]),
                                  &args[i]),
                   "clSetKernelArg(extrema dimensions)");
    check_opencl(clSetKernelArg(impl_->kernel, 5, sizeof(contrast_threshold),
                                &contrast_threshold),
                 "clSetKernelArg(contrast threshold)");

    const size_t global_size[3] = {static_cast<size_t>(width - 2),
                                   static_cast<size_t>(height - 2),
                                   static_cast<size_t>(scale_count - 2)};
    check_opencl(clEnqueueNDRangeKernel(impl_->queue, impl_->kernel, 3, nullptr,
                                        global_size, nullptr, 0, nullptr, nullptr),
                 "clEnqueueNDRangeKernel(extrema)");

    std::vector<cl_uchar> candidate_mask(work_item_count);
    check_opencl(clEnqueueReadBuffer(impl_->queue, mask, CL_TRUE, 0,
                                     candidate_mask.size() * sizeof(cl_uchar),
                                     candidate_mask.data(), 0, nullptr, nullptr),
                 "clEnqueueReadBuffer(candidate mask)");

    std::vector<ExtremaCandidate> candidates;
    for (size_t i = 0; i < candidate_mask.size(); ++i) {
      if (candidate_mask[i] == 0)
        continue;
      size_t index = i;
      const int x = static_cast<int>(index % static_cast<size_t>(width - 2)) + 1;
      index /= static_cast<size_t>(width - 2);
      const int y = static_cast<int>(index % static_cast<size_t>(height - 2)) + 1;
      const int scale = static_cast<int>(index / static_cast<size_t>(height - 2)) + 1;
      const float response = dog_levels[static_cast<size_t>(scale)]
                                 .pixels[static_cast<size_t>(y) * width + x];
      candidates.push_back({x, y, scale, response});
    }

    clReleaseMemObject(mask);
    clReleaseMemObject(input);
    return candidates;
  } catch (...) {
    clReleaseMemObject(mask);
    clReleaseMemObject(input);
    throw;
  }
}

} // namespace sift_extractor::detail
