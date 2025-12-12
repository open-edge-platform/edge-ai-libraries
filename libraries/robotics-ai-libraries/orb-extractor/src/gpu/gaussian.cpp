// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#include <algorithm>
#include <type_traits>
#include <typeinfo>

#include "device_impl.h"
#include "gpu_kernels.h"

using namespace gpu;

#define SHIFT_BITS 16

template <typename T>
struct GaussianBlurKernelParams
{
  const T * src_ptr;
  T * dst_ptr;
  const T * matx_ptr;
  const T * maty_ptr;
  Rect src_rect;
  Rect dst_rect;
  int delta;
  sycl::int2 anchor;
  uint32_t kernelX_cols;
  uint32_t kernelX_rows;
  uint32_t kernelY_cols;
  uint32_t kernelY_rows;
  uint32_t src_cols;
  uint32_t src_rows;
  uint32_t src_step;
  uint32_t dst_cols;
  uint32_t dst_rows;
  uint32_t dst_step;
};

template <typename T>
struct WorkingType
{
  using type = T;
};

template <>
struct WorkingType<unsigned char>
{
  using type = int;
};

template <>
struct WorkingType<float>
{
  using type = float;
};

struct CONSTANT
{
  auto operator()(int & x, int maxV) {}

  template <typename T>
  auto operator()(
    int & x, int y, int rEdge, int tEdge, int constant, GaussianBlurKernelParams<T> * params)
  {
    T value;

    if ((x < 0) | (x >= rEdge) | (y < 0) | (y >= tEdge)) {
      value = constant;
    } else {
      value = *(params->src_ptr + y * params->src_step + x);
    }

    return value;
  }
};

struct REPLICATE
{
  auto operator()(int & x, int maxV) { x = sycl::clamp(x, 0, maxV - 1); }

  template <typename T>
  auto operator()(
    int & x, int y, int rEdge, int tEdge, int constant, GaussianBlurKernelParams<T> * params)
  {
    return *(params->src_ptr + y * params->src_step + x);
  }
};

struct WRAP
{
  auto operator()(int & x, int maxV) { x = x + maxV % maxV; }

  template <typename T>
  auto operator()(
    int x, int y, int rEdge, int tEdge, int constant, GaussianBlurKernelParams<T> * params)
  {
    return *(params->src_ptr + y * params->src_step + x);
  }
};

struct REFLECT
{
  auto operator()(int & x, int maxV)
  {
    x = sycl::min((maxV - 1) * 2 - x + 1, sycl::max(x, -x - 1));
  }

  template <typename T>
  auto operator()(
    int x, int y, int rEdge, int tEdge, int constant, GaussianBlurKernelParams<T> * params)
  {
    return *(params->src_ptr + y * params->src_step + x);
  }
};

struct REFLECT_101
{
  auto operator()(int & x, int maxV) { x = sycl::min((maxV - 1) * 2 - x, sycl::max(x, -x)); }

  template <typename T>
  auto operator()(
    int x, int y, int rEdge, int tEdge, int constant, GaussianBlurKernelParams<T> * params)
  {
    return *(params->src_ptr + y * params->src_step + x);
  }
};

template <class BorderType>
auto extrapolate(int & x, int maxV, BorderType border_ops) -> void
{
  border_ops(x, maxV);
}

template <class BorderType, typename T>
auto element(
  int x, int y, int rEdge, int tEdge, int constant, GaussianBlurKernelParams<T> * param,
  BorderType border_ops) -> float
{
  return border_ops(x, y, rEdge, tEdge, constant, param);
}

template <typename T>
struct gaussianBlur3x3
{
  GaussianBlurKernelParams<T> params;

  gaussianBlur3x3(GaussianBlurKernelParams<T> in_params) { params = in_params; }

  void operator()(sycl::nd_item<2> it)
  {
    auto dx = it.get_global_id(0);
    auto dy = it.get_global_id(1);

    intelext::printf("Not implemented yet");
  }
};

template <typename T>
struct gaussianBlur5x5
{
  GaussianBlurKernelParams<T> params;

  gaussianBlur5x5(GaussianBlurKernelParams<T> in_params) { params = in_params; }

  void operator()(sycl::nd_item<2> it)
  {
    auto dx = it.get_global_id(0);
    auto dy = it.get_global_id(1);

    auto blk_x = it.get_group_range(0);
    auto blk_y = it.get_group_range(1);

    intelext::printf("Not implemented yet");
  }
};

template <typename T>
struct gaussianBlurSepFilter
{
  GaussianBlurKernelParams<T> params;

  gaussianBlurSepFilter(const GaussianBlurKernelParams<T> input) { params = input; }

  template <typename BorderType, typename WT>
  void operator()(
    sycl::nd_item<2> it, const sycl::local_accessor<WT, 2> & lm,
    const sycl::local_accessor<WT, 2> & lmy)
  {
    auto lix = it.get_local_id(0);
    auto liy = it.get_local_id(1);

    auto x = it.get_global_id(0);
    auto yy = it.get_global_id(1);

    // calculate pixel position in source image taking image offset into account
    int srcX = x + params.src_rect.x - params.anchor.x();
    int BLK_X = it.get_local_range(0);
    int BLK_Y = it.get_local_range(1);

    BorderType border;

    // extrapolate coordinates, if needed
    // and read my own source pixel into local memory
    // with account for extra border pixels, which will be read by starting
    // workitems
    int clocY = liy;
    do {
      int yb = clocY + params.src_rect.y - params.anchor.y();
      extrapolate(yb, (int)params.src_rows, border);

      int clocX = lix;
      int cSrcX = srcX;
      do {
        int xb = cSrcX;
        extrapolate(xb, (int)params.src_cols, border);

        lm[clocY][clocX] = element(xb, yb, params.src_cols, params.src_rows, 0, &params, border);

        clocX += BLK_X;
        cSrcX += BLK_X;
      } while (clocX < BLK_X + (params.anchor.x() * 2));

      clocY += BLK_Y;
    } while (clocY < BLK_Y + (params.anchor.y() * 2));
    it.barrier(sycl::access::fence_space::local_space);

    for (int y = 0; y < params.dst_rows; y += BLK_Y) {
      // do vertical filter pass
      // and store intermediate results to second local memory array
      int i, clocX = lix;
      WT sum = (WT)0;
      do {
        sum = (WT)0;
        for (i = 0; i <= 2 * params.anchor.y(); i++)
          sum = lm[liy + i][clocX] * params.maty_ptr[i] + sum;

        lmy[liy][clocX] = sum;
        clocX += BLK_X;
      } while (clocX < BLK_X + params.anchor.x() * 2);
      it.barrier(sycl::access::fence_space::local_space);

      // if this pixel happened to be out of image borders because of global
      // size rounding, then just return
      if ((x < params.dst_cols) && (y + liy < params.dst_rows)) {
        // do second horizontal filter pass
        // and calculate final result
        sum = (WT)params.delta;
        for (i = 0; i <= 2 * params.anchor.x(); i++) {
          sum = lmy[liy][lix + i] * params.matx_ptr[i] + sum;
        }

        if constexpr (std::is_same_v<T, unsigned char>) {
          sum = (sum + (1 << (SHIFT_BITS - 1))) >> SHIFT_BITS;
        }

        // store result into destination image
        *(params.dst_ptr + (y + liy) * params.dst_step + (x + params.dst_rect.x)) = (T)sum;
      }
      it.barrier(sycl::access::fence_space::local_space);

      for (int i = liy * BLK_X + lix; i < (params.anchor.y() * 2) * (BLK_X + params.anchor.x() * 2);
           i += BLK_X * BLK_Y) {
        int clocX = i % (BLK_X + params.anchor.x() * 2);
        int clocY = i / (BLK_X + params.anchor.x() * 2);
        lm[clocY][clocX] = lm[clocY + BLK_Y][clocX];
      }
      it.barrier(sycl::access::fence_space::local_space);

      int yb = y + liy + BLK_Y + params.src_rect.y + params.anchor.y();
      extrapolate(yb, (int)params.src_rows, border);

      clocX = lix;
      int cSrcX = x + params.src_rect.x - params.anchor.x();
      do {
        int xb = cSrcX;
        extrapolate(xb, (int)params.src_cols, border);
        lm[liy + 2 * params.anchor.y()][clocX] =
          element(xb, yb, params.src_cols, params.src_rows, 0, &params, border);

        clocX += BLK_X;
        cSrcX += BLK_X;
      } while (clocX < BLK_X + params.anchor.x() * 2);

      it.barrier(sycl::access::fence_space::local_space);
    }
  }
};

template <typename T>
struct GaussianBlurKernel
{
  GaussianBlurKernelParams<T> params_;
  static constexpr size_t optimizedLocalWidth = 16;
  static constexpr size_t optimizedLocalHeight = 32;
  uint8_t gaussian_7x7[7] = {18, 34, 48, 56, 48, 34, 18};

  GaussianBlurKernel(
    const DevImage<T> & src, DevImage<T> & dst, DevImage<T> & kernelX, DevImage<T> & kernelY,
    short kernelSize)
  {
    if (src.cols() == 0 || src.rows() == 0 || dst.cols() == 0 || dst.rows() == 0) {
      throw("Invalid image buffer size");
    }

    params_.src_ptr = src.data();
    params_.dst_ptr = dst.data();
    params_.dst_cols = dst.cols();
    params_.dst_rows = dst.rows();

    params_.src_cols = src.cols();
    params_.src_rows = src.rows();

    params_.src_rect = src.getRect();
    params_.dst_rect = dst.getRect();

    params_.src_step = src.elem_step();
    params_.dst_step = dst.elem_step();

    if (kernelX.empty() || kernelY.empty()) {
      kernelX.resize(1, kernelSize);
      kernelY.resize(1, kernelSize);

      kernelX.upload(gaussian_7x7);
      kernelY.upload(gaussian_7x7);
    }

    params_.matx_ptr = kernelX.data();
    params_.maty_ptr = kernelY.data();

    params_.kernelX_cols = kernelX.cols();
    params_.kernelX_rows = kernelX.rows();

    params_.kernelY_cols = kernelY.cols();
    params_.kernelY_rows = kernelY.rows();

    params_.anchor.x() = params_.kernelX_cols >> 1;
    params_.anchor.y() = params_.kernelY_cols >> 1;

    params_.delta = 0.0f;
  }

  sycl::int2 getRadius() { return params_.anchor; }

  sycl::range<2> getLocalRange()
  {
    return sycl::range<2>{optimizedLocalWidth, optimizedLocalHeight};
  }

  sycl::range<2> getGlobalRange()
  {
    const size_t aligned_width = align(params_.src_cols, optimizedLocalWidth);
    return sycl::range<2>{aligned_width, optimizedLocalHeight};
  }

  GaussianBlurKernelParams<T> getKernelParams() { return params_; }
};

template <class BorderType, typename T>
void gaussianBlurImpl_(
  const DevImage<T> & src_image, DevImage<T> & dst_image, DevImage<T> & kernelX,
  DevImage<T> & kernelY, const short kernel_size, Device::Ptr dev)
{
  sycl::queue * q = dev->GetDeviceImpl()->get_queue();

  if ((dst_image.cols() == 0) || (dst_image.rows() == 0)) {
    dst_image.resize(src_image.rows(), src_image.cols());
  }

  GaussianBlurKernel<T> sycl_gaussian(src_image, dst_image, kernelX, kernelY, kernel_size);
  auto params = sycl_gaussian.getKernelParams();

  sycl::range<2> local, global;

  global = sycl_gaussian.getGlobalRange();
  local = sycl_gaussian.getLocalRange();
  auto radius = sycl_gaussian.getRadius();

  using WT = typename WorkingType<T>::type;

  sycl::event event = q->submit([&](sycl::handler & cgh) {
    auto lsmem = sycl::local_accessor<WT, 2>(
      sycl::range<2>{local[1] + 2 * radius.y(), local[0] + 2 * radius.x()}, cgh);
    auto lsmemDy =
      sycl::local_accessor<WT, 2>(sycl::range<2>{local[1], local[0] + 2 * radius.x()}, cgh);
    cgh.parallel_for(
      sycl::nd_range<2>(global, local), [=](sycl::nd_item<2> it) [[sycl::reqd_sub_group_size(32)]] {
        auto ops = gaussianBlurSepFilter(params);
        ops.template operator()<BorderType, WT>(it, lsmem, lsmemDy);
      });
  });

  auto eventPtr = DeviceEvent::create();
  eventPtr->add(event);
  dst_image.setEvent(eventPtr);
}

// explicit instantiations
template void gaussianBlurImpl_<REFLECT_101>(
  const DevImage<uint8_t> & src, DevImage<uint8_t> & dst, DevImage<uint8_t> & kernelX,
  DevImage<uint8_t> & kernelY, const short kernelSize, Device::Ptr dev);
template void gaussianBlurImpl_<REFLECT>(
  const DevImage<uint8_t> & src, DevImage<uint8_t> & dst, DevImage<uint8_t> & kernelX,
  DevImage<uint8_t> & kernelY, const short kernelSize, Device::Ptr dev);
template void gaussianBlurImpl_<WRAP>(
  const DevImage<uint8_t> & src, DevImage<uint8_t> & dst, DevImage<uint8_t> & kernelX,
  DevImage<uint8_t> & kernelY, const short kernelSize, Device::Ptr dev);
template void gaussianBlurImpl_<REPLICATE>(
  const DevImage<uint8_t> & src, DevImage<uint8_t> & dst, DevImage<uint8_t> & kernelX,
  DevImage<uint8_t> & kernelY, const short kernelSize, Device::Ptr dev);
template void gaussianBlurImpl_<CONSTANT>(
  const DevImage<uint8_t> & src, DevImage<uint8_t> & dst, DevImage<uint8_t> & kernelX,
  DevImage<uint8_t> & kernelY, const short kernelSize, Device::Ptr dev);

template <typename T>
void ORBKernel::gaussianBlurImpl(
  const DevImage<T> & src, DevImage<T> & dst, DevImage<T> & kernelX, DevImage<T> & kernelY,
  const short kernel_size, BorderTypes border, Device::Ptr dev)
{
  switch (border) {
    case BORDER_CONSTANT:
      gaussianBlurImpl_<CONSTANT>(src, dst, kernelX, kernelY, kernel_size, dev);
      break;
    case BORDER_REFLECT_101:
      gaussianBlurImpl_<REFLECT_101>(src, dst, kernelX, kernelY, kernel_size, dev);
      break;
    case BORDER_REFLECT:
      gaussianBlurImpl_<REFLECT>(src, dst, kernelX, kernelY, kernel_size, dev);
      break;
    case BORDER_REPLICATE:
      gaussianBlurImpl_<REPLICATE>(src, dst, kernelX, kernelY, kernel_size, dev);
      break;
    case BORDER_WRAP:
      gaussianBlurImpl_<WRAP>(src, dst, kernelX, kernelY, kernel_size, dev);
      break;
    default:
      break;
  }
}

// explicit instantiations
template void ORBKernel::gaussianBlurImpl(
  const DevImage<uint8_t> & src, DevImage<uint8_t> & dst, DevImage<uint8_t> & kernelX,
  DevImage<uint8_t> & kernelY, const short kernel_size, BorderTypes border, Device::Ptr dev);
