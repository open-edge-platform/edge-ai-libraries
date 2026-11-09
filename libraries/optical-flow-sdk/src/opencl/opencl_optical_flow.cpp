// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#define CL_TARGET_OPENCL_VERSION 300

#include "optical_flow_sdk/opencl_optical_flow.hpp"

#include "dis_kernels.hpp"

#include <CL/cl.h>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

namespace optical_flow_sdk {
namespace {

void check_cl(cl_int status, const char *op) {
  if (status != CL_SUCCESS)
    throw std::runtime_error(std::string(op) + " failed with OpenCL status " +
                             std::to_string(status));
}

cl_device_id pick_gpu_device() {
  cl_uint platform_count = 0;
  check_cl(clGetPlatformIDs(0, nullptr, &platform_count), "clGetPlatformIDs(count)");
  if (platform_count == 0)
    throw std::runtime_error("No OpenCL platforms available");
  std::vector<cl_platform_id> platforms(platform_count);
  check_cl(clGetPlatformIDs(platform_count, platforms.data(), nullptr), "clGetPlatformIDs(list)");
  for (cl_platform_id platform : platforms) {
    cl_uint device_count = 0;
    const cl_int st = clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, 0, nullptr, &device_count);
    if (st == CL_DEVICE_NOT_FOUND || device_count == 0)
      continue;
    check_cl(st, "clGetDeviceIDs(count)");
    std::vector<cl_device_id> devices(device_count);
    check_cl(clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, device_count, devices.data(), nullptr),
             "clGetDeviceIDs(list)");
    return devices.front();
  }
  throw std::runtime_error("No OpenCL GPU device available for optical-flow");
}

struct OpenCLContext {
  cl_device_id device = nullptr;
  cl_context context = nullptr;
  cl_command_queue queue = nullptr;
  cl_program program = nullptr;
  cl_kernel k_u8_to_float = nullptr;
  cl_kernel k_u8_downsample2_to_float = nullptr;
  cl_kernel k_u8_downsample4_to_float = nullptr;
  cl_kernel k_downsample2 = nullptr;
  cl_kernel k_upsample_flow = nullptr;
  cl_kernel k_upsample_flow_x4 = nullptr;
  cl_kernel k_upsample_flow_scaled = nullptr;
  cl_kernel k_estimate_and_scatter = nullptr;
  cl_kernel k_estimate_centers = nullptr;
  cl_kernel k_densify_from_patches = nullptr;
  cl_kernel k_normalize_flow = nullptr;
  cl_kernel k_zero_float = nullptr;
  cl_kernel k_zero_flow = nullptr;

  OpenCLContext() {
    device = pick_gpu_device();
    cl_int status = CL_SUCCESS;
    context = clCreateContext(nullptr, 1, &device, nullptr, nullptr, &status);
    check_cl(status, "clCreateContext");
#if defined(CL_VERSION_2_0)
    queue = clCreateCommandQueueWithProperties(context, device, nullptr, &status);
#else
    queue = clCreateCommandQueue(context, device, 0, &status);
#endif
    check_cl(status, "clCreateCommandQueue");

    const char *src = kOpenCLDisKernelSource;
    const std::size_t len = std::char_traits<char>::length(src);
    program = clCreateProgramWithSource(context, 1, &src, &len, &status);
    check_cl(status, "clCreateProgramWithSource");
    status = clBuildProgram(program, 1, &device, "-cl-std=CL1.2 -cl-fast-relaxed-math", nullptr,
                            nullptr);
    if (status != CL_SUCCESS) {
      std::size_t log_size = 0;
      clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, 0, nullptr, &log_size);
      std::string log(log_size, '\0');
      clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, log_size, log.data(), nullptr);
      throw std::runtime_error("clBuildProgram failed:\n" + log);
    }

    auto make_kernel = [&](const char *name) {
      cl_kernel k = clCreateKernel(program, name, &status);
      check_cl(status, name);
      return k;
    };
    k_u8_to_float = make_kernel("u8_to_float");
    k_u8_downsample2_to_float = make_kernel("u8_downsample2_to_float");
    k_u8_downsample4_to_float = make_kernel("u8_downsample4_to_float");
    k_downsample2 = make_kernel("downsample2");
    k_upsample_flow = make_kernel("upsample_flow");
    k_upsample_flow_x4 = make_kernel("upsample_flow_x4");
    k_upsample_flow_scaled = make_kernel("upsample_flow_scaled");
    k_estimate_and_scatter = make_kernel("estimate_and_scatter");
    k_estimate_centers = make_kernel("estimate_centers");
    k_densify_from_patches = make_kernel("densify_from_patches");
    k_normalize_flow = make_kernel("normalize_flow");
    k_zero_float = make_kernel("zero_float");
    k_zero_flow = make_kernel("zero_flow");
  }

  ~OpenCLContext() {
    auto release_k = [](cl_kernel &k) {
      if (k) {
        clReleaseKernel(k);
        k = nullptr;
      }
    };
    release_k(k_u8_to_float);
    release_k(k_u8_downsample2_to_float);
    release_k(k_u8_downsample4_to_float);
    release_k(k_downsample2);
    release_k(k_upsample_flow);
    release_k(k_upsample_flow_x4);
    release_k(k_upsample_flow_scaled);
    release_k(k_estimate_and_scatter);
    release_k(k_estimate_centers);
    release_k(k_densify_from_patches);
    release_k(k_normalize_flow);
    release_k(k_zero_float);
    release_k(k_zero_flow);
    if (program)
      clReleaseProgram(program);
    if (queue)
      clReleaseCommandQueue(queue);
    if (context)
      clReleaseContext(context);
  }
};

OpenCLContext &shared_context() {
  static std::once_flag once;
  static OpenCLContext *ctx = nullptr;
  std::call_once(once, [] { ctx = new OpenCLContext(); });
  return *ctx;
}

void enqueue_1d(cl_command_queue queue, cl_kernel kernel, int n) {
  const std::size_t g = static_cast<std::size_t>(std::max(n, 1));
  check_cl(clEnqueueNDRangeKernel(queue, kernel, 1, nullptr, &g, nullptr, 0, nullptr, nullptr),
           "clEnqueueNDRangeKernel(1d)");
}

void enqueue_2d(cl_command_queue queue, cl_kernel kernel, int width, int height) {
  const std::size_t global[2] = {static_cast<std::size_t>(std::max(width, 1)),
                                 static_cast<std::size_t>(std::max(height, 1))};
  check_cl(clEnqueueNDRangeKernel(queue, kernel, 2, nullptr, global, nullptr, 0, nullptr, nullptr),
           "clEnqueueNDRangeKernel(2d)");
}

cl_mem create_buffer(cl_context context, cl_mem_flags flags, std::size_t bytes) {
  cl_int status = CL_SUCCESS;
  cl_mem buf = clCreateBuffer(context, flags, bytes, nullptr, &status);
  check_cl(status, "clCreateBuffer");
  return buf;
}

void release_mem(cl_mem &m) {
  if (m) {
    clReleaseMemObject(m);
    m = nullptr;
  }
}

struct Workspace {
  int width = 0;
  int height = 0;
  int scales = 0;
  cl_mem prev_u8 = nullptr;
  cl_mem next_u8 = nullptr;
  std::vector<cl_mem> pyr0;
  std::vector<cl_mem> pyr1;
  std::vector<cl_mem> flow;
  std::vector<cl_mem> cost;
  std::vector<cl_mem> acc_u;
  std::vector<cl_mem> acc_v;
  std::vector<cl_mem> acc_c;
  std::vector<cl_mem> acc_w;
  cl_mem patch_u = nullptr;
  cl_mem patch_v = nullptr;
  cl_mem patch_c = nullptr;
  int patch_capacity = 0;
  std::vector<int> widths;
  std::vector<int> heights;

  ~Workspace() { clear(); }

  void clear() {
    release_mem(prev_u8);
    release_mem(next_u8);
    for (auto &m : pyr0)
      release_mem(m);
    for (auto &m : pyr1)
      release_mem(m);
    for (auto &m : flow)
      release_mem(m);
    for (auto &m : cost)
      release_mem(m);
    for (auto &m : acc_u)
      release_mem(m);
    for (auto &m : acc_v)
      release_mem(m);
    for (auto &m : acc_c)
      release_mem(m);
    for (auto &m : acc_w)
      release_mem(m);
    release_mem(patch_u);
    release_mem(patch_v);
    release_mem(patch_c);
    pyr0.clear();
    pyr1.clear();
    flow.clear();
    cost.clear();
    acc_u.clear();
    acc_v.clear();
    acc_c.clear();
    acc_w.clear();
    widths.clear();
    heights.clear();
    width = height = scales = patch_capacity = 0;
  }

  void ensure_patches(OpenCLContext &ctx, int n_patches) {
    if (n_patches <= patch_capacity && patch_u)
      return;
    release_mem(patch_u);
    release_mem(patch_v);
    release_mem(patch_c);
    patch_capacity = std::max(n_patches, 1);
    const std::size_t bytes = static_cast<std::size_t>(patch_capacity) * sizeof(float);
    patch_u = create_buffer(ctx.context, CL_MEM_READ_WRITE, bytes);
    patch_v = create_buffer(ctx.context, CL_MEM_READ_WRITE, bytes);
    patch_c = create_buffer(ctx.context, CL_MEM_READ_WRITE, bytes);
  }

  void ensure(OpenCLContext &ctx, int w, int h, int n_scales) {
    if (width == w && height == h && scales == n_scales)
      return;
    clear();
    width = w;
    height = h;
    scales = n_scales;
    widths.resize(scales);
    heights.resize(scales);
    widths[0] = w;
    heights[0] = h;
    for (int s = 1; s < scales; ++s) {
      widths[s] = std::max(1, widths[s - 1] / 2);
      heights[s] = std::max(1, heights[s - 1] / 2);
    }
    const std::size_t pix0 = static_cast<std::size_t>(w) * h;
    prev_u8 = create_buffer(ctx.context, CL_MEM_READ_ONLY, pix0);
    next_u8 = create_buffer(ctx.context, CL_MEM_READ_ONLY, pix0);
    pyr0.assign(scales, nullptr);
    pyr1.assign(scales, nullptr);
    flow.assign(scales, nullptr);
    cost.assign(scales, nullptr);
    acc_u.assign(scales, nullptr);
    acc_v.assign(scales, nullptr);
    acc_c.assign(scales, nullptr);
    acc_w.assign(scales, nullptr);
    for (int s = 0; s < scales; ++s) {
      const std::size_t pix = static_cast<std::size_t>(widths[s]) * heights[s];
      pyr0[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix * sizeof(float));
      pyr1[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix * sizeof(float));
      flow[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix * 2u * sizeof(float));
      cost[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix);
      acc_u[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix * sizeof(float));
      acc_v[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix * sizeof(float));
      acc_c[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix * sizeof(float));
      acc_w[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix * sizeof(float));
    }
  }
};

} // namespace

struct OpenCLOpticalFlow::Impl {
  Preset preset = Preset::Fast;
  int patch_size = 8;
  int patch_stride = 4;
  int coarsest_scale = 2;
  int finest_scale = 0;
  int gradient_descent_iters = 10;
  mutable std::mutex mutex;
  mutable Workspace workspace;
};

OpenCLOpticalFlow::OpenCLOpticalFlow(Preset preset) : impl_(std::make_unique<Impl>()) {
  impl_->preset = preset;
  switch (preset) {
  case Preset::Fast:
    // Quarter-res single-scale + atomic-free densify (OpenCL primary speed path).
    impl_->patch_size = 8;
    impl_->patch_stride = 8;
    impl_->coarsest_scale = 2;
    impl_->finest_scale = 2;
    impl_->gradient_descent_iters = 2;
    break;
  case Preset::Medium:
    impl_->patch_size = 8;
    impl_->patch_stride = 3;
    impl_->coarsest_scale = 3;
    impl_->finest_scale = 0;
    impl_->gradient_descent_iters = 12;
    break;
  case Preset::Slow:
    impl_->patch_size = 12;
    impl_->patch_stride = 3;
    impl_->coarsest_scale = 3;
    impl_->finest_scale = 0;
    impl_->gradient_descent_iters = 16;
    break;
  }
  (void)shared_context();
}

OpenCLOpticalFlow::~OpenCLOpticalFlow() = default;
OpenCLOpticalFlow::OpenCLOpticalFlow(OpenCLOpticalFlow &&) noexcept = default;
OpenCLOpticalFlow &OpenCLOpticalFlow::operator=(OpenCLOpticalFlow &&) noexcept = default;

Preset OpenCLOpticalFlow::preset() const { return impl_->preset; }

OpenCLU8Image::OpenCLU8Image(void *handle, int width, int height, bool owns)
    : handle_(handle), width_(width), height_(height), owns_(owns) {}

OpenCLU8Image::~OpenCLU8Image() {
  if (owns_ && handle_)
    clReleaseMemObject(static_cast<cl_mem>(handle_));
}

OpenCLU8Image::OpenCLU8Image(OpenCLU8Image &&other) noexcept
    : handle_(other.handle_), width_(other.width_), height_(other.height_), owns_(other.owns_) {
  other.handle_ = nullptr;
  other.width_ = other.height_ = 0;
  other.owns_ = false;
}

OpenCLU8Image &OpenCLU8Image::operator=(OpenCLU8Image &&other) noexcept {
  if (this != &other) {
    if (owns_ && handle_)
      clReleaseMemObject(static_cast<cl_mem>(handle_));
    handle_ = other.handle_;
    width_ = other.width_;
    height_ = other.height_;
    owns_ = other.owns_;
    other.handle_ = nullptr;
    other.width_ = other.height_ = 0;
    other.owns_ = false;
  }
  return *this;
}

OpenCLFlowBuffer::OpenCLFlowBuffer(void *handle, int width, int height, bool owns)
    : handle_(handle), width_(width), height_(height), owns_(owns) {}

OpenCLFlowBuffer::~OpenCLFlowBuffer() {
  if (owns_ && handle_)
    clReleaseMemObject(static_cast<cl_mem>(handle_));
}

OpenCLFlowBuffer::OpenCLFlowBuffer(OpenCLFlowBuffer &&other) noexcept
    : handle_(other.handle_), width_(other.width_), height_(other.height_), owns_(other.owns_) {
  other.handle_ = nullptr;
  other.width_ = other.height_ = 0;
  other.owns_ = false;
}

OpenCLFlowBuffer &OpenCLFlowBuffer::operator=(OpenCLFlowBuffer &&other) noexcept {
  if (this != &other) {
    if (owns_ && handle_)
      clReleaseMemObject(static_cast<cl_mem>(handle_));
    handle_ = other.handle_;
    width_ = other.width_;
    height_ = other.height_;
    owns_ = other.owns_;
    other.handle_ = nullptr;
    other.width_ = other.height_ = 0;
    other.owns_ = false;
  }
  return *this;
}

OpenCLU8Image OpenCLOpticalFlow::create_u8_image(int width, int height) const {
  if (width <= 0 || height <= 0)
    throw std::invalid_argument("OpenCLU8Image size must be positive");
  OpenCLContext &ctx = shared_context();
  const std::size_t bytes = static_cast<std::size_t>(width) * height;
  cl_mem mem = create_buffer(ctx.context, CL_MEM_READ_WRITE, bytes);
  return OpenCLU8Image(mem, width, height, true);
}

OpenCLFlowBuffer OpenCLOpticalFlow::create_flow_buffer(int width, int height) const {
  if (width <= 0 || height <= 0)
    throw std::invalid_argument("OpenCLFlowBuffer size must be positive");
  OpenCLContext &ctx = shared_context();
  const std::size_t bytes = static_cast<std::size_t>(width) * height * 2u * sizeof(float);
  cl_mem mem = create_buffer(ctx.context, CL_MEM_READ_WRITE, bytes);
  return OpenCLFlowBuffer(mem, width, height, true);
}

void OpenCLOpticalFlow::upload_u8(OpenCLU8Image &dst, const ImageView &src) const {
  src.validate();
  if (dst.empty() || dst.width() != src.width || dst.height() != src.height)
    throw std::invalid_argument("upload_u8 size mismatch");
  OpenCLContext &ctx = shared_context();
  const std::size_t nbytes = dst.bytes();
  cl_mem mem = static_cast<cl_mem>(dst.handle());
  if (src.row_stride() == static_cast<std::size_t>(src.width)) {
    check_cl(clEnqueueWriteBuffer(ctx.queue, mem, CL_FALSE, 0, nbytes, src.data, 0, nullptr, nullptr),
             "upload_u8");
  } else {
    std::vector<std::uint8_t> pack(nbytes);
    for (int y = 0; y < src.height; ++y)
      std::memcpy(pack.data() + static_cast<std::size_t>(y) * src.width, src.row(y),
                  static_cast<std::size_t>(src.width));
    check_cl(clEnqueueWriteBuffer(ctx.queue, mem, CL_FALSE, 0, nbytes, pack.data(), 0, nullptr,
                                  nullptr),
             "upload_u8 packed");
  }
}

void OpenCLOpticalFlow::download_flow(const OpenCLFlowBuffer &src, FlowField &dst) const {
  if (src.empty())
    throw std::invalid_argument("download_flow empty buffer");
  dst.allocate(src.width(), src.height());
  OpenCLContext &ctx = shared_context();
  check_cl(clEnqueueReadBuffer(ctx.queue, static_cast<cl_mem>(src.handle()), CL_TRUE, 0, src.bytes(),
                               dst.data.data(), 0, nullptr, nullptr),
           "download_flow");
}

void OpenCLOpticalFlow::finish() const {
  check_cl(clFinish(shared_context().queue), "clFinish");
}

void OpenCLOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow) const {
  CostMap unused;
  calc_impl(prev, next, flow, unused, /*want_cost=*/false);
}

void OpenCLOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow,
                             CostMap &cost) const {
  calc_impl(prev, next, flow, cost, /*want_cost=*/true);
}

namespace {

void run_opencl_dis(OpenCLContext &ctx, Workspace &ws, int patch_size, int patch_stride,
                    int coarsest_scale, int finest_scale, int gd_iters, Preset preset,
                    cl_mem prev_u8, cl_mem next_u8, cl_mem flow_out, int width, int height) {
  const int scales = coarsest_scale + 1;
  ws.ensure(ctx, width, height, scales);

  auto set_u8 = [&](cl_mem src, cl_mem dst, int w, int h) {
    check_cl(clSetKernelArg(ctx.k_u8_to_float, 0, sizeof(cl_mem), &src), "u8 src");
    check_cl(clSetKernelArg(ctx.k_u8_to_float, 1, sizeof(cl_mem), &dst), "u8 dst");
    check_cl(clSetKernelArg(ctx.k_u8_to_float, 2, sizeof(int), &w), "u8 w");
    check_cl(clSetKernelArg(ctx.k_u8_to_float, 3, sizeof(int), &h), "u8 h");
    check_cl(clSetKernelArg(ctx.k_u8_to_float, 4, sizeof(int), &w), "u8 stride");
    enqueue_2d(ctx.queue, ctx.k_u8_to_float, w, h);
  };
  auto u8_to_half = [&](cl_mem src, cl_mem dst, int sw, int sh, int dw, int dh) {
    check_cl(clSetKernelArg(ctx.k_u8_downsample2_to_float, 0, sizeof(cl_mem), &src), "u8h src");
    check_cl(clSetKernelArg(ctx.k_u8_downsample2_to_float, 1, sizeof(cl_mem), &dst), "u8h dst");
    check_cl(clSetKernelArg(ctx.k_u8_downsample2_to_float, 2, sizeof(int), &sw), "u8h sw");
    check_cl(clSetKernelArg(ctx.k_u8_downsample2_to_float, 3, sizeof(int), &sh), "u8h sh");
    check_cl(clSetKernelArg(ctx.k_u8_downsample2_to_float, 4, sizeof(int), &dw), "u8h dw");
    check_cl(clSetKernelArg(ctx.k_u8_downsample2_to_float, 5, sizeof(int), &dh), "u8h dh");
    check_cl(clSetKernelArg(ctx.k_u8_downsample2_to_float, 6, sizeof(int), &sw), "u8h stride");
    enqueue_2d(ctx.queue, ctx.k_u8_downsample2_to_float, dw, dh);
  };
  auto u8_to_quarter = [&](cl_mem src, cl_mem dst, int sw, int sh, int dw, int dh) {
    check_cl(clSetKernelArg(ctx.k_u8_downsample4_to_float, 0, sizeof(cl_mem), &src), "u8q src");
    check_cl(clSetKernelArg(ctx.k_u8_downsample4_to_float, 1, sizeof(cl_mem), &dst), "u8q dst");
    check_cl(clSetKernelArg(ctx.k_u8_downsample4_to_float, 2, sizeof(int), &sw), "u8q sw");
    check_cl(clSetKernelArg(ctx.k_u8_downsample4_to_float, 3, sizeof(int), &sh), "u8q sh");
    check_cl(clSetKernelArg(ctx.k_u8_downsample4_to_float, 4, sizeof(int), &dw), "u8q dw");
    check_cl(clSetKernelArg(ctx.k_u8_downsample4_to_float, 5, sizeof(int), &dh), "u8q dh");
    check_cl(clSetKernelArg(ctx.k_u8_downsample4_to_float, 6, sizeof(int), &sw), "u8q stride");
    enqueue_2d(ctx.queue, ctx.k_u8_downsample4_to_float, dw, dh);
  };
  auto down_f = [&](cl_mem src, cl_mem dst, int sw, int sh, int dw, int dh) {
    check_cl(clSetKernelArg(ctx.k_downsample2, 0, sizeof(cl_mem), &src), "down src");
    check_cl(clSetKernelArg(ctx.k_downsample2, 1, sizeof(cl_mem), &dst), "down dst");
    check_cl(clSetKernelArg(ctx.k_downsample2, 2, sizeof(int), &sw), "down sw");
    check_cl(clSetKernelArg(ctx.k_downsample2, 3, sizeof(int), &sh), "down sh");
    check_cl(clSetKernelArg(ctx.k_downsample2, 4, sizeof(int), &dw), "down dw");
    check_cl(clSetKernelArg(ctx.k_downsample2, 5, sizeof(int), &dh), "down dh");
    enqueue_2d(ctx.queue, ctx.k_downsample2, dw, dh);
  };

  const bool fast_atomic_free = preset == Preset::Fast && patch_size == 8 && finest_scale > 0;

  if (finest_scale == 0) {
    set_u8(prev_u8, ws.pyr0[0], ws.widths[0], ws.heights[0]);
    set_u8(next_u8, ws.pyr1[0], ws.widths[0], ws.heights[0]);
    for (int s = 1; s < scales; ++s) {
      down_f(ws.pyr0[s - 1], ws.pyr0[s], ws.widths[s - 1], ws.heights[s - 1], ws.widths[s],
             ws.heights[s]);
      down_f(ws.pyr1[s - 1], ws.pyr1[s], ws.widths[s - 1], ws.heights[s - 1], ws.widths[s],
             ws.heights[s]);
    }
  } else if (finest_scale == 2 && coarsest_scale == 2) {
    u8_to_quarter(prev_u8, ws.pyr0[2], ws.widths[0], ws.heights[0], ws.widths[2], ws.heights[2]);
    u8_to_quarter(next_u8, ws.pyr1[2], ws.widths[0], ws.heights[0], ws.widths[2], ws.heights[2]);
  } else if (finest_scale == 3 && coarsest_scale == 3) {
    u8_to_quarter(prev_u8, ws.pyr0[2], ws.widths[0], ws.heights[0], ws.widths[2], ws.heights[2]);
    u8_to_quarter(next_u8, ws.pyr1[2], ws.widths[0], ws.heights[0], ws.widths[2], ws.heights[2]);
    down_f(ws.pyr0[2], ws.pyr0[3], ws.widths[2], ws.heights[2], ws.widths[3], ws.heights[3]);
    down_f(ws.pyr1[2], ws.pyr1[3], ws.widths[2], ws.heights[2], ws.widths[3], ws.heights[3]);
  } else {
    u8_to_half(prev_u8, ws.pyr0[1], ws.widths[0], ws.heights[0], ws.widths[1], ws.heights[1]);
    u8_to_half(next_u8, ws.pyr1[1], ws.widths[0], ws.heights[0], ws.widths[1], ws.heights[1]);
    for (int s = 2; s < scales; ++s) {
      down_f(ws.pyr0[s - 1], ws.pyr0[s], ws.widths[s - 1], ws.heights[s - 1], ws.widths[s],
             ws.heights[s]);
      down_f(ws.pyr1[s - 1], ws.pyr1[s], ws.widths[s - 1], ws.heights[s - 1], ws.widths[s],
             ws.heights[s]);
    }
  }

  {
    const int n = ws.widths[coarsest_scale] * ws.heights[coarsest_scale] * 2;
    check_cl(clSetKernelArg(ctx.k_zero_flow, 0, sizeof(cl_mem), &ws.flow[coarsest_scale]),
             "zero flow");
    check_cl(clSetKernelArg(ctx.k_zero_flow, 1, sizeof(int), &n), "zero n");
    enqueue_1d(ctx.queue, ctx.k_zero_flow, n);
  }

  for (int scale = coarsest_scale; scale >= finest_scale; --scale) {
    if (scale != coarsest_scale) {
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 0, sizeof(cl_mem), &ws.flow[scale + 1]),
               "up coarse");
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 1, sizeof(cl_mem), &ws.flow[scale]), "up fine");
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 2, sizeof(int), &ws.widths[scale + 1]), "up cw");
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 3, sizeof(int), &ws.heights[scale + 1]), "up ch");
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 4, sizeof(int), &ws.widths[scale]), "up fw");
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 5, sizeof(int), &ws.heights[scale]), "up fh");
      enqueue_2d(ctx.queue, ctx.k_upsample_flow, ws.widths[scale], ws.heights[scale]);
    }

    const int w = ws.widths[scale];
    const int h = ws.heights[scale];
    const int half = patch_size / 2;
    if (w <= 2 * half || h <= 2 * half)
      continue;
    const int n_gx = (w - 2 * half + patch_stride - 1) / patch_stride;
    const int n_gy = (h - 2 * half + patch_stride - 1) / patch_stride;
    if (n_gx <= 0 || n_gy <= 0)
      continue;

    int arg = 0;
    auto setm = [&](cl_kernel k, cl_mem m) {
      check_cl(clSetKernelArg(k, arg++, sizeof(cl_mem), &m), "set mem");
    };
    auto seti = [&](cl_kernel k, int v) {
      check_cl(clSetKernelArg(k, arg++, sizeof(int), &v), "set int");
    };

    if (fast_atomic_free) {
      ws.ensure_patches(ctx, n_gx * n_gy);
      arg = 0;
      setm(ctx.k_estimate_centers, ws.pyr0[scale]);
      setm(ctx.k_estimate_centers, ws.pyr1[scale]);
      setm(ctx.k_estimate_centers, ws.flow[scale]);
      setm(ctx.k_estimate_centers, ws.patch_u);
      setm(ctx.k_estimate_centers, ws.patch_v);
      setm(ctx.k_estimate_centers, ws.patch_c);
      seti(ctx.k_estimate_centers, w);
      seti(ctx.k_estimate_centers, h);
      seti(ctx.k_estimate_centers, patch_size);
      seti(ctx.k_estimate_centers, patch_stride);
      seti(ctx.k_estimate_centers, gd_iters);
      seti(ctx.k_estimate_centers, n_gx);
      enqueue_2d(ctx.queue, ctx.k_estimate_centers, n_gx, n_gy);

      arg = 0;
      setm(ctx.k_densify_from_patches, ws.patch_u);
      setm(ctx.k_densify_from_patches, ws.patch_v);
      setm(ctx.k_densify_from_patches, ws.patch_c);
      setm(ctx.k_densify_from_patches, ws.flow[scale]);
      setm(ctx.k_densify_from_patches, ws.cost[scale]);
      seti(ctx.k_densify_from_patches, w);
      seti(ctx.k_densify_from_patches, h);
      seti(ctx.k_densify_from_patches, patch_size);
      seti(ctx.k_densify_from_patches, patch_stride);
      seti(ctx.k_densify_from_patches, n_gx);
      seti(ctx.k_densify_from_patches, n_gy);
      enqueue_2d(ctx.queue, ctx.k_densify_from_patches, w, h);
      continue;
    }

    const int pix = w * h;
    auto zero_acc = [&](cl_mem buf) {
      check_cl(clSetKernelArg(ctx.k_zero_float, 0, sizeof(cl_mem), &buf), "zero acc");
      check_cl(clSetKernelArg(ctx.k_zero_float, 1, sizeof(int), &pix), "zero n");
      enqueue_1d(ctx.queue, ctx.k_zero_float, pix);
    };
    zero_acc(ws.acc_u[scale]);
    zero_acc(ws.acc_v[scale]);
    zero_acc(ws.acc_c[scale]);
    zero_acc(ws.acc_w[scale]);

    arg = 0;
    setm(ctx.k_estimate_and_scatter, ws.pyr0[scale]);
    setm(ctx.k_estimate_and_scatter, ws.pyr1[scale]);
    setm(ctx.k_estimate_and_scatter, ws.flow[scale]);
    setm(ctx.k_estimate_and_scatter, ws.acc_u[scale]);
    setm(ctx.k_estimate_and_scatter, ws.acc_v[scale]);
    setm(ctx.k_estimate_and_scatter, ws.acc_c[scale]);
    setm(ctx.k_estimate_and_scatter, ws.acc_w[scale]);
    seti(ctx.k_estimate_and_scatter, w);
    seti(ctx.k_estimate_and_scatter, h);
    seti(ctx.k_estimate_and_scatter, patch_size);
    seti(ctx.k_estimate_and_scatter, patch_stride);
    seti(ctx.k_estimate_and_scatter, gd_iters);
    seti(ctx.k_estimate_and_scatter, n_gx);
    enqueue_2d(ctx.queue, ctx.k_estimate_and_scatter, n_gx, n_gy);

    arg = 0;
    setm(ctx.k_normalize_flow, ws.acc_u[scale]);
    setm(ctx.k_normalize_flow, ws.acc_v[scale]);
    setm(ctx.k_normalize_flow, ws.acc_c[scale]);
    setm(ctx.k_normalize_flow, ws.acc_w[scale]);
    setm(ctx.k_normalize_flow, ws.flow[scale]);
    setm(ctx.k_normalize_flow, ws.cost[scale]);
    seti(ctx.k_normalize_flow, pix);
    enqueue_1d(ctx.queue, ctx.k_normalize_flow, pix);
  }

  if (finest_scale >= 2) {
    const float scale_mul = static_cast<float>(1 << finest_scale);
    check_cl(clSetKernelArg(ctx.k_upsample_flow_scaled, 0, sizeof(cl_mem), &ws.flow[finest_scale]),
             "final scaled coarse");
    check_cl(clSetKernelArg(ctx.k_upsample_flow_scaled, 1, sizeof(cl_mem), &flow_out),
             "final scaled fine");
    check_cl(clSetKernelArg(ctx.k_upsample_flow_scaled, 2, sizeof(int), &ws.widths[finest_scale]),
             "final scaled cw");
    check_cl(clSetKernelArg(ctx.k_upsample_flow_scaled, 3, sizeof(int), &ws.heights[finest_scale]),
             "final scaled ch");
    check_cl(clSetKernelArg(ctx.k_upsample_flow_scaled, 4, sizeof(int), &ws.widths[0]),
             "final scaled fw");
    check_cl(clSetKernelArg(ctx.k_upsample_flow_scaled, 5, sizeof(int), &ws.heights[0]),
             "final scaled fh");
    check_cl(clSetKernelArg(ctx.k_upsample_flow_scaled, 6, sizeof(float), &scale_mul),
             "final scaled mul");
    enqueue_2d(ctx.queue, ctx.k_upsample_flow_scaled, ws.widths[0], ws.heights[0]);
  } else {
    for (int scale = finest_scale - 1; scale >= 0; --scale) {
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 0, sizeof(cl_mem), &ws.flow[scale + 1]),
               "final up coarse");
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 1, sizeof(cl_mem), &ws.flow[scale]),
               "final up fine");
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 2, sizeof(int), &ws.widths[scale + 1]),
               "final up cw");
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 3, sizeof(int), &ws.heights[scale + 1]),
               "final up ch");
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 4, sizeof(int), &ws.widths[scale]),
               "final up fw");
      check_cl(clSetKernelArg(ctx.k_upsample_flow, 5, sizeof(int), &ws.heights[scale]),
               "final up fh");
      enqueue_2d(ctx.queue, ctx.k_upsample_flow, ws.widths[scale], ws.heights[scale]);
    }
    if (flow_out != ws.flow[0]) {
      const std::size_t bytes =
          static_cast<std::size_t>(ws.widths[0]) * ws.heights[0] * 2u * sizeof(float);
      check_cl(clEnqueueCopyBuffer(ctx.queue, ws.flow[0], flow_out, 0, 0, bytes, 0, nullptr, nullptr),
               "copy flow_out");
    }
  }
}

} // namespace

void OpenCLOpticalFlow::calc_device(const OpenCLU8Image &prev, const OpenCLU8Image &next,
                                   OpenCLFlowBuffer &flow) const {
  if (prev.empty() || next.empty() || flow.empty())
    throw std::invalid_argument("calc_device requires non-empty device buffers");
  if (prev.width() != next.width() || prev.height() != next.height() ||
      prev.width() != flow.width() || prev.height() != flow.height())
    throw std::invalid_argument("calc_device buffer sizes must match");

  std::lock_guard<std::mutex> lock(impl_->mutex);
  OpenCLContext &ctx = shared_context();
  run_opencl_dis(ctx, impl_->workspace, impl_->patch_size, impl_->patch_stride,
                 impl_->coarsest_scale, impl_->finest_scale, impl_->gradient_descent_iters,
                 impl_->preset, static_cast<cl_mem>(prev.handle()),
                 static_cast<cl_mem>(next.handle()), static_cast<cl_mem>(flow.handle()),
                 prev.width(), prev.height());
  check_cl(clFinish(ctx.queue), "clFinish calc_device");
}

void OpenCLOpticalFlow::calc_impl(const ImageView &prev, const ImageView &next, FlowField &flow,
                                  CostMap &cost, bool want_cost) const {
  prev.validate();
  next.validate();
  if (prev.width != next.width || prev.height != next.height)
    throw std::invalid_argument("prev/next must share dimensions");

  std::lock_guard<std::mutex> lock(impl_->mutex);
  OpenCLContext &ctx = shared_context();
  Workspace &ws = impl_->workspace;

  flow.allocate(prev.width, prev.height);
  if (want_cost)
    cost.allocate(prev.width, prev.height);

  const int scales = impl_->coarsest_scale + 1;
  ws.ensure(ctx, prev.width, prev.height, scales);

  const std::size_t nbytes = static_cast<std::size_t>(prev.width) * prev.height;
  const bool tight_prev = prev.row_stride() == static_cast<std::size_t>(prev.width);
  const bool tight_next = next.row_stride() == static_cast<std::size_t>(next.width);
  std::vector<std::uint8_t> prev_pack;
  std::vector<std::uint8_t> next_pack;
  if (tight_prev) {
    check_cl(clEnqueueWriteBuffer(ctx.queue, ws.prev_u8, CL_FALSE, 0, nbytes, prev.data, 0, nullptr,
                                  nullptr),
             "write prev");
  } else {
    prev_pack.resize(nbytes);
    for (int y = 0; y < prev.height; ++y)
      std::memcpy(prev_pack.data() + static_cast<std::size_t>(y) * prev.width, prev.row(y),
                  static_cast<std::size_t>(prev.width));
    check_cl(clEnqueueWriteBuffer(ctx.queue, ws.prev_u8, CL_FALSE, 0, nbytes, prev_pack.data(), 0,
                                  nullptr, nullptr),
             "write prev packed");
  }
  if (tight_next) {
    check_cl(clEnqueueWriteBuffer(ctx.queue, ws.next_u8, CL_FALSE, 0, nbytes, next.data, 0, nullptr,
                                  nullptr),
             "write next");
  } else {
    next_pack.resize(nbytes);
    for (int y = 0; y < next.height; ++y)
      std::memcpy(next_pack.data() + static_cast<std::size_t>(y) * next.width, next.row(y),
                  static_cast<std::size_t>(next.width));
    check_cl(clEnqueueWriteBuffer(ctx.queue, ws.next_u8, CL_FALSE, 0, nbytes, next_pack.data(), 0,
                                  nullptr, nullptr),
             "write next packed");
  }

  run_opencl_dis(ctx, ws, impl_->patch_size, impl_->patch_stride, impl_->coarsest_scale,
                 impl_->finest_scale, impl_->gradient_descent_iters, impl_->preset, ws.prev_u8,
                 ws.next_u8, ws.flow[0], prev.width, prev.height);

  check_cl(clEnqueueReadBuffer(ctx.queue, ws.flow[0], CL_FALSE, 0, flow.data.size() * sizeof(float),
                               flow.data.data(), 0, nullptr, nullptr),
           "read flow");
  if (want_cost) {
    if (impl_->finest_scale == 0) {
      check_cl(clEnqueueReadBuffer(ctx.queue, ws.cost[0], CL_FALSE, 0, cost.data.size(),
                                   cost.data.data(), 0, nullptr, nullptr),
               "read cost");
    } else {
      std::fill(cost.data.begin(), cost.data.end(), static_cast<std::uint8_t>(128));
    }
  }
  check_cl(clFinish(ctx.queue), "clFinish");
}

} // namespace optical_flow_sdk
