/*
 * Copyright (C) 2025 Intel Corporation
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#include <type_traits>

#include "device_impl.h"
#include "gpu_kernels.h"

using namespace gpu;

#define INC(x, l) sycl::min(x + 1, l - 1)
const int INTER_RESIZE_COEF_BITS = 11;
const int INTER_RESIZE_COEF_SCALE = 1 << INTER_RESIZE_COEF_BITS;  // 2048
const int CAST_BITS = INTER_RESIZE_COEF_BITS << 1;                // 22

template <typename T>
struct ResizeKernelParams
{
  const T * src_ptr;
  T * dst_ptr;
  int src_cols;
  int src_rows;
  int src_steps;
  int dst_cols;
  int dst_rows;
  int dst_steps;
  int depth;
  float ifx;
  float ify;
  Rect src_rect;
  Rect dst_rect;
};

template <typename T>
struct resizeNearest
{
  ResizeKernelParams<T> params;

  resizeNearest(ResizeKernelParams<T> in_params) { params = in_params; }

  void operator()(sycl::id<2> it)
  {
    int dx = it[0];
    int dy = it[1];

    if (dx < params.dst_cols && dy < params.dst_rows) {
      float s1 = dx * params.ifx;
      float s2 = dy * params.ify;

      int sx = sycl::min<int>(sycl::floor(s1), params.src_cols - 1);
      int sy = sycl::min<int>(sycl::floor(s2), params.src_rows - 1);

      T src_value =
        *(params.src_ptr + sy * params.src_steps + sx * params.depth + params.src_rect.x);
      T * dst_offset =
        params.dst_ptr + dy * params.dst_steps + dx * params.depth + params.dst_rect.x;

      *dst_offset = src_value;
    }
  }
};

template <typename T>
struct resizeLinear
{
  ResizeKernelParams<T> params;

  resizeLinear(ResizeKernelParams<T> in_params) { params = in_params; }

  void operator()(sycl::id<2> it)
  {
    int dx = it[0];
    int dy = it[1];

    if (dx < params.dst_cols && dy < params.dst_rows) {
      float sx = ((dx + 0.5f) * params.ifx - 0.5f), sy = ((dy + 0.5f) * params.ify - 0.5f);
      int x = sycl::floor(sx), y = sycl::floor(sy);

      float u = sx - x, v = sy - y;

      if (x < 0) {
        x = 0;
        u = 0;
      }
      if (x >= params.src_cols) {
        x = params.src_cols - 1;
        u = 0;
      }
      if (y < 0) {
        y = 0;
        v = 0;
      }
      if (y >= params.src_rows) {
        y = params.src_rows - 1;
        v = 0;
      }

      int y_ = INC(y, params.src_rows);
      int x_ = INC(x, params.src_cols);

      T uval;

      if (params.depth == 1) {
        using WT = int;

        u = u * INTER_RESIZE_COEF_SCALE;
        v = v * INTER_RESIZE_COEF_SCALE;

        int U = std::rint(u);
        int V = std::rint(v);
        int U1 = std::rint(INTER_RESIZE_COEF_SCALE - u);
        int V1 = std::rint(INTER_RESIZE_COEF_SCALE - v);

        WT data0 =
          (WT) * (params.src_ptr + y * params.src_steps + x * params.depth + params.src_rect.x);
        WT data1 =
          (WT) * (params.src_ptr + y * params.src_steps + x_ * params.depth + params.src_rect.x);
        WT data2 =
          (WT) * (params.src_ptr + y_ * params.src_steps + x * params.depth + params.src_rect.x);
        WT data3 =
          (WT) * (params.src_ptr + y_ * params.src_steps + x_ * params.depth + params.src_rect.x);

        WT val =
          sycl::mul24((WT)sycl::mul24(U1, V1), data0) + sycl::mul24((WT)sycl::mul24(U, V1), data1) +
          sycl::mul24((WT)sycl::mul24(U1, V), data2) + sycl::mul24((WT)sycl::mul24(U, V), data3);

        uval = (T)((val + (1 << (CAST_BITS - 1))) >> CAST_BITS);
      } else {
        // Not implemented yet
      }

      T * dst_offset =
        params.dst_ptr + dy * params.dst_steps + dx * params.depth + params.dst_rect.x;

      *dst_offset = uval;
    }
  }
};

template <typename T>
struct ResizeKernel
{
  ResizeKernelParams<T> params_;

  ResizeKernel(
    const gpu::Image8u & src, gpu::Image8u & dst, const double fx, const double fy, const int depth)
  {
    if (src.cols() == 0 || src.rows() == 0 || dst.cols() == 0 || dst.rows() == 0) {
      throw("Invalid image buffer size");
    }

    params_.src_cols = src.cols();
    params_.src_rows = src.rows();
    params_.src_steps = src.elem_step();
    params_.dst_cols = dst.cols();
    params_.dst_rows = dst.rows();
    params_.dst_steps = dst.elem_step();
    params_.src_ptr = src.data();
    params_.dst_ptr = dst.data();
    params_.src_rect = src.getRect();
    params_.dst_rect = dst.getRect();

    float inv_fx = 0.f, inv_fy = 0.f;

    if ((fx == 0.0) || (fy == 0.0)) {
      double scale_x = (double)dst.cols() / src.cols();
      double scale_y = (double)dst.rows() / src.rows();

      params_.ifx = (float)(1.0 / scale_x);
      params_.ify = (float)(1.0 / scale_y);
    } else {
      params_.ifx = (float)(1.0f / fx);
      params_.ify = (float)(1.0f / fy);
    }

    params_.depth = depth;
  }

  ResizeKernelParams<T> getResizeParams() { return params_; }
};

template <typename T>
void ORBKernel::resizeImpl(
  const DevImage<T> & src_image, DevImage<T> & dst_image, const InterpolationType inter_type,
  const double fx, const double fy, Device::Ptr dev)
{
  if ((inter_type != kInterpolationNearest) && (inter_type != kInterpolationLinear)) {
    throw("Resize unsupported interpolation");
    return;
  }

  sycl::queue * q = dev->GetDeviceImpl()->get_queue();

  if ((dst_image.cols() == 0) || (dst_image.rows() == 0)) {
    dst_image.resize(fy * src_image.rows(), fx * src_image.cols());
  }

  ResizeKernel<T> sycl_resize(src_image, dst_image, fx, fy, sizeof(T));
  auto params = sycl_resize.getResizeParams();

  sycl::event event = q->submit([&](sycl::handler & cgh) {
    cgh.parallel_for(sycl::range<2>(dst_image.cols(), dst_image.rows()), [=](sycl::id<2> it) {
      if (inter_type == kInterpolationLinear) {
        resizeLinear linearOps(params);
        linearOps(it);
      } else if (inter_type == kInterpolationNearest) {
        resizeNearest nearestOps(params);
        nearestOps(it);
      }
    });
  });

  auto eventPtr = DeviceEvent::create();
  eventPtr->add(event);
  dst_image.setEvent(eventPtr);
}

template void ORBKernel::resizeImpl(
  const DevImage<uint8_t> & src_image, DevImage<uint8_t> & dst_image,
  const InterpolationType inter_type, const double fx, const double fy, Device::Ptr dev);
