/*
 * Copyright (C) 2025 Intel Corporation
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <type_traits>

#include "device_impl.h"
#include "gpu_kernels.h"

using namespace gpu;

#define DESCRIPTOR_SIZE 32

template <typename T>
struct OrbDescriptorKernelParams
{
  const T * src_image_ptr;
  const T * gaussian_image_ptr;
  const int * u_max_ptr;
  const float * pattern_ptr;
  unsigned char * descriptors_ptr;
  PartKey * keypoints_ptr;
  int image_cols;
  int image_rows;
  int image_steps;
  int num_keypoints;
  Rect image_rect;
};

template <typename T>
struct computeOrientation
{
  OrbDescriptorKernelParams<T> params;
#define KEYPOINT_X 0
#define KEYPOINT_Y 1
#define KEYPOINT_Z 2
#define KEYPOINT_ANGLE 3
#define HALF_PATCH_SIZE 15

  computeOrientation(const OrbDescriptorKernelParams<T> in_params) { params = in_params; }

#define _DBL_EPSILON 2.2204460492503131e-16f
#define atan2_p1 (0.9997878412794807f * 57.29577951308232f)
#define atan2_p3 (-0.3258083974640975f * 57.29577951308232f)
#define atan2_p5 (0.1555786518463281f * 57.29577951308232f)
#define atan2_p7 (-0.04432655554792128f * 57.29577951308232f)

  __device_inline__ float fastAtan2(float y, float x) const
  {
    float ax = std::fabs(x), ay = std::fabs(y);
    float a, c, c2;
    if (ax >= ay) {
      c = ay / (ax + _DBL_EPSILON);
      c2 = c * c;
      a = (((atan2_p7 * c2 + atan2_p5) * c2 + atan2_p3) * c2 + atan2_p1) * c;
    } else {
      c = ax / (ay + _DBL_EPSILON);
      c2 = c * c;
      a = 90.f - (((atan2_p7 * c2 + atan2_p5) * c2 + atan2_p3) * c2 + atan2_p1) * c;
    }
    if (x < 0) a = 180.f - a;
    if (y < 0) a = 360.f - a;
    return a;
  }

  void operator()(sycl::nd_item<1> it)
  {
    int idx = it.get_global_id(0);

    if (idx < params.num_keypoints) {
      decltype(params.keypoints_ptr) kpt = params.keypoints_ptr + idx;

      decltype(params.src_image_ptr) center =
        params.src_image_ptr + kpt->pt.y * params.image_steps + kpt->pt.x;

      int u, v, m_01 = 0, m_10 = 0;

      // Treat the center line differently, v=0
      for (u = -HALF_PATCH_SIZE; u <= HALF_PATCH_SIZE; u++) m_10 += u * center[u];

      // Go line by line in the circular patch
      for (v = 1; v <= HALF_PATCH_SIZE; v++) {
        // Proceed over the two lines
        int v_sum = 0;
        int d = params.u_max_ptr[v];
        for (u = -d; u <= d; u++) {
          int val_plus = center[u + v * params.image_steps],
              val_minus = center[u - v * params.image_steps];
          v_sum += (val_plus - val_minus);
          m_10 += u * (val_plus + val_minus);
        }
        m_01 += v * v_sum;
      }

      // we do not use OpenCL's atan2 intrinsic,
      // because we want to get _exactly_ the same results as the CPU version
      kpt->angle = fastAtan2((float)m_01, (float)m_10);
    }
  }
};

template <typename T>
struct computeDescriptor
{
#define _PI 3.14159265358979f
#define _PI_2 (_PI / 2.0f)
#define _TWO_PI (2.0f * _PI)
#define _INV_TWO_PI (1.0f / _TWO_PI)
#define _THREE_PI_2 (3.0f * _PI_2)

  OrbDescriptorKernelParams<T> params;
  computeDescriptor(const OrbDescriptorKernelParams<T> in_params) { params = in_params; }

  __device_inline__ float _cos(float v)
  {
    constexpr float c1 = 0.99940307f;
    constexpr float c2 = -0.49558072f;
    constexpr float c3 = 0.03679168f;

    float v2 = v * v;
    return c1 + v2 * (c2 + c3 * v2);
  }

  __device_inline__ float cos(float v)
  {
    v = sycl::fabs(v - sycl::floor(v * _INV_TWO_PI) * _TWO_PI);

    unsigned char lpi2 = v < _PI_2;
    unsigned char lpi = (v < _PI) ^ lpi2;
    unsigned char l3pi2 = (v < _THREE_PI_2) ^ lpi ^ lpi2;
    unsigned char other = !(lpi2 | lpi | l3pi2);

    float out;

    if (lpi2) {
      out = _cos(v);
    } else if (lpi) {
      out = -_cos(v - _PI);
    } else if (l3pi2) {
      out = -_cos(v - _PI);
    } else if (other) {
      out = _cos(_TWO_PI - v);
    }

    return out;
  }

  __device_inline__ float sin(float v) { return cos(_PI_2 - v); }

  void operator()(sycl::nd_item<1> it)
  {
    int idx = it.get_global_id(0);

    if (idx < params.num_keypoints) {
      decltype(params.keypoints_ptr) kpt = params.keypoints_ptr + idx;

      decltype(params.src_image_ptr) center =
        params.gaussian_image_ptr + (int)(kpt->pt.y * params.image_steps + kpt->pt.x);
      const float * pattern = params.pattern_ptr;
      float angle = kpt->angle;
      angle *= 0.01745329251994329547f;

      float cosa = cos(angle);
      float sina = sin(angle);

      T * desc = params.descriptors_ptr + idx * DESCRIPTOR_SIZE;

#define GET_VALUE(idx)                                                                \
  center[(int)(std::rint(pattern[(idx) * 2] * sina + pattern[(idx) * 2 + 1] * cosa) * \
                 params.image_steps +                                                 \
               std::rint(pattern[(idx) * 2] * cosa - pattern[(idx) * 2 + 1] * sina))]

      for (int i = 0; i < DESCRIPTOR_SIZE; i++) {
        int val;
        int t0, t1;
        t0 = GET_VALUE(0);
        t1 = GET_VALUE(1);
        val = t0 < t1;

        t0 = GET_VALUE(2);
        t1 = GET_VALUE(3);
        val |= (t0 < t1) << 1;

        t0 = GET_VALUE(4);
        t1 = GET_VALUE(5);
        val |= (t0 < t1) << 2;

        t0 = GET_VALUE(6);
        t1 = GET_VALUE(7);
        val |= (t0 < t1) << 3;

        t0 = GET_VALUE(8);
        t1 = GET_VALUE(9);
        val |= (t0 < t1) << 4;

        t0 = GET_VALUE(10);
        t1 = GET_VALUE(11);
        val |= (t0 < t1) << 5;

        t0 = GET_VALUE(12);
        t1 = GET_VALUE(13);
        val |= (t0 < t1) << 6;

        t0 = GET_VALUE(14);
        t1 = GET_VALUE(15);
        val |= (t0 < t1) << 7;

        pattern += 16 * 2;

        desc[i] = (T)val;
      }
    }
  }
};

template <typename T>
struct OrbDescriptorKernel
{
  OrbDescriptorKernelParams<T> params_;

  OrbDescriptorKernel(
    const std::vector<PartKey> & src_keypoints, const DevImage<T> & src_image,
    const DevImage<T> & gaussian_image, const Vec32f & pattern, const Vec32i & umax,
    DevArray<PartKey> & dev_keypoints, DevArray<uint8_t> & dev_descriptors)
  {
    if (src_image.cols() == 0 || src_image.rows() == 0) {
      throw("Invalid image buffer size");
    }

    if (
      (src_image.cols() != gaussian_image.cols()) || (src_image.rows() != gaussian_image.rows())) {
      throw("Orb Descriptor expects src image and gaussian image to have same size");
    }

    dev_descriptors.resize(src_keypoints.size() * DESCRIPTOR_SIZE);
    dev_keypoints.resize(src_keypoints.size());

    dev_keypoints.upload_async(src_keypoints.data(), src_keypoints.size());

    params_.image_cols = src_image.cols();
    params_.image_rows = src_image.rows();
    params_.image_steps = src_image.elem_step();
    params_.src_image_ptr = src_image.data();
    params_.image_rect = src_image.getRect();
    params_.gaussian_image_ptr = gaussian_image.data();
    params_.pattern_ptr = pattern.data();
    params_.u_max_ptr = umax.data();
    params_.descriptors_ptr = dev_descriptors.data();
    params_.keypoints_ptr = dev_keypoints.data();
    params_.num_keypoints = src_keypoints.size();
  }

  OrbDescriptorKernelParams<T> getDescriptorParams() { return params_; }
};

template <typename T>
void ORBKernel::orbDescriptorImpl(
  const std::vector<PartKey> & src_keypoints, const DevImage<T> & src_image,
  const DevImage<T> & gaussian_image, const Vec32f & pattern, const Vec32i & umax,
  DevArray<PartKey> & dst_keypoint, DevArray<uint8_t> & dst_descriptor, Device::Ptr dev)
{
  sycl::queue * q = dev->GetDeviceImpl()->get_queue();

  OrbDescriptorKernel<T> sycl_orb(
    src_keypoints, src_image, gaussian_image, pattern, umax, dst_keypoint, dst_descriptor);
  OrbDescriptorKernelParams<T> params = sycl_orb.getDescriptorParams();

  auto aligned_width = align(src_keypoints.size(), 16);

  sycl::event event = q->submit([&](sycl::handler & cgh) {
    cgh.depends_on(dst_keypoint.getEvent()->events);
    cgh.parallel_for(
      sycl::nd_range<1>({aligned_width}, {16}),
      [=](sycl::nd_item<1> it) [[sycl::reqd_sub_group_size(16)]] {
        computeOrientation orientationOps(params);
        orientationOps(it);

        computeDescriptor descriptorOps(params);
        descriptorOps(it);
      });
  });

  auto eventPtr = DeviceEvent::create();
  eventPtr->add(event);
  dst_keypoint.setEvent(eventPtr);
  dst_descriptor.setEvent(eventPtr);
}

template void ORBKernel::orbDescriptorImpl(
  const std::vector<PartKey> & src_keypoints, const DevImage<uint8_t> & src_image,
  const DevImage<uint8_t> & gaussian_image, const Vec32f & pattern, const Vec32i & umax,
  DevArray<PartKey> & dst_keypoint, DevArray<uint8_t> & dst_descriptor, Device::Ptr);
