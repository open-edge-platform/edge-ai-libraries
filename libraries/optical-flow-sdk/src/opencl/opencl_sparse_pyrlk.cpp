// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#define CL_TARGET_OPENCL_VERSION 300

#include "optical_flow_sdk/opencl_sparse_pyrlk.hpp"

#if OPTICALFLOW_HAS_OPENCL

#include "pyrlk_kernels.hpp"

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
  throw std::runtime_error("No OpenCL GPU for SparsePyrLK");
}

struct LkContext {
  cl_device_id device = nullptr;
  cl_context context = nullptr;
  cl_command_queue queue = nullptr;
  cl_program program = nullptr;
  cl_kernel k_u8 = nullptr;
  cl_kernel k_down = nullptr;
  cl_kernel k_track = nullptr;
  cl_kernel k_scale = nullptr;

  LkContext() {
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
    const char *src = kOpenCLPyrLKKernelSource;
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
      throw std::runtime_error("PyrLK clBuildProgram failed:\n" + log);
    }
    auto mk = [&](const char *n) {
      cl_kernel k = clCreateKernel(program, n, &st);
      check_cl(st, n);
      return k;
    };
    k_u8 = mk("lk_u8_to_float");
    k_down = mk("lk_downsample2");
    k_track = mk("lk_track_level");
    k_scale = mk("lk_scale_pts");
  }

  ~LkContext() {
    auto rk = [](cl_kernel &k) {
      if (k) {
        clReleaseKernel(k);
        k = nullptr;
      }
    };
    rk(k_u8);
    rk(k_down);
    rk(k_track);
    rk(k_scale);
    if (program)
      clReleaseProgram(program);
    if (queue)
      clReleaseCommandQueue(queue);
    if (context)
      clReleaseContext(context);
  }
};

LkContext &lk_ctx() {
  static LkContext ctx;
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

void release(cl_mem &m) {
  if (m) {
    clReleaseMemObject(m);
    m = nullptr;
  }
}

} // namespace

struct OpenCLSparsePyrLK::Impl {
  SparsePyrLKOptions options;
  mutable std::mutex mutex;
};

OpenCLSparsePyrLK::OpenCLSparsePyrLK() : OpenCLSparsePyrLK(SparsePyrLKOptions{}) {}

OpenCLSparsePyrLK::OpenCLSparsePyrLK(SparsePyrLKOptions options)
    : impl_(std::make_unique<Impl>()) {
  if (options.win_size < 3 || (options.win_size % 2) == 0)
    throw std::invalid_argument("SparsePyrLK win_size must be odd and >= 3");
  if (options.max_level < 0)
    throw std::invalid_argument("SparsePyrLK max_level must be >= 0");
  impl_->options = options;
  (void)lk_ctx();
}

OpenCLSparsePyrLK::~OpenCLSparsePyrLK() = default;
OpenCLSparsePyrLK::OpenCLSparsePyrLK(OpenCLSparsePyrLK &&) noexcept = default;
OpenCLSparsePyrLK &OpenCLSparsePyrLK::operator=(OpenCLSparsePyrLK &&) noexcept = default;

const SparsePyrLKOptions &OpenCLSparsePyrLK::options() const { return impl_->options; }

void OpenCLSparsePyrLK::calc(const ImageView &prev, const ImageView &next,
                             const std::vector<Point2f> &prev_pts, std::vector<Point2f> &next_pts,
                             std::vector<std::uint8_t> &status, std::vector<float> &err) const {
  if (prev.width != next.width || prev.height != next.height)
    throw std::invalid_argument("prev/next must share dimensions");
  const int n = static_cast<int>(prev_pts.size());
  next_pts.resize(prev_pts.size());
  status.assign(prev_pts.size(), 1);
  err.assign(prev_pts.size(), 0.0f);
  if (n == 0)
    return;

  std::lock_guard<std::mutex> lock(impl_->mutex);
  LkContext &ctx = lk_ctx();
  const int W = prev.width;
  const int H = prev.height;
  const int win_half = impl_->options.win_size / 2;

  int max_level = impl_->options.max_level;
  while (max_level > 0) {
    const int cw = std::max(1, W >> max_level);
    const int ch = std::max(1, H >> max_level);
    if (cw > impl_->options.win_size && ch > impl_->options.win_size)
      break;
    --max_level;
  }
  const int levels = max_level + 1;

  std::vector<int> widths(levels), heights(levels);
  widths[0] = W;
  heights[0] = H;
  for (int l = 1; l < levels; ++l) {
    widths[l] = std::max(1, widths[l - 1] / 2);
    heights[l] = std::max(1, heights[l - 1] / 2);
  }

  cl_mem prev_u8 = buf(ctx.context, CL_MEM_READ_ONLY, static_cast<std::size_t>(W) * H);
  cl_mem next_u8 = buf(ctx.context, CL_MEM_READ_ONLY, static_cast<std::size_t>(W) * H);
  auto upload = [&](cl_mem dst, const ImageView &img) {
    if (img.row_stride() == static_cast<std::size_t>(W)) {
      check_cl(clEnqueueWriteBuffer(ctx.queue, dst, CL_TRUE, 0, static_cast<std::size_t>(W) * H,
                                    img.data, 0, nullptr, nullptr),
               "upload");
      return;
    }
    std::vector<std::uint8_t> pack(static_cast<std::size_t>(W) * H);
    for (int y = 0; y < H; ++y)
      std::memcpy(pack.data() + static_cast<std::size_t>(y) * W, img.row(y),
                  static_cast<std::size_t>(W));
    check_cl(clEnqueueWriteBuffer(ctx.queue, dst, CL_TRUE, 0, pack.size(), pack.data(), 0, nullptr,
                                  nullptr),
             "upload packed");
  };
  upload(prev_u8, prev);
  upload(next_u8, next);

  std::vector<cl_mem> pyr0(levels, nullptr), pyr1(levels, nullptr);
  for (int l = 0; l < levels; ++l) {
    const std::size_t pix = static_cast<std::size_t>(widths[l]) * heights[l] * sizeof(float);
    pyr0[l] = buf(ctx.context, CL_MEM_READ_WRITE, pix);
    pyr1[l] = buf(ctx.context, CL_MEM_READ_WRITE, pix);
  }

  auto set_u8 = [&](cl_mem src, cl_mem dst, int w, int h) {
    check_cl(clSetKernelArg(ctx.k_u8, 0, sizeof(cl_mem), &src), "u8");
    check_cl(clSetKernelArg(ctx.k_u8, 1, sizeof(cl_mem), &dst), "u8d");
    check_cl(clSetKernelArg(ctx.k_u8, 2, sizeof(int), &w), "w");
    check_cl(clSetKernelArg(ctx.k_u8, 3, sizeof(int), &h), "h");
    check_cl(clSetKernelArg(ctx.k_u8, 4, sizeof(int), &w), "s");
    enqueue_2d(ctx.queue, ctx.k_u8, w, h);
  };
  set_u8(prev_u8, pyr0[0], W, H);
  set_u8(next_u8, pyr1[0], W, H);
  for (int l = 1; l < levels; ++l) {
    check_cl(clSetKernelArg(ctx.k_down, 0, sizeof(cl_mem), &pyr0[l - 1]), "d0");
    check_cl(clSetKernelArg(ctx.k_down, 1, sizeof(cl_mem), &pyr0[l]), "d0o");
    check_cl(clSetKernelArg(ctx.k_down, 2, sizeof(int), &widths[l - 1]), "sw");
    check_cl(clSetKernelArg(ctx.k_down, 3, sizeof(int), &heights[l - 1]), "sh");
    check_cl(clSetKernelArg(ctx.k_down, 4, sizeof(int), &widths[l]), "dw");
    check_cl(clSetKernelArg(ctx.k_down, 5, sizeof(int), &heights[l]), "dh");
    enqueue_2d(ctx.queue, ctx.k_down, widths[l], heights[l]);
    check_cl(clSetKernelArg(ctx.k_down, 0, sizeof(cl_mem), &pyr1[l - 1]), "d1");
    check_cl(clSetKernelArg(ctx.k_down, 1, sizeof(cl_mem), &pyr1[l]), "d1o");
    enqueue_2d(ctx.queue, ctx.k_down, widths[l], heights[l]);
  }

  const float scale0 = std::ldexp(1.0f, -max_level);
  std::vector<float> pts(static_cast<std::size_t>(n) * 2), flow(static_cast<std::size_t>(n) * 2, 0.0f);
  for (int i = 0; i < n; ++i) {
    pts[i * 2] = prev_pts[i].x * scale0;
    pts[i * 2 + 1] = prev_pts[i].y * scale0;
  }
  cl_mem pts_b = buf(ctx.context, CL_MEM_READ_WRITE, pts.size() * sizeof(float));
  cl_mem flow_b = buf(ctx.context, CL_MEM_READ_WRITE, flow.size() * sizeof(float));
  cl_mem status_b = buf(ctx.context, CL_MEM_READ_WRITE, static_cast<std::size_t>(n));
  cl_mem err_b = buf(ctx.context, CL_MEM_READ_WRITE, static_cast<std::size_t>(n) * sizeof(float));
  check_cl(clEnqueueWriteBuffer(ctx.queue, pts_b, CL_TRUE, 0, pts.size() * sizeof(float), pts.data(),
                                0, nullptr, nullptr),
           "pts");
  check_cl(clEnqueueWriteBuffer(ctx.queue, flow_b, CL_TRUE, 0, flow.size() * sizeof(float),
                                flow.data(), 0, nullptr, nullptr),
           "flow");
  check_cl(clEnqueueWriteBuffer(ctx.queue, status_b, CL_TRUE, 0, static_cast<std::size_t>(n),
                                status.data(), 0, nullptr, nullptr),
           "status");

  const int max_iters = impl_->options.max_iters;
  const float eps = impl_->options.epsilon;
  const float min_eig = impl_->options.min_eig;
  const float two = 2.0f;

  for (int level = max_level; level >= 0; --level) {
    if (level != max_level) {
      check_cl(clSetKernelArg(ctx.k_scale, 0, sizeof(cl_mem), &pts_b), "sp");
      check_cl(clSetKernelArg(ctx.k_scale, 1, sizeof(cl_mem), &flow_b), "sf");
      check_cl(clSetKernelArg(ctx.k_scale, 2, sizeof(int), &n), "sn");
      check_cl(clSetKernelArg(ctx.k_scale, 3, sizeof(float), &two), "ss");
      enqueue_1d(ctx.queue, ctx.k_scale, n);
    }
    check_cl(clSetKernelArg(ctx.k_track, 0, sizeof(cl_mem), &pyr0[level]), "t0");
    check_cl(clSetKernelArg(ctx.k_track, 1, sizeof(cl_mem), &pyr1[level]), "t1");
    check_cl(clSetKernelArg(ctx.k_track, 2, sizeof(cl_mem), &pts_b), "tp");
    check_cl(clSetKernelArg(ctx.k_track, 3, sizeof(cl_mem), &flow_b), "tf");
    check_cl(clSetKernelArg(ctx.k_track, 4, sizeof(cl_mem), &status_b), "ts");
    check_cl(clSetKernelArg(ctx.k_track, 5, sizeof(cl_mem), &err_b), "te");
    check_cl(clSetKernelArg(ctx.k_track, 6, sizeof(int), &n), "tn");
    check_cl(clSetKernelArg(ctx.k_track, 7, sizeof(int), &widths[level]), "tw");
    check_cl(clSetKernelArg(ctx.k_track, 8, sizeof(int), &heights[level]), "th");
    check_cl(clSetKernelArg(ctx.k_track, 9, sizeof(int), &win_half), "thalf");
    check_cl(clSetKernelArg(ctx.k_track, 10, sizeof(int), &max_iters), "tit");
    check_cl(clSetKernelArg(ctx.k_track, 11, sizeof(float), &eps), "teps");
    check_cl(clSetKernelArg(ctx.k_track, 12, sizeof(float), &min_eig), "teig");
    enqueue_1d(ctx.queue, ctx.k_track, n);
  }

  check_cl(clEnqueueReadBuffer(ctx.queue, flow_b, CL_TRUE, 0, flow.size() * sizeof(float),
                               flow.data(), 0, nullptr, nullptr),
           "read flow");
  check_cl(clEnqueueReadBuffer(ctx.queue, status_b, CL_TRUE, 0, static_cast<std::size_t>(n),
                               status.data(), 0, nullptr, nullptr),
           "read status");
  check_cl(clEnqueueReadBuffer(ctx.queue, err_b, CL_TRUE, 0, static_cast<std::size_t>(n) * sizeof(float),
                               err.data(), 0, nullptr, nullptr),
           "read err");

  for (int i = 0; i < n; ++i) {
    if (status[i]) {
      next_pts[i] = {prev_pts[i].x + flow[i * 2], prev_pts[i].y + flow[i * 2 + 1]};
    } else {
      next_pts[i] = prev_pts[i];
      err[i] = 1e6f;
    }
  }

  release(prev_u8);
  release(next_u8);
  release(pts_b);
  release(flow_b);
  release(status_b);
  release(err_b);
  for (int l = 0; l < levels; ++l) {
    release(pyr0[l]);
    release(pyr1[l]);
  }
}

} // namespace optical_flow_sdk

#endif
