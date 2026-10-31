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

typedef struct {
  int x;
  int y;
  int scale;
  float response;
} ExtremaCandidateData;

__kernel void refine_dog_extrema(__global const float *dog,
                                 __global const ExtremaCandidateData *candidates,
                                 __global float *refined,
                                 const int width, const int height,
                                 const int scale_count,
                                 const int candidate_count,
                                 const float contrast_threshold,
                                 const float edge_limit) {
  const int index = (int)get_global_id(0);
  if (index >= candidate_count)
    return;

  const ExtremaCandidateData candidate = candidates[index];
  const int x = candidate.x;
  const int y = candidate.y;
  const int scale = candidate.scale;
  const int output = index * 6;
  const int plane_size = width * height;
  if (x < 1 || x >= width - 1 || y < 1 || y >= height - 1 ||
      scale < 1 || scale >= scale_count - 1) {
    refined[output + 5] = 0.0f;
    return;
  }

  const int center = scale * plane_size + y * width + x;
  const float value = dog[center];
  const float gx = 0.5f * (dog[center + 1] - dog[center - 1]);
  const float gy = 0.5f * (dog[center + width] - dog[center - width]);
  const float gs = 0.5f * (dog[center + plane_size] - dog[center - plane_size]);
  const float dxx = dog[center + 1] + dog[center - 1] - 2.0f * value;
  const float dyy = dog[center + width] + dog[center - width] - 2.0f * value;
  const float dss = dog[center + plane_size] + dog[center - plane_size] - 2.0f * value;
  const float dxy = 0.25f * (dog[center + width + 1] - dog[center + width - 1] -
                             dog[center - width + 1] + dog[center - width - 1]);
  const float dxs = 0.25f * (dog[center + plane_size + 1] -
                             dog[center + plane_size - 1] -
                             dog[center - plane_size + 1] +
                             dog[center - plane_size - 1]);
  const float dys = 0.25f * (dog[center + plane_size + width] -
                             dog[center + plane_size - width] -
                             dog[center - plane_size + width] +
                             dog[center - plane_size - width]);

  const float a11 = dyy * dss - dys * dys;
  const float a12 = dxs * dys - dxy * dss;
  const float a13 = dxy * dys - dyy * dxs;
  const float a22 = dxx * dss - dxs * dxs;
  const float a23 = dxy * dxs - dxx * dys;
  const float a33 = dxx * dyy - dxy * dxy;
  const float determinant = dxx * a11 + dxy * a12 + dxs * a13;
  if (!isfinite(determinant) || fabs(determinant) < 1e-10f) {
    refined[output + 5] = 0.0f;
    return;
  }

  const float offset_x = -(a11 * gx + a12 * gy + a13 * gs) / determinant;
  const float offset_y = -(a12 * gx + a22 * gy + a23 * gs) / determinant;
  const float offset_s = -(a13 * gx + a23 * gy + a33 * gs) / determinant;
  if (!isfinite(offset_x) || !isfinite(offset_y) || !isfinite(offset_s) ||
      fabs(offset_x) > 0.5f || fabs(offset_y) > 0.5f || fabs(offset_s) > 0.5f) {
    refined[output + 5] = 0.0f;
    return;
  }

  const float interpolated_response =
      value + 0.5f * (gx * offset_x + gy * offset_y + gs * offset_s);
  const float spatial_determinant = dxx * dyy - dxy * dxy;
  const float trace = dxx + dyy;
  if (!isfinite(interpolated_response) ||
      fabs(interpolated_response) < contrast_threshold ||
      spatial_determinant <= 0.0f ||
      trace * trace / spatial_determinant >= edge_limit) {
    refined[output + 5] = 0.0f;
    return;
  }

  refined[output + 0] = (float)x + offset_x;
  refined[output + 1] = (float)y + offset_y;
  refined[output + 2] = (float)scale + offset_s;
  refined[output + 3] = interpolated_response;
  refined[output + 4] = trace * trace / spatial_determinant;
  refined[output + 5] = 1.0f;
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
  cl_kernel refine_kernel = nullptr;

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

    refine_kernel = clCreateKernel(program, "refine_dog_extrema", &status);
    if (status != CL_SUCCESS) {
      clReleaseKernel(kernel);
      clReleaseProgram(program);
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      kernel = nullptr;
      program = nullptr;
      queue = nullptr;
      context = nullptr;
      check_opencl(status, "clCreateKernel(refine_dog_extrema)");
    }
  }

  ~Impl() {
    if (refine_kernel)
      clReleaseKernel(refine_kernel);
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

std::vector<RefinedKeypoint> OpenCLDoGExtrema::refine(
    const std::vector<DoGLevel> &dog_levels,
    const std::vector<ExtremaCandidate> &candidates,
    float contrast_threshold, float edge_limit) {
  if (!std::isfinite(contrast_threshold) || contrast_threshold < 0.0f ||
      !std::isfinite(edge_limit) || edge_limit <= 0.0f)
    throw std::invalid_argument("Refinement thresholds must be finite and positive");
  if (candidates.empty() || dog_levels.size() < 3)
    return {};

  const int width = dog_levels.front().width;
  const int height = dog_levels.front().height;
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

  static_assert(sizeof(ExtremaCandidate) == sizeof(int) * 3 + sizeof(float));
  const size_t dog_bytes = dog_data.size() * sizeof(float);
  const size_t candidate_bytes = candidates.size() * sizeof(ExtremaCandidate);
  cl_int status = CL_SUCCESS;
  cl_mem dog_buffer = clCreateBuffer(impl_->context,
                                     CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR,
                                     dog_bytes, dog_data.data(), &status);
  check_opencl(status, "clCreateBuffer(DoG volume for refinement)");
  cl_mem candidate_buffer = clCreateBuffer(
      impl_->context, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, candidate_bytes,
      const_cast<ExtremaCandidate *>(candidates.data()), &status);
  if (status != CL_SUCCESS) {
    clReleaseMemObject(dog_buffer);
    check_opencl(status, "clCreateBuffer(candidates for refinement)");
  }
  const size_t output_count = candidates.size() * 6;
  cl_mem refined_buffer = clCreateBuffer(
      impl_->context, CL_MEM_WRITE_ONLY, output_count * sizeof(float), nullptr,
      &status);
  if (status != CL_SUCCESS) {
    clReleaseMemObject(candidate_buffer);
    clReleaseMemObject(dog_buffer);
    check_opencl(status, "clCreateBuffer(refined candidates)");
  }

  try {
    const int candidate_count = static_cast<int>(candidates.size());
    check_opencl(clSetKernelArg(impl_->refine_kernel, 0, sizeof(dog_buffer),
                                &dog_buffer),
                 "clSetKernelArg(refinement DoG volume)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 1,
                                sizeof(candidate_buffer), &candidate_buffer),
                 "clSetKernelArg(refinement candidates)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 2, sizeof(refined_buffer),
                                &refined_buffer),
                 "clSetKernelArg(refinement output)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 3, sizeof(width), &width),
                 "clSetKernelArg(refinement width)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 4, sizeof(height), &height),
                 "clSetKernelArg(refinement height)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 5, sizeof(scale_count),
                                &scale_count),
                 "clSetKernelArg(refinement scale count)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 6,
                                sizeof(candidate_count), &candidate_count),
                 "clSetKernelArg(refinement candidate count)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 7,
                                sizeof(contrast_threshold),
                                &contrast_threshold),
                 "clSetKernelArg(refinement contrast threshold)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 8, sizeof(edge_limit),
                                &edge_limit),
                 "clSetKernelArg(refinement edge limit)");

    const size_t global_size = candidates.size();
    check_opencl(clEnqueueNDRangeKernel(impl_->queue, impl_->refine_kernel, 1,
                                        nullptr, &global_size, nullptr, 0,
                                        nullptr, nullptr),
                 "clEnqueueNDRangeKernel(refinement)");

    std::vector<float> host_output(output_count);
    check_opencl(clEnqueueReadBuffer(impl_->queue, refined_buffer, CL_TRUE, 0,
                                     output_count * sizeof(float),
                                     host_output.data(), 0, nullptr, nullptr),
                 "clEnqueueReadBuffer(refinement)");

    std::vector<RefinedKeypoint> result;
    for (size_t i = 0; i < candidates.size(); ++i) {
      const float *values = host_output.data() + i * 6;
      if (values[5] != 0.0f)
        result.push_back({values[0], values[1], values[2], values[3], values[4]});
    }

    clReleaseMemObject(refined_buffer);
    clReleaseMemObject(candidate_buffer);
    clReleaseMemObject(dog_buffer);
    return result;
  } catch (...) {
    clReleaseMemObject(refined_buffer);
    clReleaseMemObject(candidate_buffer);
    clReleaseMemObject(dog_buffer);
    throw;
  }
}

} // namespace sift_extractor::detail
