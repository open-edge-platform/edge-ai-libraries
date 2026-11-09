// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#define CL_TARGET_OPENCL_VERSION 300

#include "optical_flow_sdk/opencl_optical_flow.hpp"

#include "dis_kernels.hpp"

#include <CL/cl.h>

#include <algorithm>
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
    const cl_int st =
        clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, 0, nullptr, &device_count);
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
  cl_kernel k_downsample2 = nullptr;
  cl_kernel k_upsample_flow = nullptr;
  cl_kernel k_estimate_patches = nullptr;
  cl_kernel k_densify_flow = nullptr;
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
    k_downsample2 = make_kernel("downsample2");
    k_upsample_flow = make_kernel("upsample_flow");
    k_estimate_patches = make_kernel("estimate_patches");
    k_densify_flow = make_kernel("densify_flow");
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
    release_k(k_downsample2);
    release_k(k_upsample_flow);
    release_k(k_estimate_patches);
    release_k(k_densify_flow);
    release_k(k_zero_flow);
    if (program)
      clReleaseProgram(program);
    if (queue)
      clReleaseCommandQueue(queue);
    if (context)
      clReleaseContext(context);
  }

  OpenCLContext(const OpenCLContext &) = delete;
  OpenCLContext &operator=(const OpenCLContext &) = delete;
};

OpenCLContext &shared_context() {
  static std::once_flag once;
  static OpenCLContext *ctx = nullptr;
  std::call_once(once, [] { ctx = new OpenCLContext(); });
  return *ctx;
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
  std::size_t patch_capacity = 0;
  cl_mem prev_u8 = nullptr;
  cl_mem next_u8 = nullptr;
  std::vector<cl_mem> pyr0;
  std::vector<cl_mem> pyr1;
  std::vector<cl_mem> flow;
  std::vector<cl_mem> cost;
  cl_mem patch_u = nullptr;
  cl_mem patch_v = nullptr;
  cl_mem patch_cost = nullptr;
  cl_mem patch_cx = nullptr;
  cl_mem patch_cy = nullptr;
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
    release_mem(patch_u);
    release_mem(patch_v);
    release_mem(patch_cost);
    release_mem(patch_cx);
    release_mem(patch_cy);
    pyr0.clear();
    pyr1.clear();
    flow.clear();
    cost.clear();
    widths.clear();
    heights.clear();
    width = height = scales = 0;
    patch_capacity = 0;
  }

  void ensure(OpenCLContext &ctx, int w, int h, int n_scales, int patch_size, int patch_stride) {
    const int half = patch_size / 2;
    const int n_gx = std::max(1, (w - 2 * half + patch_stride - 1) / patch_stride);
    const int n_gy = std::max(1, (h - 2 * half + patch_stride - 1) / patch_stride);
    const std::size_t need_patches = static_cast<std::size_t>(n_gx) * n_gy;

    if (width == w && height == h && scales == n_scales && patch_capacity >= need_patches)
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
    pyr0.resize(scales, nullptr);
    pyr1.resize(scales, nullptr);
    flow.resize(scales, nullptr);
    cost.resize(scales, nullptr);
    for (int s = 0; s < scales; ++s) {
      const std::size_t pix = static_cast<std::size_t>(widths[s]) * heights[s];
      pyr0[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix * sizeof(float));
      pyr1[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix * sizeof(float));
      flow[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix * 2u * sizeof(float));
      cost[s] = create_buffer(ctx.context, CL_MEM_READ_WRITE, pix);
    }

    patch_capacity = need_patches;
    patch_u = create_buffer(ctx.context, CL_MEM_READ_WRITE, patch_capacity * sizeof(float));
    patch_v = create_buffer(ctx.context, CL_MEM_READ_WRITE, patch_capacity * sizeof(float));
    patch_cost = create_buffer(ctx.context, CL_MEM_READ_WRITE, patch_capacity * sizeof(float));
    patch_cx = create_buffer(ctx.context, CL_MEM_READ_WRITE, patch_capacity * sizeof(int));
    patch_cy = create_buffer(ctx.context, CL_MEM_READ_WRITE, patch_capacity * sizeof(int));
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
    impl_->patch_size = 8;
    impl_->patch_stride = 4;
    impl_->coarsest_scale = 2;
    impl_->finest_scale = 0;
    impl_->gradient_descent_iters = 10;
    break;
  case Preset::Medium:
    impl_->patch_size = 8;
    impl_->patch_stride = 3;
    impl_->coarsest_scale = 3;
    impl_->finest_scale = 0;
    impl_->gradient_descent_iters = 14;
    break;
  case Preset::Slow:
    impl_->patch_size = 12;
    impl_->patch_stride = 3;
    impl_->coarsest_scale = 3;
    impl_->finest_scale = 0;
    impl_->gradient_descent_iters = 18;
    break;
  }
  (void)shared_context();
}

OpenCLOpticalFlow::~OpenCLOpticalFlow() = default;
OpenCLOpticalFlow::OpenCLOpticalFlow(OpenCLOpticalFlow &&) noexcept = default;
OpenCLOpticalFlow &OpenCLOpticalFlow::operator=(OpenCLOpticalFlow &&) noexcept = default;

Preset OpenCLOpticalFlow::preset() const { return impl_->preset; }

void OpenCLOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow) const {
  CostMap cost;
  calc(prev, next, flow, cost);
}

void OpenCLOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow,
                             CostMap &cost) const {
  prev.validate();
  next.validate();
  if (prev.width != next.width || prev.height != next.height)
    throw std::invalid_argument("prev/next must share dimensions");

  std::lock_guard<std::mutex> lock(impl_->mutex);
  OpenCLContext &ctx = shared_context();
  Workspace &ws = impl_->workspace;

  flow.allocate(prev.width, prev.height);
  cost.allocate(prev.width, prev.height);

  const int scales = impl_->coarsest_scale + 1;
  ws.ensure(ctx, prev.width, prev.height, scales, impl_->patch_size, impl_->patch_stride);

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

  auto set_u8 = [&](cl_mem src, cl_mem dst, int w, int h) {
    check_cl(clSetKernelArg(ctx.k_u8_to_float, 0, sizeof(cl_mem), &src), "u8 src");
    check_cl(clSetKernelArg(ctx.k_u8_to_float, 1, sizeof(cl_mem), &dst), "u8 dst");
    check_cl(clSetKernelArg(ctx.k_u8_to_float, 2, sizeof(int), &w), "u8 w");
    check_cl(clSetKernelArg(ctx.k_u8_to_float, 3, sizeof(int), &h), "u8 h");
    check_cl(clSetKernelArg(ctx.k_u8_to_float, 4, sizeof(int), &w), "u8 stride");
    enqueue_2d(ctx.queue, ctx.k_u8_to_float, w, h);
  };
  set_u8(ws.prev_u8, ws.pyr0[0], ws.widths[0], ws.heights[0]);
  set_u8(ws.next_u8, ws.pyr1[0], ws.widths[0], ws.heights[0]);

  for (int s = 1; s < scales; ++s) {
    auto down = [&](cl_mem src, cl_mem dst, int sw, int sh, int dw, int dh) {
      check_cl(clSetKernelArg(ctx.k_downsample2, 0, sizeof(cl_mem), &src), "down src");
      check_cl(clSetKernelArg(ctx.k_downsample2, 1, sizeof(cl_mem), &dst), "down dst");
      check_cl(clSetKernelArg(ctx.k_downsample2, 2, sizeof(int), &sw), "down sw");
      check_cl(clSetKernelArg(ctx.k_downsample2, 3, sizeof(int), &sh), "down sh");
      check_cl(clSetKernelArg(ctx.k_downsample2, 4, sizeof(int), &dw), "down dw");
      check_cl(clSetKernelArg(ctx.k_downsample2, 5, sizeof(int), &dh), "down dh");
      enqueue_2d(ctx.queue, ctx.k_downsample2, dw, dh);
    };
    down(ws.pyr0[s - 1], ws.pyr0[s], ws.widths[s - 1], ws.heights[s - 1], ws.widths[s],
         ws.heights[s]);
    down(ws.pyr1[s - 1], ws.pyr1[s], ws.widths[s - 1], ws.heights[s - 1], ws.widths[s],
         ws.heights[s]);
  }

  {
    const int n = ws.widths[impl_->coarsest_scale] * ws.heights[impl_->coarsest_scale] * 2;
    check_cl(clSetKernelArg(ctx.k_zero_flow, 0, sizeof(cl_mem), &ws.flow[impl_->coarsest_scale]),
             "zero flow");
    check_cl(clSetKernelArg(ctx.k_zero_flow, 1, sizeof(int), &n), "zero n");
    const std::size_t g = static_cast<std::size_t>(n);
    check_cl(clEnqueueNDRangeKernel(ctx.queue, ctx.k_zero_flow, 1, nullptr, &g, nullptr, 0, nullptr,
                                    nullptr),
             "enqueue zero");
  }

  for (int scale = impl_->coarsest_scale; scale >= impl_->finest_scale; --scale) {
    if (scale != impl_->coarsest_scale) {
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
    const int half = impl_->patch_size / 2;
    if (w <= 2 * half || h <= 2 * half)
      continue;

    const int n_gx = (w - 2 * half + impl_->patch_stride - 1) / impl_->patch_stride;
    const int n_gy = (h - 2 * half + impl_->patch_stride - 1) / impl_->patch_stride;
    if (n_gx <= 0 || n_gy <= 0)
      continue;

    // Invalidate unused lattice slots (estimate_patches overwrites valid ones).
    const int fill = -1;
    // Small host fill is cheap vs full densify; reuse capacity-sized buffer.
    static thread_local std::vector<int> neg;
    const std::size_t n_patches = static_cast<std::size_t>(n_gx) * n_gy;
    if (neg.size() < n_patches)
      neg.assign(n_patches, -1);
    else
      std::fill_n(neg.begin(), n_patches, fill);
    check_cl(clEnqueueWriteBuffer(ctx.queue, ws.patch_cx, CL_FALSE, 0, n_patches * sizeof(int),
                                  neg.data(), 0, nullptr, nullptr),
             "write pcx");
    check_cl(clEnqueueWriteBuffer(ctx.queue, ws.patch_cy, CL_FALSE, 0, n_patches * sizeof(int),
                                  neg.data(), 0, nullptr, nullptr),
             "write pcy");

    int arg = 0;
    auto setm = [&](cl_kernel k, cl_mem m) {
      check_cl(clSetKernelArg(k, arg++, sizeof(cl_mem), &m), "set mem");
    };
    auto seti = [&](cl_kernel k, int v) {
      check_cl(clSetKernelArg(k, arg++, sizeof(int), &v), "set int");
    };

    arg = 0;
    setm(ctx.k_estimate_patches, ws.pyr0[scale]);
    setm(ctx.k_estimate_patches, ws.pyr1[scale]);
    setm(ctx.k_estimate_patches, ws.flow[scale]);
    setm(ctx.k_estimate_patches, ws.patch_u);
    setm(ctx.k_estimate_patches, ws.patch_v);
    setm(ctx.k_estimate_patches, ws.patch_cost);
    setm(ctx.k_estimate_patches, ws.patch_cx);
    setm(ctx.k_estimate_patches, ws.patch_cy);
    seti(ctx.k_estimate_patches, w);
    seti(ctx.k_estimate_patches, h);
    seti(ctx.k_estimate_patches, impl_->patch_size);
    seti(ctx.k_estimate_patches, impl_->patch_stride);
    seti(ctx.k_estimate_patches, impl_->gradient_descent_iters);
    seti(ctx.k_estimate_patches, n_gx);
    enqueue_2d(ctx.queue, ctx.k_estimate_patches, n_gx, n_gy);

    arg = 0;
    setm(ctx.k_densify_flow, ws.patch_u);
    setm(ctx.k_densify_flow, ws.patch_v);
    setm(ctx.k_densify_flow, ws.patch_cost);
    setm(ctx.k_densify_flow, ws.patch_cx);
    setm(ctx.k_densify_flow, ws.patch_cy);
    setm(ctx.k_densify_flow, ws.flow[scale]);
    setm(ctx.k_densify_flow, ws.cost[scale]);
    seti(ctx.k_densify_flow, w);
    seti(ctx.k_densify_flow, h);
    seti(ctx.k_densify_flow, impl_->patch_size);
    seti(ctx.k_densify_flow, impl_->patch_stride);
    seti(ctx.k_densify_flow, n_gx);
    seti(ctx.k_densify_flow, n_gy);
    enqueue_2d(ctx.queue, ctx.k_densify_flow, w, h);
  }

  check_cl(clEnqueueReadBuffer(ctx.queue, ws.flow[0], CL_FALSE, 0, flow.data.size() * sizeof(float),
                               flow.data.data(), 0, nullptr, nullptr),
           "read flow");
  check_cl(clEnqueueReadBuffer(ctx.queue, ws.cost[0], CL_FALSE, 0, cost.data.size(), cost.data.data(),
                               0, nullptr, nullptr),
           "read cost");
  check_cl(clFinish(ctx.queue), "clFinish");
}

} // namespace optical_flow_sdk
