// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <algorithm>
#include <cmath>
#include <type_traits>

#include "device_impl.h"
#include "gpu_kernels.h"

using namespace gpu;

#define ROWS_PER_THREAD 8

template <typename T>
struct FastKernelParams
{
  const T * src_image_ptr;
  const T * mask_image_ptr;
  PartKey * keypoints_ptr;
  uint32_t * keypoints_count_ptr;
  sycl::int2 * group_pos_x_ptr;
  sycl::int2 * group_pos_y_ptr;
  uint32_t group_x_size;
  uint32_t group_y_size;
  uint32_t image_cols;
  uint32_t image_rows;
  uint32_t image_steps;
  uint32_t ini_threshold;
  uint32_t min_threshold;
  uint32_t edge_clip;
  uint32_t overlap;
  uint32_t cell_size;
  uint32_t num_images;
  bool mask_check;
  bool nms_required;
  Rect image_rect;
};

template <typename T>
struct fastExtKernelImpl
{
  FastKernelParams<T> params;

  fastExtKernelImpl(const FastKernelParams<T> in_params) { params = in_params; }

  void operator()(
    sycl::nd_item<2> it, const sycl::local_accessor<sycl::int2, 1> & local_key,
    const sycl::local_accessor<uint32_t, 1> & local_count, uint32_t threshold)
  {
    auto l_x = it.get_local_id(0);
    auto l_y = it.get_local_id(1);

    auto group_x = it.get_group(0);
    auto group_y = it.get_group(1);

    local_count[0] = 0;
    it.barrier(sycl::access::fence_space::local_space);

    auto min_x = params.group_pos_x_ptr[group_x].x();
    auto max_x = params.group_pos_x_ptr[group_x].y();
    auto min_y = params.group_pos_y_ptr[group_y].x();
    auto max_y = params.group_pos_y_ptr[group_y].y();

    auto g_x = l_x + min_x + 3;
    auto g_y = l_y * ROWS_PER_THREAD + min_y + 3;

    int step = params.image_steps;

    for (int i = 0; i < ROWS_PER_THREAD; i++) {
      if ((g_x < max_x - 3) && ((g_y + i) < max_y - 3)) {
        T * img = (T *)params.src_image_ptr + (g_y + i) * step + g_x;

        if (params.mask_check) {
          T * mask_img = (T *)params.mask_image_ptr + (g_y + i) * step + g_x;
          if (mask_img[0] == 0) {
            continue;
          }
        }

        int v = img[0], t0 = v - threshold, t1 = v + threshold;
        int k, tofs, v0, v1;
        int m0 = 0, m1 = 0;

        /* FAST corner detection: Compare pixel pairs symmetrically around center point
        ** For each pair of pixels at offset ±ofs from center:
        ** - Set bit in m0 if pixel is darker than threshold (< t0)
        ** - Set bit in m1 if pixel is brighter than threshold (> t1)
        ** This creates 16-bit masks where bits 0-7 represent one direction,
        // bits 8-15 represent the opposite direction around the circle */
#define UPDATE_MASK(idx, ofs)                          \
  tofs = ofs;                                          \
  v0 = img[tofs];                                      \
  v1 = img[-tofs];                                     \
  m0 |= ((v0 < t0) << idx) | ((v1 < t0) << (8 + idx)); \
  m1 |= ((v0 > t1) << idx) | ((v1 > t1) << (8 + idx))

        UPDATE_MASK(0, 3);

        if ((m0 | m1) == 0) continue;

        UPDATE_MASK(2, -step * 2 + 2);
        UPDATE_MASK(4, -step * 3);
        UPDATE_MASK(6, -step * 2 - 2);

#define EVEN_MASK (1 + 4 + 16 + 64)

        if (
          ((m0 | (m0 >> 8)) & EVEN_MASK) != EVEN_MASK &&
          ((m1 | (m1 >> 8)) & EVEN_MASK) != EVEN_MASK)
          continue;

        UPDATE_MASK(1, -step + 3);
        UPDATE_MASK(3, -step * 3 + 1);
        UPDATE_MASK(5, -step * 3 - 1);
        UPDATE_MASK(7, -step - 3);
        if (((m0 | (m0 >> 8)) & 255) != 255 && ((m1 | (m1 >> 8)) & 255) != 255) continue;

        m0 |= m0 << 16;
        m1 |= m1 << 16;

#define CHECK0(i) ((m0 & (511 << i)) == (511 << i))
#define CHECK1(i) ((m1 & (511 << i)) == (511 << i))

        if (
          CHECK0(0) + CHECK0(1) + CHECK0(2) + CHECK0(3) + CHECK0(4) + CHECK0(5) + CHECK0(6) +
            CHECK0(7) + CHECK0(8) + CHECK0(9) + CHECK0(10) + CHECK0(11) + CHECK0(12) + CHECK0(13) +
            CHECK0(14) + CHECK0(15) +

            CHECK1(0) + CHECK1(1) + CHECK1(2) + CHECK1(3) + CHECK1(4) + CHECK1(5) + CHECK1(6) +
            CHECK1(7) + CHECK1(8) + CHECK1(9) + CHECK1(10) + CHECK1(11) + CHECK1(12) + CHECK1(13) +
            CHECK1(14) + CHECK1(15) ==
          0)
          continue;

        sycl::atomic_ref<
          uint32_t, sycl::memory_order::relaxed, sycl::memory_scope::system,
          sycl::access::address_space::local_space>
          kp_loc(local_count[0]);

        int idx = kp_loc++;
        local_key[idx].x() = g_x;
        local_key[idx].y() = g_y + i;
      }
    }
  }
};

template <typename T>
struct nmsExt
{
  FastKernelParams<T> params;
  nmsExt(const FastKernelParams<T> in_params) { params = in_params; }

  __device_inline__ int cornerScore(const T * img, int step)
  {
    int k, tofs, v = img[0], a0 = 0, b0;
    int d[16];
#define LOAD2(idx, ofs)            \
  tofs = ofs;                      \
  d[idx] = (short)(v - img[tofs]); \
  d[idx + 8] = (short)(v - img[-tofs])
    LOAD2(0, 3);
    LOAD2(1, -step + 3);
    LOAD2(2, -step * 2 + 2);
    LOAD2(3, -step * 3 + 1);
    LOAD2(4, -step * 3);
    LOAD2(5, -step * 3 - 1);
    LOAD2(6, -step * 2 - 2);
    LOAD2(7, -step - 3);

#pragma unroll
    for (k = 0; k < 16; k += 2) {
      int a = sycl::min((int)d[(k + 1) & 15], (int)d[(k + 2) & 15]);
      a = sycl::min(a, (int)d[(k + 3) & 15]);
      a = sycl::min(a, (int)d[(k + 4) & 15]);
      a = sycl::min(a, (int)d[(k + 5) & 15]);
      a = sycl::min(a, (int)d[(k + 6) & 15]);
      a = sycl::min(a, (int)d[(k + 7) & 15]);
      a = sycl::min(a, (int)d[(k + 8) & 15]);
      a0 = sycl::max(a0, sycl::min(a, (int)d[k & 15]));
      a0 = sycl::max(a0, sycl::min(a, (int)d[(k + 9) & 15]));
    }

    b0 = -a0;
#pragma unroll
    for (k = 0; k < 16; k += 2) {
      int b = sycl::max((int)d[(k + 1) & 15], (int)d[(k + 2) & 15]);
      b = sycl::max(b, (int)d[(k + 3) & 15]);
      b = sycl::max(b, (int)d[(k + 4) & 15]);
      b = sycl::max(b, (int)d[(k + 5) & 15]);
      b = sycl::max(b, (int)d[(k + 6) & 15]);
      b = sycl::max(b, (int)d[(k + 7) & 15]);
      b = sycl::max(b, (int)d[(k + 8) & 15]);

      b0 = sycl::min(b0, sycl::max(b, (int)d[k]));
      b0 = sycl::min(b0, sycl::max(b, (int)d[(k + 9) & 15]));
    }

    return -b0 - 1;
  }

  void operator()(
    sycl::nd_item<2> it, const sycl::local_accessor<sycl::int2, 1> & local_key,
    const sycl::local_accessor<uint32_t, 1> & local_count,
    const sycl::local_accessor<uint32_t, 1> & count_nms)
  {
    auto idx = it.get_local_linear_id();
    auto group_x = it.get_group(0);
    auto group_y = it.get_group(1);
    auto step = params.image_steps;
    auto cols = params.group_pos_x_ptr[group_x].y() - params.group_pos_x_ptr[group_x].x();
    auto rows = params.group_pos_y_ptr[group_y].y() - params.group_pos_y_ptr[group_y].x();
    auto l_x = it.get_local_id(0);
    auto l_y = it.get_local_id(1);

    count_nms[0] = 0;
    it.barrier(sycl::access::fence_space::local_space);

    if (idx < local_count[0]) {
      int ax = local_key[idx].x();
      int ay = local_key[idx].y();

      const T * img = params.src_image_ptr + ay * step + ax;

      auto x = ax - params.group_pos_x_ptr[group_x].x();
      auto y = ay - params.group_pos_x_ptr[group_y].x();
      int s = cornerScore(img, step);

      if (
        (x < 4 || s > cornerScore(img - 1, step)) + (y < 4 || s > cornerScore(img - step, step)) !=
        2)
        return;

      if (
        (x >= cols - 4 || s > cornerScore(img + 1, step)) +
          (y >= rows - 4 || s > cornerScore(img + step, step)) +
          (x < 4 || y < 4 || s > cornerScore(img - step - 1, step)) +
          (x >= cols - 4 || y < 4 || s > cornerScore(img - step + 1, step)) +
          (x < 4 || y >= rows - 4 || s > cornerScore(img + step - 1, step)) +
          (x >= cols - 4 || y >= rows - 4 || s > cornerScore(img + step + 1, step)) ==
        6) {
        sycl::atomic_ref<
          uint32_t, sycl::memory_order::relaxed, sycl::memory_scope::system,
          sycl::access::address_space::global_space>
          global_loc(params.keypoints_count_ptr[0]);

        sycl::atomic_ref<
          uint32_t, sycl::memory_order::relaxed, sycl::memory_scope::device,
          sycl::access::address_space::local_space>
          nms_counter(count_nms[0]);

        nms_counter++;
        int global_idx = global_loc++;
        params.keypoints_ptr[global_idx].pt.x = ax - params.edge_clip;
        params.keypoints_ptr[global_idx].pt.y = ay - params.edge_clip;
        params.keypoints_ptr[global_idx].response = s;
        params.keypoints_ptr[global_idx].angle = -1.0f;
      }
    }
  }
};

template <typename T>
struct FastExtKernel
{
  FastKernelParams<T> params_;
  static constexpr uint32_t optimizedLocalWidth = 32;

  sycl::range<2> getLocalRange()
  {
    auto local_thread = params_.cell_size + params_.overlap;
    auto local_width_thread = align(local_thread, optimizedLocalWidth);
    auto local_height_thread = align(local_thread / ROWS_PER_THREAD, ROWS_PER_THREAD);

    return sycl::range<2>{local_width_thread, local_height_thread};
  }

  sycl::range<2> getGlobalRange()
  {
    auto min_border_x = params_.edge_clip;
    auto min_border_y = min_border_x;
    auto max_border_x = params_.image_cols - min_border_x;
    auto max_border_y = params_.image_rows - min_border_y;

    if ((min_border_x > max_border_x) || (min_border_y > max_border_y)) {
      throw std::out_of_range("Unsupported scale factor\n");
    }

    const unsigned int width = max_border_x - min_border_x;
    const unsigned int height = max_border_y - min_border_y;

    auto local_threads = getLocalRange();

    const unsigned int num_cols = params_.group_x_size;
    const unsigned int num_rows = params_.group_y_size;

    return sycl::range<2>{num_cols * local_threads[0], num_rows * local_threads[1]};
  }

  void UpdateGroupPosition(DevArray<sycl::int2> & group_x_, DevArray<sycl::int2> & group_y_)
  {
    int blk_idx = 0;
    int image_count = 0;
    int min_x = 0;
    int max_x = 0;
    int current_width = (int)(params_.image_cols / params_.num_images);
    int total_width = (int)params_.image_cols;
    int mono_width = current_width;
    // int current_height = (int) (params_.image_rows / params_.num_images);
    int current_height = (int)params_.image_rows;
    // intelext::printf("\n current width:%d", current_width);
    // intelext::printf("\n params_.image_cols:%d", params_.image_cols);

    std::vector<sycl::int2> group_x, group_y;

    const unsigned int min_border_x = params_.edge_clip;
    const unsigned int min_border_y = params_.edge_clip;
    const unsigned int max_border_x = params_.image_cols - params_.edge_clip;
    const unsigned int max_border_y = params_.image_rows - params_.edge_clip;

    const unsigned int num_cols = std::ceil(params_.image_cols / params_.cell_size) + 1;
    const unsigned int num_rows = std::ceil(params_.image_rows / params_.cell_size) + 1;

    group_x.reserve(num_cols);
    group_y.reserve(num_rows);

    for (unsigned int j = 0; j < num_rows; ++j) {
      const unsigned int min_y = min_border_y + j * params_.cell_size;
      if (max_border_y - params_.overlap <= min_y) {
        continue;
      }
      unsigned int max_y = min_y + params_.cell_size + params_.overlap;
      if (max_border_y < max_y) {
        max_y = max_border_y;
      }
      group_y.push_back({min_y, max_y});
    }

    while (1) {
      if (min_x + params_.cell_size < current_width - params_.edge_clip) {
        min_x = blk_idx++ * params_.cell_size + mono_width * image_count + params_.edge_clip;
        max_x = min_x + params_.cell_size + params_.overlap;
        if (max_x > current_width - params_.edge_clip) {
          max_x = current_width - params_.edge_clip;
        }

        group_x.push_back({min_x, max_x});
        // intelext::printf("\n min_x:%d , max_x:%d", min_x, max_x);

        if (min_x > total_width - params_.edge_clip) {
          // intelext::printf("\n pop_min_x:%d , pop_max_x:%d", min_x, max_x);
          group_x.pop_back();
          break;
        }
      } else {
        blk_idx = 0;
        image_count++;
        current_width += mono_width;
      }
    }

    group_x_.resize(group_x.size());
    group_x_.upload(group_x.data(), group_x.size());

    group_y_.resize(group_y.size());
    group_y_.upload(group_y.data(), group_y.size());
  }

  FastExtKernel(
    const DevImage<T> & src_image, const DevImage<T> & mask_image, const bool mask_check,
    const uint32_t ini_threshold, const uint32_t min_threshold, const uint32_t edge_clip,
    const uint32_t overlap, const uint32_t cell_size, const uint32_t num_images,
    const uint32_t max_keypoints_size, const uint32_t nms_required,
    DevArray<sycl::int2> & dev_group_x, DevArray<sycl::int2> & dev_group_y,
    DevArray<PartKey> & dev_tmp_keypoints, Vec32u & dev_keypoints_count)
  {
    if (src_image.cols() == 0 || src_image.rows() == 0) {
      throw("Invalid image buffer size");
    }

    if (
      mask_check &&
      ((src_image.cols() != mask_image.cols()) || (src_image.rows() != mask_image.rows()))) {
      throw("Fast kernel expect src image and mask image have same size");
    }

    dev_tmp_keypoints.resize(max_keypoints_size);
    dev_keypoints_count.resize(1);
    dev_keypoints_count.data()[0] = 0;

    params_.image_cols = src_image.cols();
    params_.image_rows = src_image.rows();
    params_.image_steps = src_image.elem_step();
    params_.src_image_ptr = src_image.data();
    params_.image_rect = src_image.getRect();
    params_.mask_image_ptr = mask_image.data();
    params_.keypoints_ptr = dev_tmp_keypoints.data();
    params_.keypoints_count_ptr = dev_keypoints_count.data();
    params_.mask_check = mask_check;
    params_.ini_threshold = ini_threshold;
    params_.min_threshold = min_threshold;
    params_.edge_clip = edge_clip;
    params_.overlap = overlap;
    params_.cell_size = cell_size;
    params_.num_images = num_images;
    params_.nms_required = nms_required;

    if (dev_group_x.empty() || dev_group_y.empty()) UpdateGroupPosition(dev_group_x, dev_group_y);

    params_.group_x_size = dev_group_x.size();
    params_.group_pos_x_ptr = dev_group_x.data();

    params_.group_y_size = dev_group_y.size();
    params_.group_pos_y_ptr = dev_group_y.data();
  }

  FastKernelParams<T> getParams() { return params_; }
};

template <typename T>
void ORBKernel::fastExtImpl(
  const DevImage<T> & src_image, const DevImage<T> & mask_image, const bool mask_check,
  const uint32_t ini_threshold, const uint32_t min_threshold, const uint32_t edge_clip,
  const uint32_t overlap, const uint32_t cell_size, const uint32_t num_images, const bool nmsOn,
  const uint32_t max_keypoints_size, DevArray<sycl::int2> & dev_group_x,
  DevArray<sycl::int2> & dev_group_y, DevArray<PartKey> & dev_keypoints_tmp,
  Vec32u & dev_keypoints_count, Device::Ptr dev)
{
  sycl::queue * q = dev->GetDeviceImpl()->get_queue();

  FastExtKernel<T> sycl_fast(
    src_image, mask_image, mask_check, ini_threshold, min_threshold, edge_clip, overlap, cell_size,
    num_images, max_keypoints_size, nmsOn, dev_group_x, dev_group_y, dev_keypoints_tmp,
    dev_keypoints_count);

  auto params = sycl_fast.getParams();
  sycl::range<2> global = sycl_fast.getGlobalRange();
  sycl::range<2> local = sycl_fast.getLocalRange();

  sycl::event event = q->submit([&](sycl::handler & cgh) {
    auto keys_mem = sycl::local_accessor<sycl::int2, 1>(local[1] * local[0], cgh);
    auto counts_fast = sycl::local_accessor<uint32_t, 1>(2, cgh);
    auto counts_nms = sycl::local_accessor<uint32_t, 1>(2, cgh);

    cgh.parallel_for(
      sycl::nd_range<2>(global, local), [=](sycl::nd_item<2> it) [[sycl::reqd_sub_group_size(16)]] {
        fastExtKernelImpl fastOps(params);
        fastOps(it, keys_mem, counts_fast, params.ini_threshold);
        it.barrier(sycl::access::fence_space::local_space);

        if (params.nms_required) {
          nmsExt nmsOps(params);
          nmsOps(it, keys_mem, counts_fast, counts_nms);
          it.barrier(sycl::access::fence_space::local_space);

          if (counts_nms[0] == 0) {
            fastOps(it, keys_mem, counts_fast, params.min_threshold);
            it.barrier(sycl::access::fence_space::local_space);
            nmsOps(it, keys_mem, counts_fast, counts_nms);
          }
        } else {
          if (counts_fast[0] == 0) fastOps(it, keys_mem, counts_fast, params.min_threshold);

          it.barrier(sycl::access::fence_space::local_space);

          sycl::atomic_ref<
            uint32_t, sycl::memory_order::relaxed, sycl::memory_scope::system,
            sycl::access::address_space::global_space>
            global_loc(params.keypoints_count_ptr[0]);

          auto local_idx = it.get_local_linear_id();
          if (local_idx < counts_fast[0]) {
            auto global_idx = global_loc++;

            params.keypoints_ptr[global_idx].pt.x = keys_mem[local_idx].x() - params.edge_clip;
            params.keypoints_ptr[global_idx].pt.y = keys_mem[local_idx].y() - params.edge_clip;
            params.keypoints_ptr[global_idx].angle = -1.0f;
          }
        }
      });
  });

  auto eventPtr = DeviceEvent::create();
  eventPtr->add(event);
  dev_keypoints_tmp.setEvent(eventPtr);
  dev_keypoints_count.setEvent(eventPtr);
}

template void ORBKernel::fastExtImpl(
  const DevImage<uint8_t> & src_image, const DevImage<uint8_t> & mask_image, const bool mask_check,
  const uint32_t ini_threshold, const uint32_t min_threshold, const uint32_t edge_clip,
  const uint32_t overlap, const uint32_t cell_size, const uint32_t num_images, const bool nmsOn,
  const uint32_t max_keypoints_size, DevArray<sycl::int2> & dev_group_x,
  DevArray<sycl::int2> & dev_group_y, DevArray<PartKey> & dev_keypoints_tmp,
  Vec32u & dev_keypoints_count, Device::Ptr dev);
