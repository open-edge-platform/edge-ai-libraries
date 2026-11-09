// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#define CL_TARGET_OPENCL_VERSION 300

#include "optical_flow_sdk/opencl_farneback.hpp"

#if OPTICALFLOW_HAS_OPENCL

#include "farneback_kernels.hpp"

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

cl_device_id pick_gpu() {
  cl_uint nplat = 0;
  check_cl(clGetPlatformIDs(0, nullptr, &nplat), "clGetPlatformIDs");
  std::vector<cl_platform_id> plats(nplat);
  check_cl(clGetPlatformIDs(nplat, plats.data(), nullptr), "clGetPlatformIDs list");
  for (auto p : plats) {
    cl_uint ndev = 0;
    if (clGetDeviceIDs(p, CL_DEVICE_TYPE_GPU, 0, nullptr, &ndev) != CL_SUCCESS || ndev == 0)
      continue;
    std::vector<cl_device_id> devs(ndev);
    check_cl(clGetDeviceIDs(p, CL_DEVICE_TYPE_GPU, ndev, devs.data(), nullptr), "clGetDeviceIDs");
    return devs.front();
  }
  throw std::runtime_error("No OpenCL GPU for Farneback");
}

struct FbContext {
  cl_device_id device = nullptr;
  cl_context context = nullptr;
  cl_command_queue queue = nullptr;
  cl_program program = nullptr;
  cl_kernel k_u8 = nullptr;
  cl_kernel k_down = nullptr;
  cl_kernel k_up = nullptr;
  cl_kernel k_zero = nullptr;
  cl_kernel k_lk = nullptr;

  FbContext() {
    device = pick_gpu();
    cl_int st = CL_SUCCESS;
    context = clCreateContext(nullptr, 1, &device, nullptr, nullptr, &st);
    check_cl(st, "clCreateContext");
#if defined(CL_VERSION_2_0)
    queue = clCreateCommandQueueWithProperties(context, device, nullptr, &st);
#else
    queue = clCreateCommandQueue(context, device, 0, &st);
#endif
    check_cl(st, "clCreateCommandQueue");
    const char *src = kOpenCLFarnebackKernelSource;
    const std::size_t len = std::char_traits<char>::length(src);
    program = clCreateProgramWithSource(context, 1, &src, &len, &st);
    check_cl(st, "clCreateProgramWithSource");
    st = clBuildProgram(program, 1, &device, "-cl-std=CL1.2 -cl-fast-relaxed-math", nullptr,
                        nullptr);
    if (st != CL_SUCCESS) {
      std::size_t log_size = 0;
      clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, 0, nullptr, &log_size);
      std::string log(log_size, '\0');
      clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, log_size, log.data(), nullptr);
      throw std::runtime_error("Farneback clBuildProgram failed:\n" + log);
    }
    auto mk = [&](const char *n) {
      cl_kernel k = clCreateKernel(program, n, &st);
      check_cl(st, n);
      return k;
    };
    k_u8 = mk("fb_u8_to_float");
    k_down = mk("fb_downsample2");
    k_up = mk("fb_upsample_flow");
    k_zero = mk("fb_zero_flow");
    k_lk = mk("fb_poly_lk");
  }

  ~FbContext() {
    auto rk = [](cl_kernel &k) {
      if (k) {
        clReleaseKernel(k);
        k = nullptr;
      }
    };
    rk(k_u8);
    rk(k_down);
    rk(k_up);
    rk(k_zero);
    rk(k_lk);
    if (program)
      clReleaseProgram(program);
    if (queue)
      clReleaseCommandQueue(queue);
    if (context)
      clReleaseContext(context);
  }
};

FbContext &fb_ctx() {
  static FbContext ctx;
  return ctx;
}

void enqueue_2d(cl_command_queue q, cl_kernel k, int w, int h) {
  const std::size_t g[2] = {static_cast<std::size_t>(std::max(w, 1)),
                            static_cast<std::size_t>(std::max(h, 1))};
  check_cl(clEnqueueNDRangeKernel(q, k, 2, nullptr, g, nullptr, 0, nullptr, nullptr), "enqueue2d");
}

void enqueue_1d(cl_command_queue q, cl_kernel k, int n) {
  const std::size_t g = static_cast<std::size_t>(std::max(n, 1));
  check_cl(clEnqueueNDRangeKernel(q, k, 1, nullptr, &g, nullptr, 0, nullptr, nullptr), "enqueue1d");
}

cl_mem buf(cl_context c, cl_mem_flags f, std::size_t bytes) {
  cl_int st = CL_SUCCESS;
  cl_mem m = clCreateBuffer(c, f, bytes, nullptr, &st);
  check_cl(st, "clCreateBuffer");
  return m;
}

} // namespace

struct OpenCLFarnebackOpticalFlow::Impl {
  Preset preset = Preset::Fast;
  int levels = 2;
  int winsize = 9;
  int iterations = 2;
  int poly_n = 5;
  float poly_sigma = 1.1f;
  mutable std::mutex mutex;
};

OpenCLFarnebackOpticalFlow::OpenCLFarnebackOpticalFlow(Preset preset)
    : impl_(std::make_unique<Impl>()) {
  impl_->preset = preset;
  switch (preset) {
  case Preset::Fast:
    impl_->levels = 2;
    impl_->winsize = 9;
    impl_->iterations = 2;
    impl_->poly_n = 5;
    impl_->poly_sigma = 1.1f;
    break;
  case Preset::Medium:
    impl_->levels = 3;
    impl_->winsize = 13;
    impl_->iterations = 3;
    impl_->poly_n = 5;
    impl_->poly_sigma = 1.2f;
    break;
  case Preset::Slow:
    impl_->levels = 4;
    impl_->winsize = 15;
    impl_->iterations = 5;
    impl_->poly_n = 7;
    impl_->poly_sigma = 1.5f;
    break;
  }
  (void)fb_ctx();
}

OpenCLFarnebackOpticalFlow::~OpenCLFarnebackOpticalFlow() = default;
OpenCLFarnebackOpticalFlow::OpenCLFarnebackOpticalFlow(OpenCLFarnebackOpticalFlow &&) noexcept =
    default;
OpenCLFarnebackOpticalFlow &
OpenCLFarnebackOpticalFlow::operator=(OpenCLFarnebackOpticalFlow &&) noexcept = default;

Preset OpenCLFarnebackOpticalFlow::preset() const { return impl_->preset; }

void OpenCLFarnebackOpticalFlow::calc(const ImageView &prev, const ImageView &next,
                                      FlowField &flow) const {
  CostMap unused;
  calc(prev, next, flow, unused);
}

void OpenCLFarnebackOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow,
                                      CostMap &cost) const {
  prev.validate();
  next.validate();
  if (prev.width != next.width || prev.height != next.height)
    throw std::invalid_argument("Farneback OpenCL prev/next size mismatch");

  std::lock_guard<std::mutex> lock(impl_->mutex);
  FbContext &ctx = fb_ctx();
  const int W = prev.width;
  const int H = prev.height;
  const int levels = impl_->levels;
  const int half = impl_->winsize / 2;
  const int poly_n = impl_->poly_n;
  const float poly_sigma = impl_->poly_sigma;

  std::vector<int> widths(levels), heights(levels);
  widths[0] = W;
  heights[0] = H;
  for (int s = 1; s < levels; ++s) {
    widths[s] = std::max(1, widths[s - 1] / 2);
    heights[s] = std::max(1, heights[s - 1] / 2);
  }

  auto release = [](cl_mem &m) {
    if (m) {
      clReleaseMemObject(m);
      m = nullptr;
    }
  };

  cl_mem prev_u8 = buf(ctx.context, CL_MEM_READ_ONLY, static_cast<std::size_t>(W) * H);
  cl_mem next_u8 = buf(ctx.context, CL_MEM_READ_ONLY, static_cast<std::size_t>(W) * H);
  auto upload = [&](cl_mem dst, const ImageView &img, const char *tag) {
    if (img.row_stride() == static_cast<std::size_t>(W)) {
      check_cl(clEnqueueWriteBuffer(ctx.queue, dst, CL_TRUE, 0, static_cast<std::size_t>(W) * H,
                                    img.data, 0, nullptr, nullptr),
               tag);
      return;
    }
    std::vector<std::uint8_t> pack(static_cast<std::size_t>(W) * H);
    for (int y = 0; y < H; ++y)
      std::memcpy(pack.data() + static_cast<std::size_t>(y) * W, img.row(y),
                  static_cast<std::size_t>(W));
    check_cl(clEnqueueWriteBuffer(ctx.queue, dst, CL_TRUE, 0, pack.size(), pack.data(), 0, nullptr,
                                  nullptr),
             tag);
  };
  upload(prev_u8, prev, "upload prev");
  upload(next_u8, next, "upload next");

  std::vector<cl_mem> pyr0(levels, nullptr), pyr1(levels, nullptr);
  std::vector<cl_mem> flow_a(levels, nullptr), flow_b(levels, nullptr), cost_l(levels, nullptr);
  for (int s = 0; s < levels; ++s) {
    const std::size_t pix = static_cast<std::size_t>(widths[s]) * heights[s];
    pyr0[s] = buf(ctx.context, CL_MEM_READ_WRITE, pix * sizeof(float));
    pyr1[s] = buf(ctx.context, CL_MEM_READ_WRITE, pix * sizeof(float));
    flow_a[s] = buf(ctx.context, CL_MEM_READ_WRITE, pix * 2 * sizeof(float));
    flow_b[s] = buf(ctx.context, CL_MEM_READ_WRITE, pix * 2 * sizeof(float));
    cost_l[s] = buf(ctx.context, CL_MEM_READ_WRITE, pix);
  }

  auto set_u8 = [&](cl_mem src, cl_mem dst, int w, int h) {
    check_cl(clSetKernelArg(ctx.k_u8, 0, sizeof(cl_mem), &src), "u8 src");
    check_cl(clSetKernelArg(ctx.k_u8, 1, sizeof(cl_mem), &dst), "u8 dst");
    check_cl(clSetKernelArg(ctx.k_u8, 2, sizeof(int), &w), "u8 w");
    check_cl(clSetKernelArg(ctx.k_u8, 3, sizeof(int), &h), "u8 h");
    check_cl(clSetKernelArg(ctx.k_u8, 4, sizeof(int), &w), "u8 stride");
    enqueue_2d(ctx.queue, ctx.k_u8, w, h);
  };
  set_u8(prev_u8, pyr0[0], W, H);
  set_u8(next_u8, pyr1[0], W, H);
  for (int s = 1; s < levels; ++s) {
    check_cl(clSetKernelArg(ctx.k_down, 0, sizeof(cl_mem), &pyr0[s - 1]), "down0");
    check_cl(clSetKernelArg(ctx.k_down, 1, sizeof(cl_mem), &pyr0[s]), "down0d");
    check_cl(clSetKernelArg(ctx.k_down, 2, sizeof(int), &widths[s - 1]), "sw");
    check_cl(clSetKernelArg(ctx.k_down, 3, sizeof(int), &heights[s - 1]), "sh");
    check_cl(clSetKernelArg(ctx.k_down, 4, sizeof(int), &widths[s]), "dw");
    check_cl(clSetKernelArg(ctx.k_down, 5, sizeof(int), &heights[s]), "dh");
    enqueue_2d(ctx.queue, ctx.k_down, widths[s], heights[s]);
    check_cl(clSetKernelArg(ctx.k_down, 0, sizeof(cl_mem), &pyr1[s - 1]), "down1");
    check_cl(clSetKernelArg(ctx.k_down, 1, sizeof(cl_mem), &pyr1[s]), "down1d");
    enqueue_2d(ctx.queue, ctx.k_down, widths[s], heights[s]);
  }

  const int coarse = levels - 1;
  int nflow = widths[coarse] * heights[coarse] * 2;
  check_cl(clSetKernelArg(ctx.k_zero, 0, sizeof(cl_mem), &flow_a[coarse]), "zero");
  check_cl(clSetKernelArg(ctx.k_zero, 1, sizeof(int), &nflow), "zeron");
  enqueue_1d(ctx.queue, ctx.k_zero, nflow);

  const int max_step_x100 = 150;
  for (int s = coarse; s >= 0; --s) {
    if (s != coarse) {
      check_cl(clSetKernelArg(ctx.k_up, 0, sizeof(cl_mem), &flow_a[s + 1]), "up in");
      check_cl(clSetKernelArg(ctx.k_up, 1, sizeof(cl_mem), &flow_a[s]), "up out");
      check_cl(clSetKernelArg(ctx.k_up, 2, sizeof(int), &widths[s + 1]), "cw");
      check_cl(clSetKernelArg(ctx.k_up, 3, sizeof(int), &heights[s + 1]), "ch");
      check_cl(clSetKernelArg(ctx.k_up, 4, sizeof(int), &widths[s]), "fw");
      check_cl(clSetKernelArg(ctx.k_up, 5, sizeof(int), &heights[s]), "fh");
      enqueue_2d(ctx.queue, ctx.k_up, widths[s], heights[s]);
    }
    cl_mem in = flow_a[s];
    cl_mem out = flow_b[s];
    for (int it = 0; it < impl_->iterations; ++it) {
      check_cl(clSetKernelArg(ctx.k_lk, 0, sizeof(cl_mem), &pyr0[s]), "lk I0");
      check_cl(clSetKernelArg(ctx.k_lk, 1, sizeof(cl_mem), &pyr1[s]), "lk I1");
      check_cl(clSetKernelArg(ctx.k_lk, 2, sizeof(cl_mem), &in), "lk fin");
      check_cl(clSetKernelArg(ctx.k_lk, 3, sizeof(cl_mem), &out), "lk fout");
      check_cl(clSetKernelArg(ctx.k_lk, 4, sizeof(cl_mem), &cost_l[s]), "lk cost");
      check_cl(clSetKernelArg(ctx.k_lk, 5, sizeof(int), &widths[s]), "lk w");
      check_cl(clSetKernelArg(ctx.k_lk, 6, sizeof(int), &heights[s]), "lk h");
      check_cl(clSetKernelArg(ctx.k_lk, 7, sizeof(int), &half), "lk half");
      check_cl(clSetKernelArg(ctx.k_lk, 8, sizeof(int), &poly_n), "lk poly_n");
      check_cl(clSetKernelArg(ctx.k_lk, 9, sizeof(float), &poly_sigma), "lk poly_sigma");
      check_cl(clSetKernelArg(ctx.k_lk, 10, sizeof(int), &max_step_x100), "lk step");
      enqueue_2d(ctx.queue, ctx.k_lk, widths[s], heights[s]);
      std::swap(in, out);
    }
    if (in != flow_a[s]) {
      // last write is in `in`; copy label by swap back into flow_a
      std::swap(flow_a[s], flow_b[s]);
    }
  }

  flow.allocate(W, H);
  cost.allocate(W, H);
  check_cl(clEnqueueReadBuffer(ctx.queue, flow_a[0], CL_TRUE, 0,
                               static_cast<std::size_t>(W) * H * 2 * sizeof(float), flow.data.data(),
                               0, nullptr, nullptr),
           "download flow");
  check_cl(clEnqueueReadBuffer(ctx.queue, cost_l[0], CL_TRUE, 0, static_cast<std::size_t>(W) * H,
                               cost.data.data(), 0, nullptr, nullptr),
           "download cost");

  release(prev_u8);
  release(next_u8);
  for (int s = 0; s < levels; ++s) {
    release(pyr0[s]);
    release(pyr1[s]);
    release(flow_a[s]);
    release(flow_b[s]);
    release(cost_l[s]);
  }
}

} // namespace optical_flow_sdk

#endif // OPTICALFLOW_HAS_OPENCL
